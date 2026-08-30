from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, get_args

try:  # Linux/macOS reportable path; optional so diagnostics still import on Windows.
    import fcntl
except ImportError:  # pragma: no cover - exercised on Windows
    fcntl = None  # type: ignore[assignment]

try:
    import resource
except ImportError:  # pragma: no cover - exercised on Windows
    resource = None  # type: ignore[assignment]

from evaluator.local_evaluator import catalog_index, evaluate, load_jsonl
from src.agent import Agent
from src.catalog import OFFICIAL_CATALOG_SHA256, catalog_sha256
from src.contracts.config import get_run_config
from src.contracts.response import AskAttribute
from src.eval.split import stratified_dev_holdout_split
from src.retrieval import BM25Retriever, DenseRetriever, HybridRetriever
from src.retrieval.dense import (
    MODEL_REVISION,
    OFFICIAL_MODEL_PATH,
    OFFICIAL_MODEL_TREE_SHA256,
    model_tree_sha256,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CANONICAL_RESULTS_LOG = (REPOSITORY_ROOT / "results.jsonl").resolve()
OFFICIAL_CATALOG = (REPOSITORY_ROOT / "data/catalog.jsonl").resolve()
OFFICIAL_DATASET = (REPOSITORY_ROOT / "data/public_set.jsonl").resolve()
OFFICIAL_DATASET_SHA256 = "857259f7a438e6188ac63e18995b6ff4489bfcfc4a716a798b9a2aa0ee8f7579"
REFERENCE_REQUIREMENTS = (REPOSITORY_ROOT / "requirements-dense.lock.txt").resolve()
ALLOWED_ASK_ATTRIBUTES = frozenset(get_args(AskAttribute))


def _peak_rss_kb() -> int | None:
    """Peak resident set size in kilobytes, normalised across platforms.

    ``ru_maxrss`` is reported in kilobytes on Linux but in bytes on macOS/BSD.
    """
    if resource is None:
        return None
    maxrss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return maxrss // 1024 if sys.platform == "darwin" else maxrss


def _latency_summary(samples: list[float]) -> dict[str, float | int] | None:
    """Per-turn agent latency distribution in milliseconds.

    Only turns that returned a response are summarised, so a diagnostic run
    whose agent raised cannot pull the percentiles down with fast failure
    paths. Percentiles use nearest-rank on the sorted sample.
    """
    if not samples:
        return None
    ordered = sorted(samples)

    def percentile(fraction: float) -> float:
        index = int(round(fraction * (len(ordered) - 1)))
        return ordered[min(len(ordered) - 1, max(0, index))]

    return {
        "turns": len(ordered),
        "p50": round(percentile(0.50), 3),
        "p95": round(percentile(0.95), 3),
        "p99": round(percentile(0.99), 3),
        "max": round(ordered[-1], 3),
        "mean": round(sum(ordered) / len(ordered), 3),
    }


def _git_sha() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPOSITORY_ROOT,
            check=True, capture_output=True, text=True,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def _git_dirty(ignored_paths: tuple[str | Path, ...] = ()) -> bool | None:
    """Return whether implementation inputs differ from HEAD.

    The generated results log itself may be ignored so several reportable
    ablations can append to one tracked file without invalidating later runs.
    """
    try:
        output = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=REPOSITORY_ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    ignored: set[str] = set()
    for item in ignored_paths:
        try:
            ignored.add(Path(item).resolve().relative_to(REPOSITORY_ROOT).as_posix())
        except ValueError:
            continue
    for line in output.splitlines():
        changed = line[3:]
        if " -> " in changed:
            changed = changed.rsplit(" -> ", 1)[1]
        if Path(changed).as_posix() not in ignored:
            return True
    return False


def _scores_only(result: dict) -> dict:
    return {key: value for key, value in result.items() if key != "sessions"}


def _validate_jsonl_text(text: str, path: Path) -> None:
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSONL in {path} at line {line_number}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"JSONL record in {path} at line {line_number} is not an object")


def _resolve_results_log(path: str | Path, allow_diagnostic: bool) -> tuple[Path, bool]:
    requested = Path(path)
    if not requested.is_absolute():
        requested = REPOSITORY_ROOT / requested
    absolute = requested.absolute()
    if any(component.is_symlink() for component in (absolute, *absolute.parents)):
        raise ValueError("results log path must not contain symlinks")
    resolved = requested.resolve()
    canonical = resolved == CANONICAL_RESULTS_LOG
    if canonical and allow_diagnostic:
        raise ValueError(
            "--allow-dirty diagnostics must use --results-log outside the repository"
        )
    if not canonical:
        try:
            resolved.relative_to(REPOSITORY_ROOT)
        except ValueError:
            if not allow_diagnostic:
                raise ValueError(
                    "non-canonical result logs require --allow-dirty and must be outside the repository"
                )
        else:
            raise ValueError("refusing to write a non-canonical path inside the repository")
    if resolved.exists():
        status = resolved.stat()
        if not stat.S_ISREG(status.st_mode) or status.st_nlink != 1:
            raise ValueError("results log must be a singly-linked regular file")
    if resolved.exists():
        _validate_jsonl_text(resolved.read_text(encoding="utf-8"), resolved)
    return resolved, canonical


def append_result(path: str | Path, record: dict) -> None:
    """Append one complete JSON object under an advisory inter-process lock."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_RDWR | os.O_CREAT | os.O_APPEND
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(target, flags, 0o644)
    try:
        opened_status = os.fstat(descriptor)
        if not stat.S_ISREG(opened_status.st_mode) or opened_status.st_nlink != 1:
            raise ValueError("results log must be a singly-linked regular file")
        with os.fdopen(descriptor, "a+", encoding="utf-8") as handle:
            descriptor = -1
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            handle.seek(0)
            existing = handle.read()
            _validate_jsonl_text(existing, target)
            handle.seek(0, os.SEEK_END)
            if existing and not existing.endswith("\n"):
                handle.write("\n")
            handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _package_version(distribution: str) -> str | None:
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return None


def _locked_environment_mismatches(path: Path) -> list[str]:
    return _locked_environment_snapshot(path)[1]


def _lock_entries(text: str) -> list[str]:
    """Logical requirement entries, joining backslash line continuations.

    A hash-pinned entry spans several physical lines: ``name==version \\`` then
    one indented ``--hash=`` option per acceptable artifact.
    """
    entries: list[str] = []
    pending: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        continued = line.endswith("\\")
        pending.append(line[:-1].strip() if continued else line)
        if not continued:
            entries.append(" ".join(part for part in pending if part))
            pending.clear()
    if pending:
        entries.append(" ".join(part for part in pending if part))
    return entries


def _locked_environment_snapshot(path: Path) -> tuple[str | None, list[str]]:
    """Hash and validate one immutable view of the reference lock.

    Every entry must pin an artifact digest, not only a version number. A
    version pin lets a later resolution install different bytes under the same
    name; recording the difference afterwards diagnoses it but does not prevent
    it. Requiring ``--hash`` is what makes two installations reproduce.
    """
    try:
        contents = path.read_bytes()
    except OSError:
        return None, ["lock file is missing"]
    digest = hashlib.sha256(contents).hexdigest()
    try:
        text = contents.decode("utf-8")
    except UnicodeDecodeError:
        return digest, ["lock file is not valid UTF-8"]
    mismatches: list[str] = []
    for entry in _lock_entries(text):
        tokens = entry.split()
        name, separator, expected = tokens[0].partition("==")
        if not separator or not name or not expected:
            mismatches.append(f"unsupported lock entry: {entry}")
            continue
        if not any(token.startswith("--hash=") for token in tokens[1:]):
            mismatches.append(f"{name}: lock entry is not hash-pinned")
            continue
        actual = _package_version(name)
        if actual != expected:
            mismatches.append(f"{name}: expected {expected}, found {actual or 'missing'}")
    return digest, mismatches


def _snapshot_file(source: Path, destination: Path) -> str:
    """Copy and hash one evaluation input into a private immutable file."""
    digest = hashlib.sha256()
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with source.open("rb") as reader, os.fdopen(descriptor, "wb") as writer:
            descriptor = -1
            for block in iter(lambda: reader.read(1024 * 1024), b""):
                digest.update(block)
                writer.write(block)
            writer.flush()
            os.fsync(writer.fileno())
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    destination.chmod(0o400)
    return digest.hexdigest()


def _effective_retriever(agent: Agent) -> str:
    if isinstance(agent.retriever, HybridRetriever):
        return "hybrid"
    if isinstance(agent.retriever, DenseRetriever):
        return "dense"
    if isinstance(agent.retriever, BM25Retriever):
        return "bm25" if agent.config.retrieval_mode == "bm25" else "bm25_fallback"
    return type(agent.retriever).__name__


def _embedding_cache_status(agent: Agent) -> str:
    retriever = _dense_retriever(agent)
    return str(getattr(retriever, "cache_status", "not_used"))


def _dense_retriever(agent: Agent) -> DenseRetriever | None:
    retriever = agent.retriever
    if isinstance(retriever, HybridRetriever):
        retriever = retriever.dense
    return retriever if isinstance(retriever, DenseRetriever) else None


class _EvaluatorAgentProxy:
    """Observe turn failures that the vendor evaluator intentionally swallows."""

    def __init__(self, agent: Agent, catalog_ids: set[str] | None = None) -> None:
        self.agent = agent
        self.catalog_ids = catalog_ids
        self.raised_exception_count = 0
        self.invalid_response_count = 0
        self.turn_latency_ms: list[float] = []

    def reset(self, session_id: str, user_profile: dict) -> None:
        self.agent.reset(session_id, user_profile)

    def respond(self, session_id: str, user_message: str, turn: int, top_k: int) -> Any:
        started = time.perf_counter()
        try:
            response = self.agent.respond(session_id, user_message, turn, top_k)
        except Exception:
            self.raised_exception_count += 1
            raise
        self.turn_latency_ms.append((time.perf_counter() - started) * 1000.0)
        if not self._valid_response(response, top_k):
            self.invalid_response_count += 1
        return response

    def _valid_response(self, response: object, top_k: int) -> bool:
        if not isinstance(response, dict) or not isinstance(response.get("message"), str):
            return False
        keys = set(response)
        if not {"message", "ask_attribute", "recommendations"}.issubset(keys):
            return False
        if keys - {"message", "ask_attribute", "recommendations", "usage"}:
            return False
        asked = response.get("ask_attribute")
        if asked is not None and asked not in ALLOWED_ASK_ATTRIBUTES:
            return False
        recommendations = response.get("recommendations")
        if not isinstance(recommendations, list) or len(recommendations) > max(0, min(10, top_k)):
            return False
        seen: set[str] = set()
        for item in recommendations:
            if not isinstance(item, dict) or set(item) - {"parent_asin", "score"}:
                return False
            asin = item.get("parent_asin")
            if not isinstance(asin, str) or not asin.strip() or asin in seen:
                return False
            if self.catalog_ids is not None and asin not in self.catalog_ids:
                return False
            score = item.get("score")
            if score is not None and (
                isinstance(score, bool)
                or not isinstance(score, (int, float))
                or not math.isfinite(float(score))
            ):
                return False
            seen.add(asin)
        usage = response.get("usage")
        if usage is not None:
            if not isinstance(usage, dict) or set(usage) != {
                "prompt_tokens", "completion_tokens",
            }:
                return False
            for key in ("prompt_tokens", "completion_tokens"):
                value = usage.get(key)
                if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    return False
        return True


def _capability_status(
    agent: Agent, proxy: _EvaluatorAgentProxy | None = None,
) -> tuple[dict[str, object], list[str]]:
    effective_retriever = _effective_retriever(agent)
    expected_retriever = agent.config.retrieval_mode
    retriever_ready = effective_retriever == expected_retriever

    reranker_requested = agent.config.reranker == "local_cross_encoder"
    reranker_ready = bool(
        reranker_requested
        and agent.reranker is not None
        and getattr(agent.reranker, "_model", None) is not None
    )
    effective_reranker = "local_cross_encoder" if reranker_ready else "none"

    # No LLM ranking implementation/provider is shipped. Keep H visible in the
    # matrix without presenting the unchanged offline path as an LLM result.
    llm_ready = False
    reasons: list[str] = []
    if not retriever_ready:
        reasons.append(f"requested {expected_retriever} retrieval, used {effective_retriever}")
    if reranker_requested and not reranker_ready:
        reasons.append("requested local cross-encoder is unavailable")
    if agent.config.llm_rank and not llm_ready:
        reasons.append("requested LLM rank is not implemented")
    if agent.exception_count:
        reasons.append(f"agent fallback handled {agent.exception_count} unexpected exception(s)")
    evaluator_raised = proxy.raised_exception_count if proxy is not None else 0
    evaluator_invalid = proxy.invalid_response_count if proxy is not None else 0
    if evaluator_raised:
        reasons.append(f"evaluator swallowed {evaluator_raised} raised turn exception(s)")
    if evaluator_invalid:
        reasons.append(f"evaluator replaced {evaluator_invalid} invalid turn response(s)")

    return {
        "retriever": {
            "requested": expected_retriever,
            "effective": effective_retriever,
            "ready": retriever_ready,
        },
        "reranker": {
            "requested": agent.config.reranker,
            "effective": effective_reranker,
            "ready": not reranker_requested or reranker_ready,
        },
        "llm_rank": {
            "requested": agent.config.llm_rank,
            "effective": llm_ready,
            "ready": not agent.config.llm_rank or llm_ready,
        },
        "agent_exception_count": agent.exception_count,
        "evaluator_raised_exception_count": evaluator_raised,
        "evaluator_invalid_response_count": evaluator_invalid,
    }, reasons


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a reproducible ShopLens ablation")
    parser.add_argument("--catalog", default="data/catalog.jsonl")
    parser.add_argument("--dataset", default="data/public_set.jsonl")
    parser.add_argument("--config", default=None)
    parser.add_argument("--split", choices=("dev", "holdout", "all"), default="all")
    parser.add_argument("--results-log", default="results.jsonl")
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="permit a diagnostic run from an uncommitted tree; recorded as non-reportable",
    )
    args = parser.parse_args()

    try:
        results_path, canonical_results = _resolve_results_log(args.results_log, args.allow_dirty)
    except (OSError, UnicodeError, ValueError) as exc:
        parser.error(str(exc))

    catalog_path = Path(args.catalog)
    if not catalog_path.is_absolute():
        catalog_path = REPOSITORY_ROOT / catalog_path
    catalog_path = catalog_path.resolve()
    dataset_path = Path(args.dataset)
    if not dataset_path.is_absolute():
        dataset_path = REPOSITORY_ROOT / dataset_path
    dataset_path = dataset_path.resolve()

    ignored = (CANONICAL_RESULTS_LOG,) if canonical_results else ()
    start_sha = _git_sha()
    start_dirty = _git_dirty(ignored)
    if start_dirty is not False and not args.allow_dirty:
        reason = "unknown Git state" if start_dirty is None else "uncommitted implementation changes"
        parser.error(f"refusing a reportable run with {reason}; commit first or use --allow-dirty")

    config = get_run_config(args.config)
    if fcntl is None and not args.allow_dirty:
        parser.error("reportable runs require advisory file-lock support")
    reference_platform_ready = (
        platform.python_implementation() == "CPython"
        and sys.version_info[:2] == (3, 12)
        and platform.system() == "Linux"
        and platform.machine().casefold() in {"x86_64", "amd64"}
    )
    requirements_digest_before, lock_mismatches = _locked_environment_snapshot(
        REFERENCE_REQUIREMENTS
    )
    if config.retrieval_mode == "bm25":
        lock_mismatches = []
    if config.retrieval_mode != "bm25" and not args.allow_dirty:
        if not reference_platform_ready:
            parser.error("reportable dense runs require the CPython 3.12 Linux x86-64 reference platform")
        if lock_mismatches:
            parser.error(
                f"dense environment differs from the reference lock ({len(lock_mismatches)} mismatch(es))"
            )
    try:
        catalog_digest_before = catalog_sha256(catalog_path)
        dataset_digest_before = catalog_sha256(dataset_path)
    except OSError as exc:
        parser.error(str(exc))
    if catalog_path == OFFICIAL_CATALOG and catalog_digest_before != OFFICIAL_CATALOG_SHA256:
        parser.error("official catalog checksum mismatch")
    if dataset_path == OFFICIAL_DATASET and dataset_digest_before != OFFICIAL_DATASET_SHA256:
        parser.error("official public dataset checksum mismatch")

    input_snapshot: tempfile.TemporaryDirectory[str] | None = None
    execution_catalog = catalog_path
    execution_dataset = dataset_path
    if not args.allow_dirty:
        input_snapshot = tempfile.TemporaryDirectory(prefix="shoplens-eval-")
        snapshot_root = Path(input_snapshot.name)
        execution_catalog = snapshot_root / "catalog.jsonl"
        execution_dataset = snapshot_root / "public_set.jsonl"
        snapshot_catalog_digest = _snapshot_file(catalog_path, execution_catalog)
        snapshot_dataset_digest = _snapshot_file(dataset_path, execution_dataset)
        if snapshot_catalog_digest != catalog_digest_before:
            parser.error("catalog changed while creating the immutable evaluation snapshot")
        if snapshot_dataset_digest != dataset_digest_before:
            parser.error("dataset changed while creating the immutable evaluation snapshot")

    samples = load_jsonl(execution_dataset)
    dev, holdout = stratified_dev_holdout_split(samples)
    selected = samples if args.split == "all" else (dev if args.split == "dev" else holdout)
    catalog_ids, categories, products = catalog_index(execution_catalog)
    cache_path = execution_catalog.with_suffix(".embeddings.npz")
    cache_existed_before = cache_path.is_file()
    started = time.perf_counter()
    prior_checksum = os.environ.get("SHOPLENS_CATALOG_SHA256")
    if input_snapshot is not None:
        os.environ["SHOPLENS_CATALOG_SHA256"] = catalog_digest_before
    construction_started = time.perf_counter()
    try:
        agent = Agent(execution_catalog, config=config)
    finally:
        agent_init_seconds = time.perf_counter() - construction_started
        if input_snapshot is not None:
            if prior_checksum is None:
                os.environ.pop("SHOPLENS_CATALOG_SHA256", None)
            else:
                os.environ["SHOPLENS_CATALOG_SHA256"] = prior_checksum
    proxy = _EvaluatorAgentProxy(agent, catalog_ids)
    dense = _dense_retriever(agent)
    model_digest_before = dense.model_sha256 if dense is not None else None
    model_path = dense.model_path if dense is not None else None
    cache_path = dense.cache_path if dense is not None else cache_path
    cache_digest_before = dense.cache_sha256 if dense is not None else None
    dense_provenance = dict(dense.cache_provenance) if dense is not None else None
    result = evaluate(proxy, selected, catalog_ids, categories, products)
    elapsed_seconds = time.perf_counter() - started
    end_sha = _git_sha()
    end_dirty = _git_dirty(ignored)
    catalog_digest_after = catalog_sha256(catalog_path)
    dataset_digest_after = catalog_sha256(dataset_path)
    execution_catalog_digest_after = catalog_sha256(execution_catalog)
    execution_dataset_digest_after = catalog_sha256(execution_dataset)
    model_verification_error: str | None = None
    try:
        model_digest_after = model_tree_sha256(model_path) if model_path is not None else None
    except (OSError, ValueError) as exc:
        model_digest_after = None
        model_verification_error = type(exc).__name__
    cache_digest_after: str | None = None
    cache_verification_error: str | None = None
    if dense is not None:
        try:
            if cache_path.is_symlink():
                raise ValueError("cache is a symlink")
            if not cache_path.exists():
                if dense.cache_status != "write_failed":
                    raise ValueError("cache is unexpectedly missing")
            else:
                cache_status = cache_path.lstat()
                if not stat.S_ISREG(cache_status.st_mode) or cache_status.st_nlink != 1:
                    raise ValueError("cache is not a singly-linked regular file")
                cache_digest_after = catalog_sha256(cache_path)
        except (OSError, ValueError) as exc:
            cache_verification_error = type(exc).__name__

    capability_status, reportability_reasons = _capability_status(agent, proxy)
    if args.allow_dirty:
        reportability_reasons.insert(0, "diagnostic --allow-dirty run")
    if not canonical_results:
        reportability_reasons.append("results were written outside the canonical evidence log")
    if start_dirty is True:
        reportability_reasons.append("Git tree was not clean at run start")
    elif start_dirty is None:
        reportability_reasons.append("Git state could not be determined at run start")
    if end_dirty is True:
        reportability_reasons.append("Git tree was not clean at run end")
    elif end_dirty is None:
        reportability_reasons.append("Git state could not be determined at run end")
    if start_sha == "unknown" or end_sha == "unknown":
        reportability_reasons.append("Git revision could not be determined")
    elif start_sha != end_sha:
        reportability_reasons.append("Git revision changed during evaluation")
    if catalog_path != OFFICIAL_CATALOG:
        reportability_reasons.append("non-official catalog path")
    if dataset_path != OFFICIAL_DATASET:
        reportability_reasons.append("non-official public dataset path")
    if agent.catalog_checksum_verified is not True:
        reportability_reasons.append("official catalog checksum was not enforced")
    if catalog_digest_before != agent.catalog.sha256:
        reportability_reasons.append("catalog changed between initial hashing and Agent loading")
    if catalog_digest_before != catalog_digest_after:
        reportability_reasons.append("catalog changed during evaluation")
    if catalog_digest_before != execution_catalog_digest_after:
        reportability_reasons.append("immutable catalog snapshot changed during evaluation")
    if dataset_digest_before != dataset_digest_after:
        reportability_reasons.append("dataset changed during evaluation")
    if dataset_digest_before != execution_dataset_digest_after:
        reportability_reasons.append("immutable dataset snapshot changed during evaluation")
    if config.retrieval_mode != "bm25" and dense is not None:
        if dense.model_path != OFFICIAL_MODEL_PATH.resolve():
            reportability_reasons.append("dense run used a non-official model path")
        if dense.official_model_verified is not True:
            reportability_reasons.append("dense official model verification was not enforced")
        if dense.model_sha256 != OFFICIAL_MODEL_TREE_SHA256:
            reportability_reasons.append("dense model did not match the pinned digest")
        if dense.trusted_for_reporting is not True:
            reportability_reasons.append(
                "dense vectors were not rebuilt in-process from the verified official model"
            )
    if model_verification_error is not None:
        reportability_reasons.append(
            "dense model provenance could not be verified after evaluation"
        )
    if model_digest_before != model_digest_after:
        reportability_reasons.append("dense model changed during evaluation")
    if cache_verification_error is not None:
        reportability_reasons.append("embedding cache provenance could not be verified")
    if cache_digest_before != cache_digest_after:
        reportability_reasons.append("embedding cache changed during evaluation")
    requirements_digest_after, _ = _locked_environment_snapshot(REFERENCE_REQUIREMENTS)
    if requirements_digest_before != requirements_digest_after:
        reportability_reasons.append("locked dense requirements changed during evaluation")
    evidence_sha = _git_sha()
    evidence_dirty = _git_dirty(ignored)
    if evidence_dirty is True:
        reportability_reasons.append("Git tree was not clean when evidence was finalized")
    elif evidence_dirty is None:
        reportability_reasons.append("Git state could not be determined when evidence was finalized")
    if evidence_sha != end_sha:
        reportability_reasons.append("Git revision changed while evidence was finalized")
    if config.retrieval_mode != "bm25" and requirements_digest_before is None:
        reportability_reasons.append("locked dense requirements are missing")
    elif lock_mismatches:
        reportability_reasons.append(
            f"dense environment differs from reference lock ({len(lock_mismatches)} mismatch(es))"
        )
    if config.retrieval_mode != "bm25" and not reference_platform_ready:
        reportability_reasons.append("dense run used a non-reference platform")
    reportable = not reportability_reasons
    record = {
        "config": config.name,
        "split": args.split,
        "scores": _scores_only(result),
        "git_sha": start_sha if start_sha == end_sha == evidence_sha else None,
        "reportable": reportable,
        "reportability_reasons": reportability_reasons,
        "reproducibility": {
            "git": {
                "start_sha": start_sha,
                "end_sha": end_sha,
                "evidence_sha": evidence_sha,
                "start_dirty": start_dirty,
                "end_dirty": end_dirty,
                "evidence_dirty": evidence_dirty,
                "final_sha": None,
                "final_dirty": None,
            },
            "config_flags": asdict(config),
            "effective_retriever": _effective_retriever(agent),
            "capability_status": capability_status,
            "python": platform.python_version(),
            "platform": {
                "system": platform.system(),
                "release": platform.release(),
                "machine": platform.machine(),
                "sqlite": sqlite3.sqlite_version,
            },
            "dependencies": {
                "numpy": _package_version("numpy"),
                "sentence_transformers": _package_version("sentence-transformers"),
                "torch": _package_version("torch"),
                "transformers": _package_version("transformers"),
                "tokenizers": _package_version("tokenizers"),
            },
            "model_revision": MODEL_REVISION if config.retrieval_mode != "bm25" else None,
            "model_sha256": model_digest_before,
            "encoder_runtime_signature": (
                dense.runtime_signature if dense is not None else None
            ),
            "device": dense.device if dense is not None else None,
            "requirements_lock_sha256": requirements_digest_before,
            "requirements_lock_sha256_after": requirements_digest_after,
            "requirements_lock_mismatches": lock_mismatches,
            "catalog_sha256": catalog_digest_before,
            "dataset_sha256": dataset_digest_before,
            "immutable_input_snapshot": input_snapshot is not None,
            "embedding_cache": {
                "path": str(cache_path),
                "existed_before": cache_existed_before,
                "exists_after": cache_path.is_file(),
                "status": _embedding_cache_status(agent),
                "sha256_before_evaluation": cache_digest_before,
                "sha256_after_evaluation": cache_digest_after,
                "verification_error": cache_verification_error,
                "dense_provenance": dense_provenance,
            },
            "elapsed_seconds": round(elapsed_seconds, 6),
            "agent_init_seconds": round(agent_init_seconds, 6),
            "peak_rss_kb": _peak_rss_kb(),
            "turn_latency_ms": _latency_summary(proxy.turn_latency_ms),
        },
    }
    final_sha = _git_sha()
    final_dirty = _git_dirty(ignored)
    record["reproducibility"]["git"]["final_sha"] = final_sha
    record["reproducibility"]["git"]["final_dirty"] = final_dirty
    if final_dirty is True:
        reportability_reasons.append("Git tree was not clean immediately before evidence append")
    elif final_dirty is None:
        reportability_reasons.append("Git state could not be determined before evidence append")
    if final_sha != evidence_sha:
        reportability_reasons.append("Git revision changed immediately before evidence append")
    record["reportable"] = not reportability_reasons
    record["git_sha"] = (
        start_sha
        if start_sha == end_sha == evidence_sha == final_sha and start_sha != "unknown"
        else None
    )
    if canonical_results and not record["reportable"]:
        print(json.dumps(record, indent=2))
        raise SystemExit(
            "refusing to append non-reportable evidence to canonical results.jsonl"
        )
    append_result(results_path, record)
    print(json.dumps(record, indent=2))
    if input_snapshot is not None:
        input_snapshot.cleanup()


if __name__ == "__main__":
    main()

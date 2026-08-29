from __future__ import annotations

import argparse
import importlib.metadata
import json
import platform
import resource
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path

from evaluator.local_evaluator import catalog_index, evaluate, load_jsonl
from src.agent import Agent
from src.catalog import catalog_sha256
from src.contracts.config import get_run_config
from src.eval.split import stratified_dev_holdout_split
from src.retrieval import BM25Retriever, DenseRetriever, HybridRetriever
from src.retrieval.dense import MODEL_REVISION


def _peak_rss_kb() -> int:
    """Peak resident set size in kilobytes, normalised across platforms.

    ``ru_maxrss`` is reported in kilobytes on Linux but in bytes on macOS/BSD.
    """
    maxrss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return maxrss // 1024 if sys.platform == "darwin" else maxrss


def _git_sha() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def _git_dirty(ignored_paths: tuple[str, ...] = ()) -> bool | None:
    """Return whether implementation inputs differ from HEAD.

    The generated results log itself may be ignored so several reportable
    ablations can append to one tracked file without invalidating later runs.
    """
    try:
        output = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    ignored = {Path(item).as_posix() for item in ignored_paths}
    for line in output.splitlines():
        changed = line[3:]
        if " -> " in changed:
            changed = changed.rsplit(" -> ", 1)[1]
        if Path(changed).as_posix() not in ignored:
            return True
    return False


def _scores_only(result: dict) -> dict:
    return {key: value for key, value in result.items() if key != "sessions"}


def append_result(path: str | Path, record: dict) -> None:
    with Path(path).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def _package_version(distribution: str) -> str | None:
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return None


def _effective_retriever(agent: Agent) -> str:
    if isinstance(agent.retriever, HybridRetriever):
        return "hybrid"
    if isinstance(agent.retriever, DenseRetriever):
        return "dense"
    if isinstance(agent.retriever, BM25Retriever):
        return "bm25" if agent.config.retrieval_mode == "bm25" else "bm25_fallback"
    return type(agent.retriever).__name__


def _embedding_cache_status(agent: Agent) -> str:
    retriever = agent.retriever
    if isinstance(retriever, HybridRetriever):
        retriever = retriever.dense
    return str(getattr(retriever, "cache_status", "not_used"))


def _capability_status(agent: Agent) -> tuple[dict[str, object], list[str]]:
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

    dirty = _git_dirty((args.results_log,))
    if dirty is not False and not args.allow_dirty:
        reason = "unknown Git state" if dirty is None else "uncommitted implementation changes"
        parser.error(f"refusing a reportable run with {reason}; commit first or use --allow-dirty")

    config = get_run_config(args.config)
    samples = load_jsonl(args.dataset)
    dev, holdout = stratified_dev_holdout_split(samples)
    selected = samples if args.split == "all" else (dev if args.split == "dev" else holdout)
    catalog_ids, categories, products = catalog_index(args.catalog)
    cache_path = Path(args.catalog).with_suffix(".embeddings.npz")
    cache_existed_before = cache_path.is_file()
    started = time.perf_counter()
    agent = Agent(args.catalog, config=config)
    result = evaluate(agent, selected, catalog_ids, categories, products)
    elapsed_seconds = time.perf_counter() - started
    capability_status, reportability_reasons = _capability_status(agent)
    if dirty is True:
        reportability_reasons.insert(0, "Git tree is not clean")
    elif dirty is None:
        reportability_reasons.insert(0, "Git state could not be determined")
    reportable = not reportability_reasons
    record = {
        "config": config.name,
        "split": args.split,
        "scores": _scores_only(result),
        "git_sha": _git_sha(),
        "reportable": reportable,
        "reportability_reasons": reportability_reasons,
        "reproducibility": {
            "git_dirty": dirty,
            "config_flags": asdict(config),
            "effective_retriever": _effective_retriever(agent),
            "capability_status": capability_status,
            "python": platform.python_version(),
            "dependencies": {
                "numpy": _package_version("numpy"),
                "sentence_transformers": _package_version("sentence-transformers"),
                "torch": _package_version("torch"),
            },
            "model_revision": MODEL_REVISION if config.retrieval_mode != "bm25" else None,
            "catalog_sha256": catalog_sha256(args.catalog),
            "dataset_sha256": catalog_sha256(args.dataset),
            "embedding_cache": {
                "path": str(cache_path),
                "existed_before": cache_existed_before,
                "exists_after": cache_path.is_file(),
                "status": _embedding_cache_status(agent),
            },
            "elapsed_seconds": round(elapsed_seconds, 6),
            "peak_rss_kb": _peak_rss_kb(),
        },
    }
    append_result(args.results_log, record)
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()

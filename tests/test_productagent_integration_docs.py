from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INTEGRATION_RECORD = ROOT / "docs" / "productagent-integration.md"
LOCAL_TRANSCRIPT = "docs/ProductAgent.md"
PUBLIC_CREDIT = (
    ROOT / "README.md",
    ROOT / "docs" / "research-attribution.md",
    ROOT / "docs" / "release-checklist.md",
)
# Measured by the authors on their own 1M-item AliMe KG corpus with an LLM
# agent. They are not ShopLens evidence and must never reach a results surface.
PAPER_ONLY_METRICS = ("32.00", "30.20", "69.00", "8.27", "6.11")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _normalized_markdown(path: Path) -> str:
    lines = _read(path).splitlines()
    return " ".join(line.removeprefix("> ").strip() for line in lines)


def _is_tracked(relative_path: str) -> bool:
    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", relative_path],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    return tracked.returncode == 0


def test_integration_record_cites_the_primary_paper() -> None:
    text = _normalized_markdown(INTEGRATION_RECORD)
    required = {
        "Jingheng Ye",
        "Yong Jiang",
        "Xiaobin Wang",
        "Yinghui Li",
        "Yangning Li",
        "Hai-Tao Zheng",
        "Pengjun Xie",
        "Fei Huang",
        "ProductAgent: Benchmarking Conversational Product Search Agent with Asking Clarification Questions",
        "arXiv:2407.00942",
        "https://arxiv.org/abs/2407.00942",
        "https://doi.org/10.48550/arXiv.2407.00942",
    }

    missing = {value for value in required if value not in text}

    assert not missing


def test_source_audit_records_the_arxiv_license_grant() -> None:
    text = _normalized_markdown(INTEGRATION_RECORD)
    required = {
        "http://arxiv.org/licenses/nonexclusive-distrib/1.0/",
        "perpetual, non-exclusive license to distribute",
        "does not grant",
    }

    missing = {value for value in required if value not in text}

    assert not missing


def test_source_audit_blocks_copying_artifacts_without_clear_terms() -> None:
    text = _read(INTEGRATION_RECORD).casefold()
    required = {
        "upstream productagent code | do not import",
        "alime kg | do not import",
        "local conversion | do not redistribute",
    }

    missing = {value for value in required if value not in text}

    assert not missing


def test_adoption_matrix_has_adopt_evaluate_and_defer_decisions() -> None:
    text = _read(INTEGRATION_RECORD).casefold()
    required = {
        "| adopt |",
        "| evaluate |",
        "| defer |",
        "| do not adopt |",
        "question redundancy",
        "field population",
        "text2sql",
    }

    missing = {value for value in required if value not in text}

    assert not missing


def test_adoption_boundary_preserves_shoplens_contracts() -> None:
    text = _read(INTEGRATION_RECORD).casefold()
    required = {
        "offline determinism",
        "agent contract",
        "immutable catalog",
        "read-only evaluator",
        "dev-only",
    }

    missing = {value for value in required if value not in text}

    assert not missing


def test_repository_entry_points_link_the_integration_record() -> None:
    documents = {
        "README.md": _read(ROOT / "README.md"),
        "DATA_ATTRIBUTION.md": _read(ROOT / "DATA_ATTRIBUTION.md"),
        "docs/data-provenance.md": _read(ROOT / "docs" / "data-provenance.md"),
        "docs/research-attribution.md": _read(ROOT / "docs" / "research-attribution.md"),
    }
    missing = {
        name
        for name, text in documents.items()
        if "productagent-integration.md" not in text
    }

    assert not missing


def test_release_facing_docs_contain_full_paper_credit() -> None:
    required = {
        "Jingheng Ye",
        "Hai-Tao Zheng",
        "Fei Huang",
        "2024",
        "ProductAgent: Benchmarking Conversational Product Search Agent with Asking Clarification Questions",
        "arXiv:2407.00942",
    }

    for path in PUBLIC_CREDIT:
        text = _normalized_markdown(path)
        assert not {item for item in required if item not in text}, path


def test_release_facing_docs_state_the_non_permissive_license() -> None:
    for path in PUBLIC_CREDIT:
        text = _normalized_markdown(path).casefold()
        assert "arxiv non-exclusive distribution license" in text, path


def test_paper_metrics_never_reach_a_shoplens_results_surface() -> None:
    tracked_docs = subprocess.run(
        ["git", "ls-files", "*.md"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split()

    offenders = {
        (name, metric)
        for name in tracked_docs
        if name != "docs/productagent-integration.md"
        for metric in PAPER_ONLY_METRICS
        if metric in _read(ROOT / name)
    }

    assert not offenders


def test_local_transcript_is_ignored_and_untracked() -> None:
    ignore = _read(ROOT / ".gitignore").splitlines()

    assert LOCAL_TRANSCRIPT in ignore
    assert not _is_tracked(LOCAL_TRANSCRIPT)
    assert not _is_tracked("docs/10-implementation-checklist.md")


def test_release_asset_archives_are_ignored() -> None:
    ignored = subprocess.run(
        ["git", "check-ignore", "data/catalog.jsonl.gz"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert ignored.returncode == 0

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INTEGRATION_RECORD = ROOT / "docs" / "wizard-of-shopping-integration.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_integration_record_cites_the_primary_paper() -> None:
    text = _read(INTEGRATION_RECORD)
    required = {
        "Xiangci Li",
        "Zhiyu Chen",
        "Jason Ingyu Choi",
        "Nikhita Vedula",
        "Besnik Fetahu",
        "Oleg Rokhlenko",
        "Shervin Malmasi",
        "https://aclanthology.org/2025.acl-long.641/",
        "https://doi.org/10.18653/v1/2025.acl-long.641",
        "CC BY 4.0",
    }

    assert not required.difference(text)


def test_source_audit_blocks_copying_artifacts_without_clear_terms() -> None:
    text = _read(INTEGRATION_RECORD).casefold()
    required = {
        "research purposes",
        "trec product search",
        "upstream code | do not import",
        "wos dataset | do not import",
    }

    assert not required.difference(text)


def test_adoption_matrix_has_adopt_evaluate_and_defer_decisions() -> None:
    text = _read(INTEGRATION_RECORD).casefold()
    required = {
        "| adopt |",
        "| evaluate |",
        "| defer |",
        "wanted, unwanted, and optional",
        "information-gain",
    }

    assert not required.difference(text)


def test_adoption_boundary_preserves_shoplens_contracts() -> None:
    text = _read(INTEGRATION_RECORD).casefold()
    required = {
        "offline determinism",
        "agent contract",
        "immutable catalog",
        "read-only evaluator",
        "dev-only",
    }

    assert not required.difference(text)


def test_repository_entry_points_link_the_integration_record() -> None:
    documents = {
        "README.md": _read(ROOT / "README.md"),
        "DATA_ATTRIBUTION.md": _read(ROOT / "DATA_ATTRIBUTION.md"),
        "docs/data-provenance.md": _read(ROOT / "docs" / "data-provenance.md"),
    }
    missing = {
        name
        for name, text in documents.items()
        if "wizard-of-shopping-integration.md" not in text
    }

    assert not missing

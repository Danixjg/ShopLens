from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INTEGRATION_RECORD = ROOT / "docs" / "wizard-of-shopping-integration.md"
PRODUCTAGENT_RECORD = ROOT / "docs" / "productagent-integration.md"
RESULTS_LOG = ROOT / "results.jsonl"


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

    missing = {value for value in required if value not in text}

    assert not missing


def test_source_audit_blocks_copying_artifacts_without_clear_terms() -> None:
    text = _read(INTEGRATION_RECORD).casefold()
    required = {
        "research purposes",
        "trec product search",
        "upstream code | do not import",
        "wos dataset | do not import",
    }

    missing = {value for value in required if value not in text}

    assert not missing


def test_adoption_matrix_has_adopt_evaluate_and_defer_decisions() -> None:
    text = _read(INTEGRATION_RECORD).casefold()
    required = {
        "| adopt |",
        "| evaluate |",
        "| defer |",
        "wanted, unwanted, and optional",
        "information-gain",
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
        "docs/release-checklist.md": _read(ROOT / "docs" / "release-checklist.md"),
        "docs/demo-script.md": _read(ROOT / "docs" / "demo-script.md"),
    }
    missing = {
        name
        for name, text in documents.items()
        if "wizard-of-shopping-integration.md" not in text
    }

    assert not missing


def _dev_technical_score(config: str) -> str:
    """Latest reportable dev TechnicalScore for one config, formatted as docs write it.

    Reading the number from the evidence log rather than hard-coding it means a
    documented outcome cannot drift away from the run it claims to describe.
    """
    scores = []
    for line in RESULTS_LOG.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row["config"] == config and row["split"] == "dev" and row["reportable"]:
            scores.append(row["scores"]["recommended_technical_score"])
    assert scores, f"no reportable dev row for config {config}"
    return f"{scores[-1]:.6f}"


def test_adoption_matrix_records_the_measured_facet_gate_outcome() -> None:
    """Catalog-aware aspect selection was built as config V and measured.

    The audit may not present it as an open decision once a reportable run
    exists: it must carry the measured score and say it is not retained.
    """
    text = _read(INTEGRATION_RECORD)
    required = {
        _dev_technical_score("V"),
        "99.43",
    }

    missing = {value for value in required if value not in text}

    assert not missing
    assert "not retained" in text.casefold()


def test_audit_records_the_planner_gap_outcome() -> None:
    """The closing prerequisite demanded the planner gap be tested before adoption.

    Config U supplied that test and failed its gate, so the audit must record
    the rejection rather than leave the prerequisite reading as pending.
    """
    text = _read(INTEGRATION_RECORD)

    assert _dev_technical_score("U") in text
    assert "rejected" in text.casefold()


def test_audit_cross_references_the_shared_facet_credit() -> None:
    """One implementation claimed by two source audits must be visible from both."""
    assert "productagent-integration.md" in _read(INTEGRATION_RECORD)
    assert "wizard-of-shopping-integration.md" in _read(PRODUCTAGENT_RECORD)

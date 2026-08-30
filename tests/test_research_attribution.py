from __future__ import annotations

import re
import subprocess
from pathlib import Path

from src.contracts.config import CONFIGS


ROOT = Path(__file__).resolve().parents[1]
ATTRIBUTION = ROOT / "docs" / "research-attribution.md"
PUBLIC_CREDIT = (
    ROOT / "README.md",
    ROOT / "docs" / "devpost-draft.md",
    ROOT / "docs" / "release-checklist.md",
)


def _normalized_markdown(path: Path) -> str:
    lines = path.read_text(encoding="utf-8").splitlines()
    return " ".join(line.removeprefix("> ").strip() for line in lines)


def test_research_attribution_contains_canonical_paper_credit() -> None:
    text = ATTRIBUTION.read_text(encoding="utf-8")
    required = {
        "Sudha Rao",
        "Hal Daumé III",
        "Learning to Ask Good Questions: Ranking Clarification Questions using Neural Expected Value of Perfect Information",
        "10.18653/v1/P18-1255",
        "https://aclanthology.org/P18-1255/",
        "Creative Commons Attribution 4.0 International",
        "independent",
    }

    assert not {item for item in required if item not in text}


def test_readme_links_the_research_attribution() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "[Research attribution](docs/research-attribution.md)" in readme


def test_release_facing_docs_contain_full_paper_credit() -> None:
    required = {
        "Sudha Rao",
        "Hal Daumé III",
        "2018",
        "Learning to Ask Good Questions: Ranking Clarification Questions using Neural Expected Value of Perfect Information",
        "ACL 2018",
        "2737–2746",
        "10.18653/v1/P18-1255",
        "https://aclanthology.org/P18-1255/",
        "CC BY 4.0",
    }

    for path in PUBLIC_CREDIT:
        text = _normalized_markdown(path)
        assert not {item for item in required if item not in text}, path


def test_public_evpi_outcome_matches_reportable_evidence() -> None:
    required = {
        "U",
        "87834f4",
        "0.941667",
        "0.641323",
        "3.175000",
        "0.819730",
        "0.819939",
    }

    for path in PUBLIC_CREDIT:
        text = _normalized_markdown(path)
        assert not {item for item in required if item not in text}, path


def test_local_reference_transcript_remains_ignored() -> None:
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()

    assert "docs/Learning_to_Ask_Good_Questions.md" in ignore

    tracked = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "docs/Learning_to_Ask_Good_Questions.md"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert tracked.returncode != 0


def test_readme_ablation_table_documents_every_registered_config() -> None:
    """Every config that ships in CONFIGS must appear in the README ablation table.

    R, S, and T were registered and measured on reportable rows without ever
    reaching the README, so the published table understated what had been run.
    Pinning the table to the registry stops a future config being added without
    being documented.
    """
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    documented = {
        match.group(1) for match in re.finditer(r"^\| ([A-Z]) \| ", text, re.MULTILINE)
    }

    missing = set(CONFIGS) - documented

    assert not missing

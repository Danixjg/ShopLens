from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ATTRIBUTION = ROOT / "docs" / "research-attribution.md"


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


def test_local_reference_transcript_remains_ignored() -> None:
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()

    assert "docs/Learning_to_Ask_Good_Questions.md" in ignore

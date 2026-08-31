from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

from src.contracts.config import CONFIGS, get_run_config


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


def test_every_tracked_document_link_resolves_in_a_fresh_clone() -> None:
    """No tracked document may link to a path that is absent from a fresh clone.

    The local paper conversions are deliberately Git-ignored, so linking to one
    leaves a dead link in the published repository even though the file is
    present on the author's machine. Scanning every tracked document catches
    the whole class, including the evidence records under docs/testing.
    """
    tracked = subprocess.run(
        ["git", "ls-files", "*.md"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()

    dangling = []
    for relative in tracked:
        document = ROOT / relative
        text = document.read_text(encoding="utf-8")
        for target in re.findall(r"\]\(([^)]+)\)", text):
            if "://" in target or target.startswith(("#", "mailto:")):
                continue
            path = target.split("#", 1)[0]
            if path and not (document.parent / path).exists():
                dangling.append(f"{relative} -> {target}")

    assert not dangling


RESULTS_LOG = ROOT / "results.jsonl"
CLEAN_HOLDOUT_CONFIGS = ("P", "R", "S")
EXPLORATORY_HOLDOUT_CONFIGS = ("Q", "T", "O")


def _reported_score(config: str, split: str) -> str:
    """Latest reportable TechnicalScore for one config and split.

    Documents must quote the evidence log rather than a remembered number, so
    the expectation is derived from the log instead of hard-coded.
    """
    scores = []
    for line in RESULTS_LOG.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row["config"] == config and row["split"] == split and row["reportable"]:
            scores.append(row["scores"]["recommended_technical_score"])
    assert scores, f"no reportable {split} row for config {config}"
    return f"{scores[-1]:.6f}"


def test_readme_reports_every_measured_candidate_on_both_splits() -> None:
    """A candidate with reportable dev and holdout rows must appear with both.

    Reporting only the configurations that flatter the submission is the
    failure this guards against.
    """
    text = (ROOT / "README.md").read_text(encoding="utf-8")

    missing = [
        f"{config}/{split}={_reported_score(config, split)}"
        for config in CLEAN_HOLDOUT_CONFIGS + EXPLORATORY_HOLDOUT_CONFIGS
        for split in ("dev", "holdout")
        if _reported_score(config, split) not in text
    ]

    assert not missing


def test_public_docs_never_quote_an_exploratory_score_without_the_label() -> None:
    """Q and T carry the popularity prior, so their holdout rows are exploratory.

    Every line quoting one of those numbers, in any release-facing document,
    must say so on that same line. This is what stops the caveat drifting away
    from the figure it qualifies once the number starts to look good. "Clean
    reportable run" and "clean holdout" mean different things, and a reader
    skimming a single sentence must not be able to confuse them.
    """
    unlabelled = []
    for path in PUBLIC_CREDIT:
        for config in EXPLORATORY_HOLDOUT_CONFIGS:
            score = _reported_score(config, "holdout")
            for line in path.read_text(encoding="utf-8").splitlines():
                if score in line and "exploratory" not in line.casefold():
                    unlabelled.append(f"{path.name} {config} {score}: {line.strip()[:60]}")

    assert not unlabelled


def test_readme_never_describes_a_measured_config_as_unrun() -> None:
    """A config holding a reportable row may not be described as never run.

    V's prose survived its own evaluation: it still claimed V was unevaluated
    with no row in results.jsonl, while the candidate table in the same
    document already quoted V's dev score.
    """
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    measured = sorted(
        {
            json.loads(line)["config"]
            for line in RESULTS_LOG.read_text(encoding="utf-8").splitlines()
            if line.strip() and json.loads(line)["reportable"]
        }
    )

    stale = [
        f"{config}: {claim}"
        for config in measured
        for claim in (
            f"{config} is implemented but **unevaluated**",
            f"so {config} is not a retained configuration and has",
        )
        if claim in text
    ]

    assert not stale


def test_default_config_is_the_documented_submission_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A bare Agent must run the configuration the README calls the submission.

    The official harness constructs the Agent without setting SHOPLENS_CONFIG,
    so a default that disagrees with the documented submission configuration
    would have the entry point graded on a different system than the one the
    write-up reports. Binding the default to the README declaration keeps the
    two from drifting apart in either direction.
    """
    monkeypatch.delenv("SHOPLENS_CONFIG", raising=False)
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    declared = re.search(
        r"\*\*Configuration ([A-Z]) is the submission configuration\.\*\*", readme
    )

    assert declared, "the README must name a submission configuration"
    assert get_run_config().name == declared.group(1)

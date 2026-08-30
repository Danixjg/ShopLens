"""Config X: an overridden preference is rejected information, not absent information."""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from src.catalog import Catalog
from src.contracts.config import CONFIGS
from src.contracts.retrieval import Candidate, RetrievalQuery
from src.contracts.state import SessionState, Slot
from src.scoring.constraints import ConstraintScorer
from src.state import build_retrieval_query


@pytest.fixture
def two_material_catalog(tmp_path: Path) -> Catalog:
    """One leather boot and one canvas boot, identical otherwise."""
    path = tmp_path / "catalog.jsonl"
    path.write_text(
        "".join(
            json.dumps(row) + "\n"
            for row in (
                {"parent_asin": "LEATHER", "title": "boot", "features": ["leather upper"]},
                {"parent_asin": "CANVAS", "title": "boot", "features": ["canvas upper"]},
            )
        ),
        encoding="utf-8",
    )
    return Catalog(path)


def _slot(value: str, *, active: bool, superseded: bool = False, turn: int = 1) -> Slot:
    return Slot(
        attribute="material",
        value=value,
        hard=False,
        source_turn=turn,
        confidence=1.0,
        active=active,
        updated_at=turn,
        superseded=superseded,
    )


def test_query_carries_the_superseded_value_as_an_exclusion() -> None:
    """The override scenario's whole point: the old value is now unwanted."""
    state = SessionState(slots=[_slot("leather", active=False, superseded=True)], turn_index=3)

    query = build_retrieval_query(state, exclude_superseded=True)

    assert query.exclude == (("material", "leather"),)


def test_baseline_query_leaves_exclusions_empty() -> None:
    """T must be untouched, so the seam stays inert unless the flag is on."""
    state = SessionState(slots=[_slot("leather", active=False, superseded=True)], turn_index=3)

    assert build_retrieval_query(state).exclude == ()


def test_a_superseded_slot_never_returns_to_the_positive_query() -> None:
    state = SessionState(slots=[_slot("leather", active=False, superseded=True)], turn_index=3)

    query = build_retrieval_query(state, exclude_superseded=True)

    assert "leather" not in query.text
    assert ("material", "leather") not in query.soft
    assert ("material", "leather") not in query.hard


def test_excluded_value_penalises_only_the_matching_candidate(two_material_catalog: Catalog) -> None:
    scorer = ConstraintScorer(two_material_catalog)
    query = RetrievalQuery(text="boot", exclude=(("material", "leather"),), turn_index=1)
    candidates = [Candidate("LEATHER", 1.0), Candidate("CANVAS", 1.0)]

    scored = {item.asin: item.score for item in scorer.score(candidates, query)}

    assert scored["LEATHER"] < scored["CANVAS"]
    assert scored["CANVAS"] == pytest.approx(1.0)


def test_exclusion_records_its_own_scoring_component(two_material_catalog: Catalog) -> None:
    scorer = ConstraintScorer(two_material_catalog)
    query = RetrievalQuery(text="boot", exclude=(("material", "leather"),), turn_index=1)

    scored = {item.asin: item.components for item in scorer.score([Candidate("LEATHER", 1.0)], query)}

    assert scored["LEATHER"]["excluded_material"] < 0.0


def test_exclusion_decays_with_the_turn_like_every_soft_signal(two_material_catalog: Catalog) -> None:
    """Mirrors the existing soft_weight decay rather than adding a new constant."""
    scorer = ConstraintScorer(two_material_catalog)
    early = RetrievalQuery(text="boot", exclude=(("material", "leather"),), turn_index=1)
    late = RetrievalQuery(text="boot", exclude=(("material", "leather"),), turn_index=9)

    early_penalty = scorer.score([Candidate("LEATHER", 1.0)], early)[0].components["excluded_material"]
    late_penalty = scorer.score([Candidate("LEATHER", 1.0)], late)[0].components["excluded_material"]

    assert early_penalty < late_penalty < 0.0


def test_no_exclusions_leaves_scores_exactly_as_they_were(two_material_catalog: Catalog) -> None:
    """The inert path must be bit-identical, or T's evidence would move."""
    scorer = ConstraintScorer(two_material_catalog)
    query = RetrievalQuery(text="boot", turn_index=1)

    scored = scorer.score([Candidate("LEATHER", 1.0), Candidate("CANVAS", 1.0)], query)

    assert [item.score for item in scored] == [1.0, 1.0]


def test_a_declined_question_is_not_an_unwanted_value() -> None:
    """"I would rather not say" is not "I do not want that".

    Conflating them would suppress products over a question the shopper simply
    skipped, which is a different and much more damaging behaviour.
    """
    state = SessionState(slots=[_slot("leather", active=True)], turn_index=2)
    state.declined_attributes.add("material")

    assert build_retrieval_query(state, exclude_superseded=True).exclude == ()


def test_config_x_is_t_with_only_the_negative_preference_flag_changed() -> None:
    assert CONFIGS["X"].negative_preference is True
    assert CONFIGS["T"].negative_preference is False
    assert replace(CONFIGS["X"], name="T", negative_preference=False) == CONFIGS["T"]

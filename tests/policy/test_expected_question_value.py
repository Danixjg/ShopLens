from __future__ import annotations

import json
from dataclasses import fields, replace
from math import isclose, isfinite
from pathlib import Path
from typing import get_args

import pytest

from agent import Agent as SubmissionAgent
from src.catalog import Catalog
from src.contracts.config import CONFIGS, ClarificationMode
from src.contracts.retrieval import Candidate
from src.contracts.state import SessionState
from src.policy import ClarificationPolicy
from src.policy.question_value import expected_question_value, rank_weights


def _catalog(tmp_path: Path) -> Catalog:
    path = tmp_path / "catalog.jsonl"
    rows = [
        {
            "parent_asin": "A",
            "title": "coat",
            "features": ["waterproof"],
            "details": {"Material": "Cotton"},
        },
        {
            "parent_asin": "B",
            "title": "coat",
            "features": ["waterproof"],
            "details": {"Material": "Cotton"},
        },
        {
            "parent_asin": "C",
            "title": "coat",
            "features": ["waterproof"],
            "details": {"Material": "Wool"},
        },
        {
            "parent_asin": "D",
            "title": "coat",
            "features": ["waterproof"],
            "details": {"Material": "Wool"},
        },
    ]
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return Catalog(path)


def test_rank_weights_are_normalized_and_descending() -> None:
    weights = rank_weights(4)

    assert isclose(sum(weights), 1.0) and all(
        left > right > 0.0 for left, right in zip(weights, weights[1:])
    )


def test_question_value_rewards_answers_that_split_the_candidate_pool() -> None:
    weights = [1.0, 1.0, 1.0, 1.0]
    uninformative = expected_question_value(
        [("same",)] * 4, weights=weights, recommendation_limit=1,
    )
    useful = expected_question_value(
        [("x",), ("x",), ("y",), ("y",)],
        weights=weights,
        recommendation_limit=1,
    )
    identifying = expected_question_value(
        [("w",), ("x",), ("y",), ("z",)],
        weights=weights,
        recommendation_limit=1,
    )

    assert uninformative == 0.0 < useful < identifying <= 1.0


def test_missing_answers_contribute_no_false_information_gain() -> None:
    value = expected_question_value(
        [(), (), (), ()],
        weights=[1.0, 1.0, 1.0, 1.0],
        recommendation_limit=1,
    )

    assert value == 0.0


def test_multi_value_answers_share_probability_mass_without_exceeding_bounds() -> None:
    value = expected_question_value(
        [("x", "y"), ("y",)],
        weights=[1.0, 1.0],
        recommendation_limit=1,
    )

    assert isfinite(value) and 0.0 < value <= 1.0


def test_question_value_normalizes_equivalent_weight_scales() -> None:
    buckets = [("x",), ("x",), ("y",)]

    assert isclose(
        expected_question_value(buckets, weights=[1.0, 2.0, 3.0], recommendation_limit=1),
        expected_question_value(buckets, weights=[10.0, 20.0, 30.0], recommendation_limit=1),
    )


def test_question_value_rejects_mismatched_weights() -> None:
    with pytest.raises(ValueError, match="one weight per answer bucket"):
        expected_question_value([("x",)], weights=[], recommendation_limit=1)


def test_expected_value_policy_prefers_useful_material_question(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    candidates = [Candidate(letter, score) for letter, score in zip("ABCD", (4.0, 3.0, 2.0, 1.0))]
    state = SessionState()

    selected = ClarificationPolicy(CONFIGS["U"], catalog).choose(
        state,
        candidates,
        over_general=True,
        recommendation_limit=1,
    )

    assert selected == "material"


def test_expected_value_policy_respects_declines_and_preserves_state(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    candidates = [Candidate(letter, score) for letter, score in zip("ABCD", (4.0, 3.0, 2.0, 1.0))]
    state = SessionState(declined_attributes={"material"})

    selected = ClarificationPolicy(CONFIGS["U"], catalog).choose(
        state,
        candidates,
        over_general=True,
        recommendation_limit=1,
    )

    assert selected == "other" and state.asked_attributes == []


def test_expected_value_policy_uses_targeted_fallback_after_other(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    state = SessionState(
        asked_attributes=["other"],
        declined_attributes={"material"},
    )

    selected = ClarificationPolicy(CONFIGS["U"], catalog).choose(
        state,
        [],
        over_general=True,
        recommendation_limit=1,
    )

    assert selected == "feature"


def test_config_u_is_p_with_only_expected_value_clarification_changed() -> None:
    changed = {
        field.name
        for field in fields(CONFIGS["P"])
        if getattr(CONFIGS["P"], field.name) != getattr(CONFIGS["U"], field.name)
    }

    assert changed == {"name", "clarification"}


def test_expected_value_is_a_declared_clarification_mode() -> None:
    assert "expected_value" in get_args(ClarificationMode)


def test_agent_builds_facets_for_expected_value_mode(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    config = replace(CONFIGS["A"], name="U-test", clarification="expected_value")

    agent = SubmissionAgent(catalog.path, config=config)

    assert agent.catalog.facet_values("A", "material") == ("cotton",)

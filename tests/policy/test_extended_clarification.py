from __future__ import annotations

import json
from dataclasses import fields, replace
from pathlib import Path

import pytest

from src.catalog import Catalog
from src.contracts.config import CONFIGS
from src.contracts.retrieval import Candidate
from src.contracts.state import SessionState
from src.policy import ClarificationPolicy
from src.policy.clarification import CLARIFICATION_SEQUENCE, EXTENDED_CLARIFICATION_SEQUENCE


def _write(path: Path, rows: list[dict]) -> Catalog:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return Catalog(path)


@pytest.fixture
def populated_catalog(tmp_path: Path) -> Catalog:
    """Feature, material and color are all answerable, so the gain-based
    branch of _information_choice has somewhere to go before exhaustion."""
    return _write(
        tmp_path / "catalog.jsonl",
        [
            {"parent_asin": "A", "title": "coat", "features": ["waterproof"], "details": {"Color": "Black"}, "price": 20.0},
            {"parent_asin": "B", "title": "coat", "features": ["insulated"], "details": {"Color": "Brown"}, "price": 30.0},
            {"parent_asin": "C", "title": "coat", "features": ["waterproof"], "details": {"Color": "Brown"}, "price": None},
            {"parent_asin": "D", "title": "coat", "features": ["insulated"], "details": {"Color": "Black"}, "price": None},
        ],
    )


def _candidates() -> list[Candidate]:
    return [Candidate(letter, score) for letter, score in zip("ABCD", (4.0, 3.0, 2.0, 1.0))]


def test_config_k_is_o_with_only_extended_clarification_changed() -> None:
    baseline, extended = CONFIGS["O"], CONFIGS["K"]
    differing = {
        field.name
        for field in fields(baseline)
        if getattr(baseline, field.name) != getattr(extended, field.name)
    }

    assert differing == {"name", "extended_clarification"}
    assert extended.extended_clarification is True
    assert baseline.extended_clarification is False
    assert replace(baseline, name="K", extended_clarification=True) == extended


def test_extended_sequence_only_appends_budget() -> None:
    assert EXTENDED_CLARIFICATION_SEQUENCE[: len(CLARIFICATION_SEQUENCE)] == CLARIFICATION_SEQUENCE
    assert EXTENDED_CLARIFICATION_SEQUENCE == (*CLARIFICATION_SEQUENCE, "budget")


def test_baseline_o_goes_silent_once_the_fixed_sequence_and_other_are_exhausted(
    populated_catalog: Catalog,
) -> None:
    """Pins the stall this config is meant to fix: O has nothing left to ask."""
    state = SessionState(asked_attributes=["feature", "material", "color", "other"])

    selected = ClarificationPolicy(CONFIGS["O"], populated_catalog).choose(
        state, _candidates(), over_general=True,
    )

    assert selected is None


def test_config_k_asks_budget_once_the_fixed_sequence_and_other_are_exhausted(
    populated_catalog: Catalog,
) -> None:
    state = SessionState(asked_attributes=["feature", "material", "color", "other"])

    selected = ClarificationPolicy(CONFIGS["K"], populated_catalog).choose(
        state, _candidates(), over_general=True,
    )

    assert selected == "budget"


def test_config_k_asks_budget_before_other_when_pool_is_not_over_general(
    populated_catalog: Catalog,
) -> None:
    """Once feature/material/color are exhausted, an unasked sequence entry
    is preferred over the generic "other" catch-all whenever the pool isn't
    ambiguous (the `not over_general and unasked: return unasked[0]` branch
    fires before the "other" check does). This is a real divergence from O,
    which has nothing left in its own sequence at this point and falls
    straight to "other" -- see test_config_k_matches_o_while_its_own_sequence_
    still_has_an_unasked_attribute for where K and O do still agree."""
    state = SessionState(asked_attributes=["feature", "material", "color"])

    selected = ClarificationPolicy(CONFIGS["K"], populated_catalog).choose(
        state, _candidates(), over_general=False,
    )

    assert selected == "budget"


def test_config_k_matches_o_while_its_own_sequence_still_has_an_unasked_attribute(
    populated_catalog: Catalog,
) -> None:
    """K and O agree for as long as O's own 3-attribute sequence still has an
    unasked entry -- budget never outranks a real remaining feature/material/
    color choice. They only diverge once O's sequence is fully asked (see the
    two tests above)."""
    for asked in ([], ["feature"], ["feature", "material"]):
        state_o = SessionState(asked_attributes=list(asked))
        state_k = SessionState(asked_attributes=list(asked))
        for over_general in (True, False):
            o_choice = ClarificationPolicy(CONFIGS["O"], populated_catalog).choose(
                state_o, _candidates(), over_general=over_general,
            )
            k_choice = ClarificationPolicy(CONFIGS["K"], populated_catalog).choose(
                state_k, _candidates(), over_general=over_general,
            )
            assert k_choice == o_choice, (asked, over_general)


def test_config_k_never_repeats_budget(populated_catalog: Catalog) -> None:
    state = SessionState(
        asked_attributes=["feature", "material", "color", "other", "budget"],
    )

    selected = ClarificationPolicy(CONFIGS["K"], populated_catalog).choose(
        state, _candidates(), over_general=True,
    )

    assert selected is None

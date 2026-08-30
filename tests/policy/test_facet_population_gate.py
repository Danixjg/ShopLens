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


def _write(path: Path, rows: list[dict]) -> Catalog:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return Catalog(path)


@pytest.fixture
def split_catalog(tmp_path: Path) -> Catalog:
    """Feature and color are answerable; material is absent from every record.

    This is the shape the ProductAgent audit flags: a facet that exists in the
    schema but is unpopulated for the live pool, so a question about it cannot
    be answered from the catalog.
    """
    return _write(
        tmp_path / "catalog.jsonl",
        [
            {"parent_asin": "A", "title": "coat", "features": ["waterproof"], "details": {"Color": "Black"}},
            {"parent_asin": "B", "title": "coat", "features": ["waterproof"], "details": {"Color": "Brown"}},
            {"parent_asin": "C", "title": "coat", "features": ["insulated"], "details": {"Color": "Black"}},
            {"parent_asin": "D", "title": "coat", "features": ["insulated"], "details": {"Color": "Brown"}},
        ],
    )


@pytest.fixture
def barren_catalog(tmp_path: Path) -> Catalog:
    """No targeted facet is populated for any record."""
    return _write(
        tmp_path / "barren.jsonl",
        [
            {"parent_asin": "A", "title": "coat", "features": [], "details": {}},
            {"parent_asin": "B", "title": "coat", "features": [], "details": {}},
            {"parent_asin": "C", "title": "coat", "features": [], "details": {}},
            {"parent_asin": "D", "title": "coat", "features": [], "details": {}},
        ],
    )


def _candidates() -> list[Candidate]:
    return [Candidate(letter, score) for letter, score in zip("ABCD", (4.0, 3.0, 2.0, 1.0))]


def test_config_v_is_p_with_only_the_population_gate_changed() -> None:
    baseline, gated = CONFIGS["P"], CONFIGS["V"]
    differing = {
        field.name
        for field in fields(baseline)
        if getattr(baseline, field.name) != getattr(gated, field.name)
    }

    assert differing == {"name", "facet_population_gate"}
    assert gated.facet_population_gate is True
    assert baseline.facet_population_gate is False
    assert replace(baseline, name="V", facet_population_gate=True) == gated


def test_fixture_leaves_material_unpopulated(split_catalog: Catalog) -> None:
    assert all(split_catalog.facet_values(asin, "material") == () for asin in "ABCD")
    assert any(split_catalog.facet_values(asin, "color") for asin in "ABCD")


def test_gate_skips_an_unanswerable_facet_on_a_targeted_turn(
    split_catalog: Catalog,
) -> None:
    state = SessionState(asked_attributes=["feature"])

    selected = ClarificationPolicy(CONFIGS["V"], split_catalog).choose(
        state, _candidates(), over_general=False,
    )

    assert selected == "color"


def test_ungated_baseline_still_asks_the_unanswerable_facet(
    split_catalog: Catalog,
) -> None:
    """Pins the gap the gate closes, and proves config P is left alone."""
    state = SessionState(asked_attributes=["feature"])

    selected = ClarificationPolicy(CONFIGS["P"], split_catalog).choose(
        state, _candidates(), over_general=False,
    )

    assert selected == "material"


def test_gate_never_returns_an_unpopulated_facet_when_a_populated_one_exists(
    split_catalog: Catalog,
) -> None:
    policy = ClarificationPolicy(CONFIGS["V"], split_catalog)

    for over_general in (False, True):
        selected = policy.choose(
            SessionState(asked_attributes=["feature"]),
            _candidates(),
            over_general=over_general,
        )
        assert selected != "material", over_general


def test_gate_falls_back_rather_than_going_silent(barren_catalog: Catalog) -> None:
    """Losing the ability to ask is worse than asking a sparse facet."""
    state = SessionState(asked_attributes=["feature"])

    selected = ClarificationPolicy(CONFIGS["V"], barren_catalog).choose(
        state, _candidates(), over_general=False,
    )

    assert selected in {"material", "color", "other"}


def test_gate_respects_declined_attributes(split_catalog: Catalog) -> None:
    state = SessionState(asked_attributes=["feature"], declined_attributes={"material"})

    selected = ClarificationPolicy(CONFIGS["V"], split_catalog).choose(
        state, _candidates(), over_general=False,
    )

    assert selected == "color"


def test_gate_never_repeats_an_asked_attribute(split_catalog: Catalog) -> None:
    state = SessionState(asked_attributes=["feature", "color"])

    selected = ClarificationPolicy(CONFIGS["V"], split_catalog).choose(
        state, _candidates(), over_general=False,
    )

    assert selected not in {"feature", "color"}


def test_gate_leaves_session_state_unchanged(split_catalog: Catalog) -> None:
    state = SessionState(asked_attributes=["feature"])
    before = (list(state.asked_attributes), set(state.declined_attributes), list(state.slots))

    ClarificationPolicy(CONFIGS["V"], split_catalog).choose(
        state, _candidates(), over_general=False,
    )

    assert (list(state.asked_attributes), set(state.declined_attributes), list(state.slots)) == before


def test_gate_is_inert_without_a_catalog(split_catalog: Catalog) -> None:
    """No catalog means no population evidence, so behavior must match P."""
    state = SessionState(asked_attributes=["feature"])

    gated = ClarificationPolicy(CONFIGS["V"], None).choose(
        state, _candidates(), over_general=False,
    )
    baseline = ClarificationPolicy(CONFIGS["P"], None).choose(
        SessionState(asked_attributes=["feature"]), _candidates(), over_general=False,
    )

    assert gated == baseline

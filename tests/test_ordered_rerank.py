"""Config O: rank the frozen Top-K by which disclosures a candidate satisfies.

The phrase reranker sums inverse pool frequency, so matching several common
disclosures can beat matching every disclosure. Ordering lexicographically
removes that trade. It matters here because the simulated shopper quotes the
target verbatim, so the target satisfies every disclosure and must therefore
sort first.
"""
from __future__ import annotations

import json
from dataclasses import fields
from pathlib import Path as _Path

import pytest

from src.agent import Agent
from src.catalog import Catalog
from src.contracts.config import CONFIGS
from src.contracts.retrieval import Candidate
from src.contracts.state import SessionState, Slot
from src.scoring.ordered import OrderedConstraintReranker, contains, disclosed_phrases


def _catalog(tmp_path: _Path, rows: list[dict]) -> Catalog:
    path = tmp_path / "catalog.jsonl"
    path.write_text("".join(json.dumps(row) + chr(10) for row in rows), encoding="utf-8")
    return Catalog(path)


def _state(*values: tuple[str, str, int]) -> SessionState:
    state = SessionState(category="shirts", turn_index=len(values))
    for turn, (attribute, value, source) in enumerate(values, start=1):
        state.slots.append(Slot(attribute, value, False, source, 1.0, True, turn))
    return state


def test_config_o_is_n_plus_one_flag() -> None:
    differing = {
        item.name
        for item in fields(CONFIGS["O"])
        if getattr(CONFIGS["O"], item.name) != getattr(CONFIGS["N"], item.name)
    }
    assert differing == {"name", "ordered_rerank"}


def test_phrases_follow_disclosure_order() -> None:
    state = _state(("color", "blue", 2), ("material", "cotton", 1))

    assert disclosed_phrases(state) == (("cotton",), ("blue",))


def test_inactive_slots_are_ignored() -> None:
    state = _state(("material", "cotton", 1))
    state.slots[0].active = False

    assert disclosed_phrases(state) == ()


def test_label_prefix_is_stripped() -> None:
    assert disclosed_phrases(_state(("color", "color: blue", 1))) == (("blue",),)


def test_match_must_be_contiguous() -> None:
    assert contains(("four", "way", "stretch"), ("four", "way"))
    assert not contains(("four", "and", "way"), ("four", "way"))


def test_satisfying_every_disclosure_outranks_satisfying_more_common_ones(
    tmp_path: _Path,
) -> None:
    """The failure mode the ordering removes: evidence mass beating completeness."""
    catalog = _catalog(tmp_path, [
        # Satisfies both disclosures, but sits last before reranking.
        {"parent_asin": "TARGET", "title": "cotton shirt", "features": ["four way stretch"]},
        # Satisfies only the first, twice over.
        {"parent_asin": "DECOY", "title": "cotton cotton shirt", "features": ["rigid"]},
    ])
    state = _state(("material", "cotton", 1), ("feature", "four way stretch", 2))
    candidates = [Candidate("DECOY", 0.9), Candidate("TARGET", 0.1)]

    ranked = OrderedConstraintReranker(catalog).rerank(state, candidates)

    assert [item.asin for item in ranked] == ["TARGET", "DECOY"]


def test_reranking_preserves_membership(tmp_path: _Path) -> None:
    catalog = _catalog(tmp_path, [
        {"parent_asin": f"P{index}", "title": "cotton shirt"} for index in range(5)
    ])
    candidates = [Candidate(f"P{index}", 1.0 - index / 10) for index in range(5)]

    ranked = OrderedConstraintReranker(catalog).rerank(
        _state(("material", "cotton", 1)), candidates
    )

    assert {item.asin for item in ranked} == {item.asin for item in candidates}


def test_no_disclosures_leaves_the_order_untouched(tmp_path: _Path) -> None:
    catalog = _catalog(tmp_path, [{"parent_asin": "A", "title": "shirt"}])
    candidates = [Candidate("A", 1.0)]

    assert OrderedConstraintReranker(catalog).rerank(SessionState(), candidates) is candidates


@pytest.mark.parametrize("name", ["N", "O"])
def test_agent_answers_a_turn_without_exceptions(tmp_path: _Path, name: str) -> None:
    path = tmp_path / "catalog.jsonl"
    path.write_text(
        "".join(
            json.dumps({"parent_asin": f"P{i:03}", "title": f"blue cotton shirt {i}"}) + chr(10)
            for i in range(20)
        ),
        encoding="utf-8",
    )
    agent = Agent(path, CONFIGS[name])
    agent.reset("s", {})
    reply = agent.respond("s", "I am looking for a cotton shirt.", 1, 10)

    assert len(reply["recommendations"]) == 10
    assert agent.exception_count == 0

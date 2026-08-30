"""Config N: recommendations are never repeated within a session.

Every asin the agent returns is scored by the evaluator, so a session that
reaches another turn proves none of them was the target. Withholding them
therefore costs no recall. The one exception is an intent override, which the
evaluator refuses to convert before its own turn.
"""
from __future__ import annotations

import json
from dataclasses import fields
from pathlib import Path

import pytest

from src.agent import Agent
from src.contracts.config import CONFIGS
from src.contracts.state import SessionState
from src.parsing import TurnParser
from src.state import apply_parsed_turn, build_retrieval_query

_ROWS = [
    {
        "parent_asin": f"P{index:03}",
        "title": f"blue cotton shirt {index}",
        "features": ["slim fit", "machine washable"],
        "details": {"Material": "Cotton"},
        "categories": ["Clothing", "Shirts"],
        "store": "ExampleStore",
        "description": ["a shirt"],
        "average_rating": 4.0,
        "rating_number": 10 + index,
    }
    for index in range(40)
]


@pytest.fixture()
def catalog_path(tmp_path: Path) -> Path:
    path = tmp_path / "catalog.jsonl"
    path.write_text(
        "".join(json.dumps(row) + chr(10) for row in _ROWS), encoding="utf-8"
    )
    return path


def _turns(agent: Agent, session: str, count: int) -> list[list[str]]:
    agent.reset(session, {})
    seen = []
    for turn in range(1, count + 1):
        reply = agent.respond(session, "I'm looking for a cotton shirt.", turn, 10)
        seen.append([item["parent_asin"] for item in reply["recommendations"]])
    return seen


def test_config_n_is_q_plus_one_flag() -> None:
    differing = {
        item.name
        for item in fields(CONFIGS["N"])
        if getattr(CONFIGS["N"], item.name) != getattr(CONFIGS["Q"], item.name)
    }
    assert differing == {"name", "exclude_shown"}
    assert CONFIGS["N"].exclude_shown is True
    assert CONFIGS["Q"].exclude_shown is False


def test_baseline_repeats_the_same_products_every_turn(catalog_path: Path) -> None:
    agent = Agent(catalog_path, CONFIGS["Q"])
    turns = _turns(agent, "q", 3)

    assert turns[0] == turns[1] == turns[2]
    assert agent._sessions["q"].shown_asins == set()


def test_no_repeat_never_offers_the_same_product_twice(catalog_path: Path) -> None:
    agent = Agent(catalog_path, CONFIGS["N"])
    turns = _turns(agent, "n", 3)

    offered = [asin for turn in turns for asin in turn]
    assert len(offered) == len(set(offered)), "a product was offered twice"
    assert agent._sessions["n"].shown_asins == set(offered)
    assert agent.exception_count == 0


def test_exhausted_pool_falls_back_rather_than_returning_nothing(catalog_path: Path) -> None:
    """The catalog is smaller than ten turns of unique recommendations."""
    agent = Agent(catalog_path, CONFIGS["N"])
    turns = _turns(agent, "n", 10)

    assert all(turn for turn in turns), "a turn returned no recommendations"
    assert agent.exception_count == 0


def test_override_clears_the_memory_so_the_target_is_offerable_again() -> None:
    state = SessionState(category="shirts", turn_index=1)
    state.shown_asins.update({"P001", "P002"})
    parser = TurnParser()

    parsed = parser.parse(
        "Actually, ignore my earlier preference. What I need is: cotton.", 3
    )
    assert parsed.is_override
    apply_parsed_turn(state, parsed, "Actually, ignore my earlier preference.", 3)

    assert state.shown_asins == set()
    assert build_retrieval_query(state).exclude == frozenset()


def test_query_carries_the_exclusion_set() -> None:
    state = SessionState(category="shirts", turn_index=2)
    state.shown_asins.update({"P001", "P002"})

    assert build_retrieval_query(state).exclude == frozenset({"P001", "P002"})

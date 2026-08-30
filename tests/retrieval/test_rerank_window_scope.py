"""Config J: only per-session evidence may decide Top-10 membership."""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from src.agent import Agent
from src.contracts.config import CONFIGS


@pytest.fixture
def popularity_split_catalog(tmp_path: Path) -> Path:
    """The least lexically favoured boot is by far the most reviewed."""
    rows = []
    for index in range(1, 16):
        padding = "" if index <= 10 else " ".join(["filler"] * 40)
        rows.append({
            "parent_asin": f"B{index:04d}",
            "title": "boot",
            "features": ["leather"],
            "description": padding,
            "average_rating": 4.5,
            "rating_number": 100000 if index == 15 else 1,
        })
    path = tmp_path / "catalog.jsonl"
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return path


def _top10(catalog: Path, config: str) -> list[str]:
    # get_run_config falls back to baseline A for an unrecognised name, so an
    # unregistered config here would silently assert against A instead of
    # failing. Refuse that rather than reporting a vacuous pass.
    assert config in CONFIGS, (
        f"config {config} is not registered; get_run_config would fall back to A"
    )
    agent = Agent(catalog, config=config)
    agent.reset("s", {})
    return [r["parent_asin"] for r in agent.respond("s", "boot", 1, 10)["recommendations"]]


def test_a_popularity_prior_alone_must_not_decide_membership(
    popularity_split_catalog: Path,
) -> None:
    """The distinction the architecture turns on.

    Popularity is a population-level prior, not evidence about this shopper,
    and its value was established by reviewing all public sessions. It may
    break ties inside a frozen Top-10; it may not decide who is in it.
    """
    assert "B0015" in _top10(popularity_split_catalog, "Y")
    assert "B0015" not in _top10(popularity_split_catalog, "J")


def test_evidence_scope_still_returns_exactly_top_k(popularity_split_catalog: Path) -> None:
    assert len(_top10(popularity_split_catalog, "J")) == 10


def test_config_j_is_y_with_only_the_window_scope_changed() -> None:
    assert CONFIGS["J"].rerank_window_scope == "evidence"
    assert CONFIGS["Y"].rerank_window_scope == "all"
    assert replace(CONFIGS["J"], name="Y", rerank_window_scope="all") == CONFIGS["Y"]


def test_scope_is_inert_without_a_window() -> None:
    """Existing configs must be untouched however the scope reads."""
    assert CONFIGS["T"].rerank_window == 0
    assert replace(CONFIGS["T"], rerank_window_scope="evidence") != CONFIGS["Y"]

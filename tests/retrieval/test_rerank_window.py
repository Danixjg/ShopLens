"""Config Y: let reranking change Top-10 membership, not just its order."""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from src.agent import Agent, rerank_window_size
from src.contracts.config import CONFIGS


def test_window_defaults_to_the_recommendation_limit() -> None:
    """With the flag off, the rerankers see exactly the frozen Top-K.

    This is what keeps every existing config's Hit Rate@10 unchanged.
    """
    assert rerank_window_size(10, 0) == 10


def test_a_configured_window_widens_what_the_rerankers_may_reorder() -> None:
    assert rerank_window_size(10, 50) == 50


def test_a_window_narrower_than_the_limit_is_clamped_up() -> None:
    """A misconfigured window must never shrink the answer below top_k."""
    assert rerank_window_size(10, 3) == 10


@pytest.fixture
def popularity_split_catalog(tmp_path: Path) -> Path:
    """Fifteen matching boots; the least lexically favoured is the most popular.

    Padding pushes the last products down the BM25 ranking through length
    normalisation, so the popular one starts outside the Top-10 cut.
    """
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
    agent = Agent(catalog, config=config)
    agent.reset("s", {})
    reply = agent.respond("s", "boot", 1, 10)
    return [item["parent_asin"] for item in reply["recommendations"]]


def test_a_widened_window_can_promote_a_product_into_the_top_ten(
    popularity_split_catalog: Path,
) -> None:
    """The behaviour Phase 0 identified as the cap on Hit Rate@10.

    Every reranker currently runs after membership is frozen, so a product
    that loses the cut by a hairline can never be recovered no matter how
    strong its rerank signal.
    """
    baseline = _top10(popularity_split_catalog, "T")
    widened = _top10(popularity_split_catalog, "Y")

    assert "B0015" not in baseline
    assert "B0015" in widened


def test_the_widened_window_still_returns_exactly_top_k(
    popularity_split_catalog: Path,
) -> None:
    assert len(_top10(popularity_split_catalog, "Y")) == 10


def test_config_y_is_t_with_only_the_rerank_window_changed() -> None:
    assert CONFIGS["Y"].rerank_window == 50
    assert CONFIGS["T"].rerank_window == 0
    assert replace(CONFIGS["Y"], name="T", rerank_window=0) == CONFIGS["T"]

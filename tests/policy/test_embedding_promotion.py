from __future__ import annotations

import json
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


def _product(asin: str, text: str) -> dict:
    return {"parent_asin": asin, "title": text, "features": [text], "details": {}}


@pytest.fixture
def material_heavy_catalog(tmp_path: Path) -> Catalog:
    """Two in-Top-K items, plus a near-miss slice (ranks 3-12) whose text is
    saturated with material language and nothing about color."""
    rows = [
        _product("top1", "Comfortable everyday item"),
        _product("top2", "Popular everyday item"),
        *[
            _product(f"miss{i}", "Genuine leather full-grain leather cowhide leather construction")
            for i in range(10)
        ],
    ]
    return _write(tmp_path / "catalog.jsonl", rows)


def _candidates_ranked(catalog: Catalog) -> list[Candidate]:
    # Descending score by insertion order: top1, top2 are in Top-K (limit=2);
    # miss0..miss9 are the near-miss slice.
    return [
        Candidate(product.parent_asin, score)
        for product, score in zip(catalog, range(100, 100 - len(catalog), -1))
    ]


def test_embedding_choice_prefers_the_attribute_matching_the_near_miss_pool(
    material_heavy_catalog: Catalog,
) -> None:
    policy = ClarificationPolicy(CONFIGS["AA"], material_heavy_catalog)
    state = SessionState()

    selected = policy._embedding_choice(
        state, _candidates_ranked(material_heavy_catalog), over_general=True, recommendation_limit=2,
    )

    assert selected == "material"


def test_embedding_choice_returns_none_when_pool_is_not_over_general(
    material_heavy_catalog: Catalog,
) -> None:
    policy = ClarificationPolicy(CONFIGS["AA"], material_heavy_catalog)
    state = SessionState()

    selected = policy._embedding_choice(
        state, _candidates_ranked(material_heavy_catalog), over_general=False, recommendation_limit=2,
    )

    assert selected is None


def test_embedding_choice_skips_asked_and_declined_attributes(
    material_heavy_catalog: Catalog,
) -> None:
    state = SessionState(asked_attributes=["material"], declined_attributes={"color"})
    policy = ClarificationPolicy(CONFIGS["AA"], material_heavy_catalog)

    selected = policy._embedding_choice(
        state, _candidates_ranked(material_heavy_catalog), over_general=True, recommendation_limit=2,
    )

    assert selected not in {"material", "color"}


def test_embedding_choice_falls_back_to_first_candidate_without_a_catalog() -> None:
    """No catalog means no dense retriever to reuse; the mode must still ask
    something deterministic rather than going silent."""
    policy = ClarificationPolicy(CONFIGS["AA"], None)
    state = SessionState()

    selected = policy._embedding_choice(state, [], over_general=True, recommendation_limit=2)

    assert selected == "feature"


def test_embedding_choice_returns_none_once_everything_is_asked_or_declined(
    material_heavy_catalog: Catalog,
) -> None:
    state = SessionState(
        asked_attributes=["feature", "material", "color", "other"],
    )
    policy = ClarificationPolicy(CONFIGS["AA"], material_heavy_catalog)

    selected = policy._embedding_choice(
        state, _candidates_ranked(material_heavy_catalog), over_general=True, recommendation_limit=2,
    )

    assert selected is None


def test_config_aa_is_o_with_only_clarification_mode_changed() -> None:
    from dataclasses import fields, replace

    baseline, embedding = CONFIGS["O"], CONFIGS["AA"]
    differing = {
        field.name
        for field in fields(baseline)
        if getattr(baseline, field.name) != getattr(embedding, field.name)
    }

    assert differing == {"name", "clarification"}
    assert embedding.clarification == "embedding_promotion"
    assert baseline.clarification == "info_gain"
    assert replace(baseline, name="AA", clarification="embedding_promotion") == embedding

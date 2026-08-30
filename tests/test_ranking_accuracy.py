from __future__ import annotations

import json
from math import isclose
from pathlib import Path

from src.catalog import Catalog
from src.contracts.config import CONFIGS
from src.contracts.retrieval import Candidate
from src.contracts.state import SessionState, Slot
from src.policy.clarification import ClarificationPolicy, _information_gain
from src.scoring.phrase import PhraseReranker, _slot_phrases


def _catalog(tmp_path: Path, rows: list[dict]) -> Catalog:
    path = tmp_path / "catalog.jsonl"
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return Catalog(path)


def test_catalog_keeps_bounded_raw_facets_outside_product(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path, [{
        "parent_asin": "A",
        "title": "coat",
        "features": ["Waterproof", "Black cotton shell", "Packable"],
        "details": {"Color": "Blue", "Material": "Wool"},
    }])

    assert catalog.facet_values("A", "feature") == ("waterproof", "packable")
    assert catalog.facet_values("A", "material") == ("cotton", "wool")
    assert catalog.facet_values("A", "color") == ("black", "blue")
    assert not hasattr(catalog.get("A"), "facets")


def test_multiclass_gain_leaves_missing_bucket_unresolved() -> None:
    gain = _information_gain([("x",), ("x",), ("y",), ()])
    assert isclose(gain, 0.5)


def test_over_general_policy_uses_best_full_pool_raw_facet(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path, [
        {"parent_asin": "A", "title": "coat", "details": {"Material": "Cotton"}},
        {"parent_asin": "B", "title": "coat", "details": {"Material": "Cotton"}},
        {"parent_asin": "C", "title": "coat", "details": {"Material": "Wool"}},
        {"parent_asin": "D", "title": "coat", "details": {"Material": "Wool"}},
    ])
    candidates = [Candidate(letter, 1.0) for letter in "ABCD"]

    assert ClarificationPolicy(CONFIGS["E"], catalog).choose(
        SessionState(), candidates, over_general=True,
    ) == "material"


def test_information_policy_uses_other_once_then_targeted_fallback() -> None:
    policy = ClarificationPolicy(CONFIGS["E"])
    state = SessionState()
    assert policy.choose(state, [], over_general=True) == "other"
    state.asked_attributes.append("other")
    assert policy.choose(state, [], over_general=True) == "feature"
    state.asked_attributes.extend(["feature", "material", "color"])
    assert policy.choose(state, [], over_general=True) is None


def test_phrase_rerank_preserves_membership_and_uses_raw_slot_tokens(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path, [
        {"parent_asin": "A", "title": "ordinary coat"},
        {"parent_asin": "B", "title": "the waterproof coat"},
        {"parent_asin": "C", "title": "another coat"},
    ])
    state = SessionState(slots=[Slot("feature", "feature: the waterproof", False, 1, 1.0, True, 1)])
    frozen = [Candidate("A", 10.0), Candidate("B", 9.0)]
    pool = frozen + [Candidate("C", 8.0)]

    assert _slot_phrases(state) == (("the", "waterproof"),)
    result = PhraseReranker(catalog).rerank(state, frozen, pool)

    assert [candidate.asin for candidate in result] == ["B", "A"]
    assert {candidate.asin for candidate in result} == {candidate.asin for candidate in frozen}

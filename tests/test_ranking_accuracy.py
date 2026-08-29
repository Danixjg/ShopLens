from __future__ import annotations

import json
from math import isclose
from pathlib import Path

from src.catalog import Catalog
from src.contracts.config import CONFIGS
from src.contracts.retrieval import Candidate
import pytest

from src.contracts.state import SessionState, Slot, UserProfile
from src.policy.clarification import ClarificationPolicy, _information_gain
from src.scoring.phrase import PhraseReranker, _slot_phrases
from src.scoring.profile import ProfileReranker


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


def _profile_catalog(tmp_path: Path) -> Catalog:
    return _catalog(tmp_path, [
        {"parent_asin": "A", "title": "ordinary coat"},
        {"parent_asin": "B", "title": "comfort coat"},
        {"parent_asin": "C", "title": "another coat"},
    ])


def _profile_state(tags: list[str], slots: list[Slot] | None = None) -> SessionState:
    return SessionState(
        slots=list(slots or []),
        user_profile=UserProfile.from_dict({"preference_tags": tags}),
    )


# Reciprocal-rank scale: adjacent ranks differ by ~0.00026, so a bounded profile
# bonus can break a tie without approaching the constraint penalty scale.
_RANK_1 = 1.0 / 61.0
_RANK_2 = 1.0 / 62.0


def test_profile_rerank_breaks_ties_without_changing_membership(tmp_path: Path) -> None:
    catalog = _profile_catalog(tmp_path)
    state = _profile_state(["comfort"])
    frozen = [Candidate("A", _RANK_1), Candidate("B", _RANK_2)]
    pool = frozen + [Candidate("C", 0.015)]

    result = ProfileReranker(catalog).rerank(state, frozen, pool)

    assert [candidate.asin for candidate in result] == ["B", "A"]
    assert {candidate.asin for candidate in result} == {"A", "B"}


def test_disclosed_constraint_supersedes_the_matching_profile_tag(tmp_path: Path) -> None:
    catalog = _profile_catalog(tmp_path)
    # "comfort" classifies as a feature; an active feature slot means the
    # shopper has spoken, so the standing prior must not re-weight it.
    disclosed = Slot("feature", "feature: waterproof", False, 1, 1.0, True, 1)
    state = _profile_state(["comfort"], [disclosed])
    frozen = [Candidate("A", _RANK_1), Candidate("B", _RANK_2)]
    pool = frozen + [Candidate("C", 0.015)]

    result = ProfileReranker(catalog).rerank(state, frozen, pool)

    assert [candidate.asin for candidate in result] == ["A", "B"]


def test_profile_never_promotes_a_hard_constraint_violator(tmp_path: Path) -> None:
    catalog = _profile_catalog(tmp_path)
    state = _profile_state(["comfort"])
    # B matches the tag but violates a disclosed requirement, so it earns
    # nothing and keeps its place.
    frozen = [
        Candidate("A", _RANK_1),
        Candidate("B", _RANK_2, {"hard_material": -4.0}),
    ]
    pool = frozen + [Candidate("C", 0.015)]

    result = ProfileReranker(catalog).rerank(state, frozen, pool)

    assert [candidate.asin for candidate in result] == ["A", "B"]


def test_absent_or_empty_profile_is_a_no_op(tmp_path: Path) -> None:
    catalog = _profile_catalog(tmp_path)
    frozen = [Candidate("A", _RANK_1), Candidate("B", _RANK_2)]
    pool = list(frozen)
    reranker = ProfileReranker(catalog)

    assert reranker.rerank(SessionState(), frozen, pool) == frozen
    assert reranker.rerank(_profile_state([]), frozen, pool) == frozen


def test_profile_rerank_weight_must_come_from_the_declared_grid(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        ProfileReranker(_profile_catalog(tmp_path), weight=0.5)

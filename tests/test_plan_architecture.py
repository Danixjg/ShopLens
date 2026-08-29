from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

import pytest

import src.agent as agent_module
from agent import Agent as SubmissionAgent
from src.catalog import OFFICIAL_CATALOG_SHA256, Catalog
from src.contracts.config import CONFIGS, get_run_config
from src.contracts.response import AgentReply, Recommendation, Usage
from src.contracts.retrieval import Candidate, RetrievalQuery
from src.contracts.state import SessionState
from src.eval.runner import (
    REFERENCE_REQUIREMENTS,
    _capability_status,
    _lock_entries,
    _locked_environment_snapshot,
)
from src.eval.split import stratified_dev_holdout_split
from src.parsing import OVERRIDE_MARKER, TurnParser
from src.policy import ClarificationPolicy
from src.retrieval import HybridRetriever
from src.retrieval.dense import model_tree_sha256
from src.scoring import ConstraintScorer, DynamicWeightScorer
from src.state import apply_parsed_turn, build_retrieval_query
from starter.agent import Agent as EvaluatorAgent


ROWS = [
    {"parent_asin": "A", "title": "Black leather boot", "features": ["waterproof"], "categories": ["Shoes"]},
    {"parent_asin": "B", "title": "Brown cotton shirt", "features": ["soft"], "categories": ["Shirts"]},
    {"parent_asin": "C", "title": "Blue polyester jacket", "features": ["packable"], "categories": ["Jackets"]},
]


@pytest.fixture()
def catalog_path(tmp_path: Path) -> Path:
    path = tmp_path / "catalog.jsonl"
    path.write_text("".join(json.dumps(row) + "\n" for row in ROWS), encoding="utf-8")
    return path


def test_entry_points_are_the_same_implementation() -> None:
    assert SubmissionAgent is EvaluatorAgent


def test_unknown_config_falls_back_to_a() -> None:
    assert get_run_config("typo") is CONFIGS["A"]


def test_agent_defaults_to_reproducible_baseline(catalog_path: Path) -> None:
    assert SubmissionAgent(catalog_path).config is CONFIGS["A"]


def test_environment_can_select_hybrid_config(
    catalog_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SHOPLENS_CONFIG", "C")
    assert SubmissionAgent(catalog_path).config is CONFIGS["C"]


def test_ablation_matrix_has_exact_names() -> None:
    assert set(CONFIGS) == set("ABCDEFGHPQRZ")


def test_config_z_is_the_only_no_clarification_diagnostic() -> None:
    assert CONFIGS["Z"].clarification == "off"
    assert all(CONFIGS[name].clarification != "off" for name in "ABCDEFGH")


def test_catalog_checksum_is_verified(catalog_path: Path) -> None:
    expected = hashlib.sha256(catalog_path.read_bytes()).hexdigest()
    assert len(Catalog(catalog_path, expected_sha256=expected)) == 3
    with pytest.raises(ValueError, match="checksum mismatch"):
        Catalog(catalog_path, expected_sha256="0" * 64)


def test_default_catalog_path_is_repository_anchored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    official = tmp_path / "official" / "catalog.jsonl"
    official.parent.mkdir()
    official.write_text(json.dumps(ROWS[0]) + "\n", encoding="utf-8")
    official_digest = hashlib.sha256(official.read_bytes()).hexdigest()
    data = tmp_path / "data"
    data.mkdir()
    path = data / "catalog.jsonl"
    path.write_text(json.dumps(ROWS[1]) + "\n", encoding="utf-8")
    monkeypatch.setattr(agent_module, "OFFICIAL_CATALOG_PATH", official)
    monkeypatch.setattr(agent_module, "OFFICIAL_CATALOG_SHA256", official_digest)
    monkeypatch.chdir(tmp_path)
    assert SubmissionAgent().catalog.path == official.resolve()


def test_explicit_checksum_override_is_a_hard_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "custom-catalog.jsonl"
    path.write_text(json.dumps(ROWS[0]) + "\n", encoding="utf-8")
    monkeypatch.setenv("SHOPLENS_CATALOG_SHA256", "0" * 64)
    with pytest.raises(ValueError, match="checksum mismatch"):
        SubmissionAgent(path)


def test_default_catalog_checksum_has_expected_release_value() -> None:
    assert OFFICIAL_CATALOG_SHA256 == (
        "da979b05a68af864cb0dcf9ee6a81c010c7e66a57978ad286c7a2e005fc69a67"
    )


def test_catalog_rejects_duplicate_identifiers(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.jsonl"
    path.write_text(json.dumps(ROWS[0]) + "\n" + json.dumps(ROWS[0]) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        Catalog(path)


def test_dense_model_fingerprint_covers_runtime_files(tmp_path: Path) -> None:
    model = tmp_path / "model"
    model.mkdir()
    (model / "model.safetensors").write_bytes(b"weights")
    config = model / "config.json"
    config.write_text('{"version": 1}', encoding="utf-8")
    before = model_tree_sha256(model)
    config.write_text('{"version": 2}', encoding="utf-8")
    assert model_tree_sha256(model) != before


def test_response_serialization_has_no_additional_properties() -> None:
    result = AgentReply("ok", "feature", [Recommendation("A")], Usage()).to_dict()
    assert set(result) == {"message", "ask_attribute", "recommendations", "usage"}
    assert set(result["recommendations"][0]) == {"parent_asin"}
    assert set(result["usage"]) == {"prompt_tokens", "completion_tokens"}


def test_parser_recognizes_buying_template() -> None:
    parsed = TurnParser().parse("I'm looking for Shoes. A key requirement is: leather.", 1)
    assert parsed.intent == "buying"
    assert parsed.category == "Shoes"
    assert parsed.hard_constraints == (("material", "leather"),)


def test_parser_recognizes_override() -> None:
    parsed = TurnParser().parse(f"{OVERRIDE_MARKER} brown.", 3)
    assert parsed.is_override
    assert parsed.hard_constraints == (("feature", "brown"),)


def test_parser_routes_override_scenario_on_first_message() -> None:
    parsed = TurnParser().parse("I'm looking for Boots. I prefer a relaxed fit.", 1)
    assert parsed.intent == "intent_override"


def test_parser_keeps_negative_and_control_responses_out_of_retrieval() -> None:
    parser = TurnParser()
    boundary = parser.parse("I don't have a preference for feature; please use your judgment.", 2)
    ordinary = parser.parse("I don't have an additional preference for feature.", 2)
    control = parser.parse(
        "Those options are not quite right yet. Ask me about one specific attribute.", 2,
    )
    assert boundary.declined_attribute == "feature"
    assert ordinary.declined_attribute == "feature"
    assert boundary.soft_preferences == ordinary.soft_preferences == ()
    assert control.declined_attribute is None
    assert control.soft_preferences == ()
    assert boundary.soft_preferences == ()


def test_runner_rejects_unavailable_requested_capability(catalog_path: Path) -> None:
    agent = SubmissionAgent(catalog_path, config=CONFIGS["G"])
    status, reasons = _capability_status(agent)
    assert status["reranker"]["ready"] is False
    assert "requested local cross-encoder is unavailable" in reasons


def test_agent_counts_guarded_response_failures(
    catalog_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    agent = SubmissionAgent(catalog_path)
    agent.reset("session", {})

    def fail(*args: object, **kwargs: object) -> dict:
        raise RuntimeError("synthetic failure")

    monkeypatch.setattr(agent, "_respond", fail)
    reply = agent.respond("session", "boots", 1, 10)
    assert reply["recommendations"]
    assert agent.exception_count == 1
    status, reasons = _capability_status(agent)
    assert status["agent_exception_count"] == 1
    assert reasons == ["agent fallback handled 1 unexpected exception(s)"]


def test_clarification_reply_preserves_buying_route() -> None:
    parser = TurnParser()
    state = SessionState()
    first = parser.parse("I'm looking for Boots. A key requirement is: leather.", 1)
    apply_parsed_turn(state, first, "first", 1)
    reply = parser.parse("For that, what matters is: waterproof.", 2)
    apply_parsed_turn(state, reply, "reply", 2)
    assert state.intent == "buying"


def test_hybrid_intent_route_uses_lexical_for_buying_only() -> None:
    class RecordingRetriever:
        def __init__(self, asin: str) -> None:
            self.asin = asin
            self.calls = 0

        def search(self, query: RetrievalQuery, k: int) -> list[Candidate]:
            self.calls += 1
            return [Candidate(self.asin, 1.0)]

    lexical = RecordingRetriever("lexical")
    dense = RecordingRetriever("dense")
    retriever = HybridRetriever(lexical, dense)
    query = RetrievalQuery("boots")
    assert retriever.search_for_intent(query, 10, "buying")[0].asin == "lexical"
    assert dense.calls == 1
    retriever.search_for_intent(query, 10, "browsing")
    assert dense.calls == 2


def test_override_deactivates_old_soft_slot() -> None:
    parser = TurnParser()
    state = SessionState()
    initial = parser.parse("I'm looking for Boots. color: black", 1)
    apply_parsed_turn(state, initial, "initial", 1)
    override = parser.parse(f"{OVERRIDE_MARKER} color: brown.", 3)
    apply_parsed_turn(state, override, "override", 3)
    query = build_retrieval_query(state)
    assert "brown" in query.text
    assert "black" not in query.text


def test_override_keeps_later_disclosed_constraints() -> None:
    parser = TurnParser()
    state = SessionState()
    initial = parser.parse("I'm looking for Boots. black", 1)
    apply_parsed_turn(state, initial, "initial", 1)
    disclosed = parser.parse("For that, what matters is: waterproof.", 2)
    apply_parsed_turn(state, disclosed, "disclosed", 2)
    override = parser.parse(f"{OVERRIDE_MARKER} leather.", 3)
    apply_parsed_turn(state, override, "override", 3)
    query = build_retrieval_query(state)
    assert "black" not in query.text
    assert "waterproof" in query.text
    assert "leather" in query.text


def test_override_promotes_a_value_already_volunteered_as_a_preference() -> None:
    parser = TurnParser()
    state = SessionState()
    apply_parsed_turn(state, parser.parse("I'm looking for Boots. old style", 1), "initial", 1)
    apply_parsed_turn(
        state, parser.parse("For that, what matters is: leather; waterproof.", 2), "disclosed", 2,
    )
    apply_parsed_turn(state, parser.parse(f"{OVERRIDE_MARKER} leather.", 3), "override", 3)
    query = build_retrieval_query(state)
    assert ("material", "leather") in query.hard
    assert ("material", "leather") not in query.soft
    assert ("feature", "waterproof") in query.soft


def test_override_does_not_erase_later_constraint_in_same_bucket() -> None:
    parser = TurnParser()
    state = SessionState()
    initial = parser.parse("I'm looking for Boots. cushioned", 1)
    apply_parsed_turn(state, initial, "initial", 1)
    disclosed = parser.parse("For that, what matters is: waterproof.", 2)
    apply_parsed_turn(state, disclosed, "disclosed", 2)
    override = parser.parse(f"{OVERRIDE_MARKER} leather.", 3)
    apply_parsed_turn(state, override, "override", 3)
    query = build_retrieval_query(state)
    assert "cushioned" not in query.text
    assert "waterproof" in query.text
    assert "leather" in query.text


def test_category_change_clears_soft_but_preserves_hard() -> None:
    parser = TurnParser()
    state = SessionState()
    first = parser.parse("I'm looking for Boots. A key requirement is: leather.", 1)
    apply_parsed_turn(state, first, "first", 1)
    state.slots.append(type(state.slots[0])("color", "black", False, 1, .75, True, 1))
    changed = parser.parse("I'm looking for Jackets, but I'm still exploring.", 2)
    apply_parsed_turn(state, changed, "changed", 2)
    query = build_retrieval_query(state)
    assert query.category == "Jackets"
    assert query.hard == (("material", "leather"),)
    assert "black" not in query.text


def test_query_builder_passes_hard_constraint_without_filtering() -> None:
    parser = TurnParser()
    state = SessionState()
    parsed = parser.parse("I'm looking for Boots. A key requirement is: leather.", 1)
    apply_parsed_turn(state, parsed, "message", 1)
    assert build_retrieval_query(state).hard == (("material", "leather"),)


def test_constraint_scorer_penalizes_but_keeps_mismatch(catalog_path: Path) -> None:
    scorer = ConstraintScorer(Catalog(catalog_path))
    query = RetrievalQuery("boots leather", hard=(("material", "leather"),))
    result = scorer.score([Candidate("A", 0.0), Candidate("B", 0.0)], query)
    assert {item.asin for item in result} == {"A", "B"}
    assert result[0].asin == "A"


def test_constraint_scorer_ignores_evaluator_attribute_label(catalog_path: Path) -> None:
    scorer = ConstraintScorer(Catalog(catalog_path))
    query = RetrievalQuery("black", hard=(("color", "color: black"),))
    result = scorer.score([Candidate("A", 0.0)], query)
    assert result[0].components["hard_color"] == 1.5


def test_material_penalty_is_stronger_than_color(catalog_path: Path) -> None:
    scorer = ConstraintScorer(Catalog(catalog_path))
    material = scorer.score([Candidate("B", 0.0)], RetrievalQuery("leather", hard=(("material", "leather"),)))[0]
    color = scorer.score([Candidate("B", 0.0)], RetrievalQuery("blue", hard=(("color", "blue"),)))[0]
    assert material.score < color.score


def test_dynamic_route_emphasizes_hard_components_for_buying() -> None:
    candidate = Candidate("A", 1.0, {"hard_material_0": 2.0, "soft_style_0": 1.0})
    scorer = DynamicWeightScorer()
    buying = scorer.score([candidate], "buying")[0]
    browsing = scorer.score([candidate], "browsing")[0]
    assert buying.score > browsing.score


def test_boundary_policy_excludes_only_the_declined_attribute() -> None:
    state = SessionState(declined_attributes={"feature"})
    assert ClarificationPolicy(CONFIGS["E"]).choose(state, []) == "other"


def test_declined_open_question_is_persistently_ineligible() -> None:
    policy = ClarificationPolicy(CONFIGS["E"])
    refused = SessionState(declined_attributes={"other"})
    assert policy.choose(refused, []) == "feature"


def test_declined_open_question_does_not_return_later() -> None:
    policy = ClarificationPolicy(CONFIGS["E"])
    later = SessionState(
        asked_attributes=["feature", "material", "color"],
        declined_attributes={"other"},
    )
    assert policy.choose(later, []) is None


def test_fixed_clarification_retains_measured_priority() -> None:
    state = SessionState()
    policy = ClarificationPolicy(CONFIGS["A"])
    assert policy.choose(state, []) == "feature"
    state.asked_attributes.extend(["feature", "material"])
    assert policy.choose(state, []) == "color"


def test_information_policy_asks_openly_without_a_discriminating_facet() -> None:
    policy = ClarificationPolicy(CONFIGS["E"])
    assert policy.choose(SessionState(), []) == "other"


def test_information_policy_skips_facets_already_covered_by_a_slot() -> None:
    parser = TurnParser()
    state = SessionState()
    apply_parsed_turn(
        state, parser.parse("I'm looking for Boots. A key requirement is: leather.", 1), "m", 1,
    )
    assert "material" in ClarificationPolicy._covered(state)


def test_same_attribute_disclosures_accumulate_instead_of_replacing() -> None:
    parser = TurnParser()
    state = SessionState()
    parsed = parser.parse(
        "For that, what matters is: waterproof construction; removable footbed.", 2,
    )
    assert len(parsed.soft_preferences) == 2
    apply_parsed_turn(state, parsed, "disclosed", 2)
    query = build_retrieval_query(state)
    assert "waterproof construction" in query.text
    assert "removable footbed" in query.text
    assert len(query.soft) == 2


def test_repeated_identical_disclosure_does_not_duplicate_a_slot() -> None:
    parser = TurnParser()
    state = SessionState()
    for turn in (2, 3):
        apply_parsed_turn(
            state, parser.parse("For that, what matters is: waterproof.", turn), "d", turn,
        )
    assert len([slot for slot in state.slots if slot.active]) == 1


def test_open_question_is_never_repeated() -> None:
    state = SessionState(asked_attributes=["feature", "material", "color", "other"])
    policy = ClarificationPolicy(CONFIGS["E"])
    assert policy.choose(state, []) is None


def test_fixed_clarification_uses_other_only_once() -> None:
    state = SessionState(asked_attributes=["feature", "material", "color"])
    policy = ClarificationPolicy(CONFIGS["A"])
    assert policy.choose(state, []) == "other"
    state.asked_attributes.append("other")
    assert policy.choose(state, []) is None


def test_over_generality_changes_guidance_without_suppressing_recommendations() -> None:
    candidates = [Candidate(str(index), 1.0) for index in range(11)]
    policy = ClarificationPolicy(CONFIGS["E"])
    assert policy.is_over_general(candidates, 10)
    assert policy.message("feature", over_general=True).startswith(
        "I found many plausible matches."
    )


def test_parser_classifier_matches_evaluator_bucket_rules() -> None:
    parser = TurnParser()
    assert parser.parse("brown", 1).soft_preferences == (("feature", "brown"),)
    assert parser.parse("suede", 1).soft_preferences == (("feature", "suede"),)


def test_turn_ten_never_returns_empty(catalog_path: Path) -> None:
    agent = SubmissionAgent(catalog_path)
    agent.reset("s", {})
    response = agent.respond("s", "", 10, 10)
    assert response["recommendations"]


def test_internal_exception_degrades_to_populated_response(catalog_path: Path) -> None:
    agent = SubmissionAgent(catalog_path)
    agent.reset("s", {})
    agent.retriever.search = lambda query, k: (_ for _ in ()).throw(RuntimeError("boom"))  # type: ignore[method-assign]
    response = agent.respond("s", "boots", 1, 10)
    assert response["recommendations"]
    assert isinstance(response["message"], str)


def test_empty_search_relaxes_to_category_before_global_fallback(catalog_path: Path) -> None:
    agent = SubmissionAgent(catalog_path, config="C")
    agent.reset("s", {})
    calls: list[str] = []

    def search(query: RetrievalQuery, k: int) -> list[Candidate]:
        calls.append(query.text)
        return [] if len(calls) == 1 else [Candidate("A", 1.0)]

    agent.retriever.search = search  # type: ignore[method-assign]
    response = agent.respond(
        "s", "I'm looking for Shoes. A key requirement is: leather.", 1, 10,
    )
    assert len(calls) == 2
    assert calls[1] == "Shoes"
    assert response["recommendations"][0]["parent_asin"] == "A"


def test_stratified_split_is_120_80_with_fixed_scenario_counts() -> None:
    counts = {"buying": 80, "browsing": 80, "intent_override": 30, "boundary": 10}
    samples = [
        {"sample_id": f"{scenario}-{index}", "scenario_type": scenario}
        for scenario, count in counts.items() for index in range(count)
    ]
    dev, holdout = stratified_dev_holdout_split(samples)
    assert (len(dev), len(holdout)) == (120, 80)
    assert Counter(item["scenario_type"] for item in dev) == {
        "buying": 48, "browsing": 48, "intent_override": 18, "boundary": 6,
    }


def test_split_is_deterministic() -> None:
    samples = [{"sample_id": str(i), "scenario_type": "buying"} for i in range(20)]
    assert stratified_dev_holdout_split(samples) == stratified_dev_holdout_split(samples)


def test_lock_entries_join_hash_continuations_and_drop_comments() -> None:
    text = (
        "# header\n"
        "alpha==1.0 \\\n"
        f"    --hash=sha256:{'0' * 64} \\\n"
        f"    --hash=sha256:{'1' * 64}\n"
        "    # via beta\n"
        "beta==2.0 \\\n"
        f"    --hash=sha256:{'2' * 64}\n"
    )
    entries = _lock_entries(text)
    assert len(entries) == 2
    assert entries[0].startswith("alpha==1.0 --hash=sha256:")
    assert entries[0].count("--hash=") == 2
    assert entries[1] == f"beta==2.0 --hash=sha256:{'2' * 64}"


def test_version_only_lock_entry_is_rejected_as_not_hash_pinned(tmp_path: Path) -> None:
    path = tmp_path / "plain.txt"
    path.write_text("numpy==2.5.2\n", encoding="utf-8")
    _digest, mismatches = _locked_environment_snapshot(path)
    assert mismatches == ["numpy: lock entry is not hash-pinned"]


def test_reference_lock_is_hash_pinned_and_matches_environment() -> None:
    pytest.importorskip("torch")
    digest, mismatches = _locked_environment_snapshot(REFERENCE_REQUIREMENTS)
    assert digest is not None
    assert mismatches == []

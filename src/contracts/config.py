from __future__ import annotations

import os
from dataclasses import dataclass, replace
from typing import Literal


RetrievalMode = Literal["bm25", "dense", "hybrid"]
ClarificationMode = Literal["off", "empty_result_only", "info_gain", "expected_value"]
RerankerMode = Literal["none", "local_cross_encoder"]
# What the dense encoder indexes. "full" is the historical flat concatenation;
# "compact" keeps only the fields the BM25 index already weights highest.
DenseTextRecipe = Literal["full", "compact"]
# Which signals a widened rerank window exposes. "all" is the historical
# behaviour, where every reranker sees the window and may therefore decide
# Top-K membership. "evidence" freezes membership once the disclosure-derived
# rerankers have run, so the population-level priors may only reorder inside it.
RerankWindowScope = Literal["all", "evidence"]

HIT_RATE_WEIGHT = 0.50
MRR_WEIGHT = 0.30
EFFICIENCY_WEIGHT = 0.20
MISS_TURN_VALUE = 11
MAX_TURNS = 10
# Selected once on the 120-session dev split. The public holdout is not used
# to revise this value.
POPULARITY_RERANK_WEIGHT = 0.15
# Selected once on the 120-session dev split. The public holdout is not used
# to revise this value.
PROFILE_RERANK_WEIGHT = 0.05


@dataclass(frozen=True, slots=True)
class RunConfig:
    name: str = "A"
    retrieval_mode: RetrievalMode = "bm25"
    constraint_scoring: bool = False
    clarification: ClarificationMode = "empty_result_only"
    session_memory: bool = False
    dynamic_weights: bool = False
    reranker: RerankerMode = "none"
    llm_rank: bool = False
    phrase_rerank: bool = False
    popularity_rerank: bool = False
    symmetric_intent_routing: bool = False
    profile_rerank: bool = False
    facet_population_gate: bool = False
    exclude_shown: bool = False
    ordered_rerank: bool = False
    # Resolve a disclosure against known catalog field values rather than
    # splitting on every semicolon. Catalog text uses ";" as punctuation, so
    # the separator is not reserved and one value can look like several.
    catalog_grounded_segmentation: bool = False
    popularity_rerank_weight: float = 0.0
    profile_rerank_weight: float = 0.0
    dense_text_recipe: DenseTextRecipe = "full"
    negative_preference: bool = False
    # Candidates handed to the rerankers before truncation. 0 keeps Top-K
    # membership frozen, which is the historical behaviour.
    rerank_window: int = 0
    # Which rerankers the widened window reaches. Inert while rerank_window is
    # 0, because membership is already frozen at the recommendation limit.
    rerank_window_scope: RerankWindowScope = "all"
    # Extends the clarification policy's fixed attribute sequence beyond
    # feature/material/color. Only reached once that sequence and "other" are
    # exhausted, so it changes nothing before then.
    extended_clarification: bool = False
    # Excludes an attribute already covered by an active disclosed slot from
    # the clarification policy's candidate set, the same way an already-asked
    # or already-declined attribute is excluded. ClarificationPolicy._covered
    # computes this set already; this flag is what makes choose() consult it.
    skip_covered_attributes: bool = False


_A = RunConfig()
CONFIGS: dict[str, RunConfig] = {
    "A": _A,
    "B": replace(_A, name="B", retrieval_mode="hybrid"),
    "C": replace(_A, name="C", retrieval_mode="hybrid", constraint_scoring=True, session_memory=True),
    "D": replace(_A, name="D", retrieval_mode="hybrid", constraint_scoring=True, session_memory=False),
    "E": replace(_A, name="E", retrieval_mode="hybrid", constraint_scoring=True, session_memory=True, clarification="info_gain"),
    "F": replace(_A, name="F", retrieval_mode="hybrid", constraint_scoring=True, session_memory=True, clarification="info_gain", dynamic_weights=True),
    "G": replace(_A, name="G", retrieval_mode="hybrid", constraint_scoring=True, session_memory=True, clarification="info_gain", dynamic_weights=True, reranker="local_cross_encoder"),
    "H": replace(_A, name="H", retrieval_mode="hybrid", constraint_scoring=True, session_memory=True, clarification="info_gain", dynamic_weights=True, reranker="local_cross_encoder", llm_rank=True),
    "P": replace(_A, name="P", retrieval_mode="hybrid", constraint_scoring=True, session_memory=True, clarification="info_gain", dynamic_weights=True, phrase_rerank=True),
    "Q": replace(
        _A,
        name="Q",
        retrieval_mode="hybrid",
        constraint_scoring=True,
        session_memory=True,
        clarification="info_gain",
        dynamic_weights=True,
        phrase_rerank=True,
        popularity_rerank=True,
        popularity_rerank_weight=POPULARITY_RERANK_WEIGHT,
    ),
    "R": replace(
        _A,
        name="R",
        retrieval_mode="hybrid",
        constraint_scoring=True,
        session_memory=True,
        clarification="info_gain",
        dynamic_weights=True,
        phrase_rerank=True,
        symmetric_intent_routing=True,
    ),
    "S": replace(
        _A,
        name="S",
        retrieval_mode="hybrid",
        constraint_scoring=True,
        session_memory=True,
        clarification="info_gain",
        dynamic_weights=True,
        phrase_rerank=True,
        profile_rerank=True,
        profile_rerank_weight=PROFILE_RERANK_WEIGHT,
    ),
    # Every component below independently passed the dev + holdout + per-scenario
    # retention gate against P. T measures whether they compose; it is retained
    # only if the combination also clears that gate.
    "T": replace(
        _A,
        name="T",
        retrieval_mode="hybrid",
        constraint_scoring=True,
        session_memory=True,
        clarification="info_gain",
        dynamic_weights=True,
        phrase_rerank=True,
        symmetric_intent_routing=True,
        profile_rerank=True,
        profile_rerank_weight=PROFILE_RERANK_WEIGHT,
        popularity_rerank=True,
        popularity_rerank_weight=POPULARITY_RERANK_WEIGHT,
    ),
    # Research-derived ablation: P with only the clarification question-value
    # policy changed. It remains experimental until its dev gate is frozen and
    # a single holdout run is recorded.
    "U": replace(
        _A,
        name="U",
        retrieval_mode="hybrid",
        constraint_scoring=True,
        session_memory=True,
        clarification="expected_value",
        dynamic_weights=True,
        phrase_rerank=True,
    ),
    # Research-derived ablation: P with only clarification facet eligibility
    # changed, so an unanswerable facet is not spent on a turn. It remains
    # experimental until its dev gate is run and recorded.
    "V": replace(
        _A,
        name="V",
        retrieval_mode="hybrid",
        constraint_scoring=True,
        session_memory=True,
        clarification="info_gain",
        dynamic_weights=True,
        phrase_rerank=True,
        facet_population_gate=True,
    ),
    # Research-derived ablation: T with only the dense encoder's input text
    # changed. The lexical index already weights title, categories and features
    # highest and the low-weight tails overflow the encoder's 256 word-piece
    # window, so this measures whether the dense half was being diluted.
    "W": replace(
        _A,
        name="W",
        retrieval_mode="hybrid",
        constraint_scoring=True,
        session_memory=True,
        clarification="info_gain",
        dynamic_weights=True,
        phrase_rerank=True,
        symmetric_intent_routing=True,
        profile_rerank=True,
        profile_rerank_weight=PROFILE_RERANK_WEIGHT,
        popularity_rerank=True,
        popularity_rerank_weight=POPULARITY_RERANK_WEIGHT,
        dense_text_recipe="compact",
    ),
    # Research-derived ablation: T with only overridden-preference exclusion
    # added. A value the shopper replaces is rejected information; without this
    # the retrieval seam cannot tell it from a value never mentioned.
    "X": replace(
        _A,
        name="X",
        retrieval_mode="hybrid",
        constraint_scoring=True,
        session_memory=True,
        clarification="info_gain",
        dynamic_weights=True,
        phrase_rerank=True,
        symmetric_intent_routing=True,
        profile_rerank=True,
        profile_rerank_weight=PROFILE_RERANK_WEIGHT,
        popularity_rerank=True,
        popularity_rerank_weight=POPULARITY_RERANK_WEIGHT,
        negative_preference=True,
    ),
    # Research-derived ablation: T with only the rerank window widened, so the
    # existing rerankers may decide Top-10 membership instead of only its order.
    # Phase 0 measured three dev misses within 0.002 of the tenth-place score,
    # which no post-truncation reranker could ever reach.
    "Y": replace(
        _A,
        name="Y",
        retrieval_mode="hybrid",
        constraint_scoring=True,
        session_memory=True,
        clarification="info_gain",
        dynamic_weights=True,
        phrase_rerank=True,
        symmetric_intent_routing=True,
        profile_rerank=True,
        profile_rerank_weight=PROFILE_RERANK_WEIGHT,
        popularity_rerank=True,
        popularity_rerank_weight=POPULARITY_RERANK_WEIGHT,
        rerank_window=50,
    ),
    # Research-derived ablation: Y with only the widened window's scope
    # narrowed. Popularity and profile are population-level priors whose values
    # were fitted across sessions, not evidence about this shopper; they may
    # break ties inside a frozen Top-K but may not decide who is in it.
    "J": replace(
        _A,
        name="J",
        retrieval_mode="hybrid",
        constraint_scoring=True,
        session_memory=True,
        clarification="info_gain",
        dynamic_weights=True,
        phrase_rerank=True,
        symmetric_intent_routing=True,
        profile_rerank=True,
        profile_rerank_weight=PROFILE_RERANK_WEIGHT,
        popularity_rerank=True,
        popularity_rerank_weight=POPULARITY_RERANK_WEIGHT,
        rerank_window=50,
        rerank_window_scope="evidence",
    ),
    # Q plus no-repeat recommendations. Every asin returned is scored, so a turn
    # that did not end the session proves none of them was the target; they are
    # withheld from later turns instead of being offered again. An intent
    # override clears that memory, because a hit cannot register before the
    # override turn and those candidates were therefore never tested.
    "N": replace(
        _A,
        name="N",
        retrieval_mode="hybrid",
        constraint_scoring=True,
        session_memory=True,
        clarification="info_gain",
        dynamic_weights=True,
        phrase_rerank=True,
        popularity_rerank=True,
        popularity_rerank_weight=POPULARITY_RERANK_WEIGHT,
        exclude_shown=True,
    ),
    # N with the phrase reranker replaced by disclosure-order ranking, so a
    # candidate satisfying more of what the shopper said always outranks one
    # satisfying fewer, rather than more inverse-frequency evidence winning.
    "O": replace(
        _A,
        name="O",
        retrieval_mode="hybrid",
        constraint_scoring=True,
        session_memory=True,
        clarification="info_gain",
        dynamic_weights=True,
        phrase_rerank=True,
        popularity_rerank=True,
        popularity_rerank_weight=POPULARITY_RERANK_WEIGHT,
        exclude_shown=True,
        ordered_rerank=True,
    ),
    # O with catalog-grounded disclosure segmentation. A feature bullet that
    # contains a semicolon currently becomes several slots, which inflates the
    # ordered-rerank match vector and dilutes the soft-term union that scores
    # it. Isolating the flag keeps the effect measurable against O.
    "K": replace(
        _A,
        name="K",
        retrieval_mode="hybrid",
        constraint_scoring=True,
        session_memory=True,
        clarification="info_gain",
        dynamic_weights=True,
        phrase_rerank=True,
        popularity_rerank=True,
        popularity_rerank_weight=POPULARITY_RERANK_WEIGHT,
        exclude_shown=True,
        ordered_rerank=True,
        catalog_grounded_segmentation=True,
    ),
    "Z": replace(_A, name="Z", clarification="off"),
    # Research-derived ablation: O with the clarification policy's fixed
    # attribute sequence extended by "budget" only, reached once
    # feature/material/color/other are exhausted. 178/200 public-set target
    # products carry a usable price (materialize_hidden_fields derives a
    # budget soft preference only then), so a shopper can usually answer it,
    # even though catalog-wide price coverage is much sparser. It remains
    # experimental until its dev gate is run and recorded.
    "K": replace(
        _A,
        name="K",
        retrieval_mode="hybrid",
        constraint_scoring=True,
        session_memory=True,
        clarification="info_gain",
        dynamic_weights=True,
        phrase_rerank=True,
        popularity_rerank=True,
        popularity_rerank_weight=POPULARITY_RERANK_WEIGHT,
        exclude_shown=True,
        ordered_rerank=True,
        extended_clarification=True,
    ),
    # Research-derived ablation: O with the clarification policy excluding an
    # attribute already covered by an active disclosed slot from what it will
    # ask about next, the same way an already-asked or already-declined
    # attribute is excluded. Probe evidence (2026-08-31 session) found a
    # session that discloses feature, material, and color in its opening
    # message still gets asked "Do you have a feature preference?" -- state
    # tracking registers the disclosure correctly, but the clarification
    # policy never consults it. It remains experimental until its dev gate is
    # run and recorded.
    "L": replace(
        _A,
        name="L",
        retrieval_mode="hybrid",
        constraint_scoring=True,
        session_memory=True,
        clarification="info_gain",
        dynamic_weights=True,
        phrase_rerank=True,
        popularity_rerank=True,
        popularity_rerank_weight=POPULARITY_RERANK_WEIGHT,
        exclude_shown=True,
        ordered_rerank=True,
        skip_covered_attributes=True,
    ),
}

# The configuration the submission claims and is graded on. Documented in
# the README under "Retention decision"; a test binds the two together.
SUBMISSION_CONFIG_NAME = "O"


def get_run_config(name: str | None = None) -> RunConfig:
    """Resolve a named ablation config.

    An unset environment selects ``SUBMISSION_CONFIG_NAME``, because the
    official harness constructs the Agent without naming a config and whatever
    the default resolves to is what actually gets graded. A misspelled name
    still falls back to baseline A, which needs no optional dependency.

    Selecting a hybrid config is safe without the dense extras: the retriever
    factory degrades to the deterministic BM25 route rather than failing.
    """
    fallback = os.getenv("SHOPLENS_CONFIG", SUBMISSION_CONFIG_NAME)
    selected = (name if name is not None else fallback).strip().upper()
    return CONFIGS.get(selected, CONFIGS["A"])

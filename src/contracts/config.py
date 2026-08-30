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
    popularity_rerank_weight: float = 0.0
    profile_rerank_weight: float = 0.0
    dense_text_recipe: DenseTextRecipe = "full"
    negative_preference: bool = False


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
    "Z": replace(_A, name="Z", clarification="off"),
}

# The configuration the submission claims and is graded on. Documented in
# the README under "Retention decision"; a test binds the two together.
SUBMISSION_CONFIG_NAME = "T"


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

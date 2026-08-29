from __future__ import annotations

import os
from dataclasses import dataclass, replace
from typing import Literal


RetrievalMode = Literal["bm25", "dense", "hybrid"]
ClarificationMode = Literal["off", "empty_result_only", "info_gain"]
RerankerMode = Literal["none", "local_cross_encoder"]

HIT_RATE_WEIGHT = 0.50
MRR_WEIGHT = 0.30
EFFICIENCY_WEIGHT = 0.20
MISS_TURN_VALUE = 11
MAX_TURNS = 10


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
    "Z": replace(_A, name="Z", clarification="off"),
}


def get_run_config(name: str | None = None) -> RunConfig:
    """Resolve a named ablation config; unknown values safely use baseline A."""
    selected = (name if name is not None else os.getenv("SHOPLENS_CONFIG", "A")).strip().upper()
    return CONFIGS.get(selected, CONFIGS["A"])

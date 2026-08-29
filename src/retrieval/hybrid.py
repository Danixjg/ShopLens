from __future__ import annotations

from pathlib import Path

from src.catalog import Catalog
from src.contracts.config import RunConfig
from src.contracts.retrieval import Candidate, RetrievalQuery, Retriever
from src.retrieval.bm25 import BM25Retriever
from src.retrieval.dense import DenseRetriever, DenseUnavailable


class HybridRetriever:
    """Reciprocal-rank fusion of lexical and dense candidate lists."""

    def __init__(self, lexical: Retriever, dense: Retriever, rank_constant: int = 60) -> None:
        self.lexical = lexical
        self.dense = dense
        self.rank_constant = rank_constant

    def search(self, query: RetrievalQuery, k: int) -> list[Candidate]:
        depth = max(k * 5, 50)
        lists = (self.lexical.search(query, depth), self.dense.search(query, depth))
        scores: dict[str, float] = {}
        components: dict[str, dict[str, float]] = {}
        for name, candidates in zip(("bm25_rrf", "dense_rrf"), lists):
            for rank, candidate in enumerate(candidates, start=1):
                value = 1.0 / (self.rank_constant + rank)
                scores[candidate.asin] = scores.get(candidate.asin, 0.0) + value
                components.setdefault(candidate.asin, {})[name] = value
        ordered = sorted(scores, key=lambda asin: (-scores[asin], asin))[:max(0, k)]
        return [Candidate(asin=asin, score=scores[asin], components=components[asin]) for asin in ordered]

    def search_for_intent(
        self, query: RetrievalQuery, k: int, intent: str,
    ) -> list[Candidate]:
        """Route Buying to lexical-weighted recall; keep discovery intents hybrid."""
        if intent != "buying":
            return self.search(query, k)
        lexical = self.lexical.search(query, k)
        hybrid = self.search(query, k)
        scores: dict[str, float] = {}
        components: dict[str, dict[str, float]] = {}
        for name, weight, candidates in (
            ("buying_lexical_rrf", 0.75, lexical),
            ("buying_hybrid_rrf", 0.25, hybrid),
        ):
            for rank, candidate in enumerate(candidates, start=1):
                value = weight / (self.rank_constant + rank)
                scores[candidate.asin] = scores.get(candidate.asin, 0.0) + value
                components.setdefault(candidate.asin, {})[name] = value
        ordered = sorted(scores, key=lambda asin: (-scores[asin], asin))
        # Return the union to the recoverable constraint scorer. The Agent
        # still truncates only after scoring and never emits more than top_k.
        return [Candidate(asin, scores[asin], components[asin]) for asin in ordered]


def build_retriever(
    catalog: Catalog,
    config: RunConfig,
    model_path: str | Path = "models/all-MiniLM-L6-v2",
) -> Retriever:
    if config.retrieval_mode == "bm25":
        return BM25Retriever(catalog)
    try:
        dense = DenseRetriever(catalog, model_path)
    except DenseUnavailable:
        # Official scoring may be offline. A missing optional dense component
        # degrades to the deterministic BM25 route instead of failing a turn.
        return BM25Retriever(catalog)
    if config.retrieval_mode == "dense":
        return dense
    return HybridRetriever(BM25Retriever(catalog), dense)

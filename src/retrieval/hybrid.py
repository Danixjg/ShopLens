from __future__ import annotations

from pathlib import Path

from src.catalog import Catalog
from src.contracts.config import RunConfig
from src.contracts.retrieval import Candidate, RetrievalQuery, Retriever
from src.retrieval.bm25 import BM25Retriever
from src.retrieval.dense import DenseRetriever, DenseUnavailable, OFFICIAL_MODEL_PATH


class HybridRetriever:
    """Reciprocal-rank fusion of lexical and dense candidate lists."""

    def __init__(self, lexical: Retriever, dense: Retriever, rank_constant: int = 60) -> None:
        self.lexical = lexical
        self.dense = dense
        self.rank_constant = rank_constant

    def _source_lists(
        self, query: RetrievalQuery, k: int,
    ) -> tuple[list[Candidate], list[Candidate]]:
        count = self._safe_k(k)
        if count == 0:
            return [], []
        depth = max(count * 5, 50)
        return self.lexical.search(query, depth), self.dense.search(query, depth)

    @staticmethod
    def _safe_k(k: int) -> int:
        try:
            return max(0, int(k))
        except (TypeError, ValueError, OverflowError):
            return 0

    def _fuse(
        self,
        lexical: list[Candidate],
        dense: list[Candidate],
        k: int,
    ) -> list[Candidate]:
        count = self._safe_k(k)
        if count == 0:
            return []
        scores: dict[str, float] = {}
        components: dict[str, dict[str, float]] = {}
        for name, candidates in (("bm25_rrf", lexical), ("dense_rrf", dense)):
            for rank, candidate in enumerate(candidates, start=1):
                value = 1.0 / (self.rank_constant + rank)
                scores[candidate.asin] = scores.get(candidate.asin, 0.0) + value
                components.setdefault(candidate.asin, {})[name] = value
        ordered = sorted(scores, key=lambda asin: (-scores[asin], asin))[:count]
        return [Candidate(asin=asin, score=scores[asin], components=components[asin]) for asin in ordered]

    def search(self, query: RetrievalQuery, k: int) -> list[Candidate]:
        if self._safe_k(k) == 0:
            return []
        lexical, dense = self._source_lists(query, k)
        return self._fuse(lexical, dense, k)

    def search_for_intent(
        self, query: RetrievalQuery, k: int, intent: str,
    ) -> list[Candidate]:
        """Route Buying to lexical-weighted recall; keep discovery intents hybrid."""
        count = self._safe_k(k)
        if count == 0:
            return []
        if intent != "buying":
            return self.search(query, count)
        lexical_pool, dense_pool = self._source_lists(query, count)
        lexical = lexical_pool[:count]
        hybrid = self._fuse(lexical_pool, dense_pool, count)
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
    model_path: str | Path = OFFICIAL_MODEL_PATH,
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

from __future__ import annotations

import math

from src.catalog import Catalog
from src.contracts.config import POPULARITY_RERANK_WEIGHT
from src.contracts.retrieval import Candidate


# Small, predeclared diagnostic grid; production config Q records its choice.
ALLOWED_POPULARITY_WEIGHTS = frozenset((0.05, 0.10, 0.15, 0.20))


class PopularityReranker:
    """Apply a bounded catalog-popularity prior to frozen Top-K membership.

    Popularity is deliberately subordinate to relevance: this class receives
    only the already-selected Top-K and cannot add or remove a product. Counts
    are log-scaled against the immutable catalog maximum so a single viral
    product cannot contribute an unbounded score.
    """

    def __init__(
        self,
        catalog: Catalog,
        weight: float = POPULARITY_RERANK_WEIGHT,
    ) -> None:
        if weight not in ALLOWED_POPULARITY_WEIGHTS:
            raise ValueError(
                f"popularity rerank weight must be one of "
                f"{sorted(ALLOWED_POPULARITY_WEIGHTS)}"
            )
        self.catalog = catalog
        self.weight = weight
        maximum = max((max(0, product.rating_number) for product in catalog), default=0)
        self._maximum_log_count = math.log1p(maximum)

    def _normalized_count(self, asin: str) -> tuple[float, float]:
        product = self.catalog.get(asin)
        count = max(0, product.rating_number) if product is not None else 0
        log_count = math.log1p(count)
        normalized = (
            min(1.0, max(0.0, log_count / self._maximum_log_count))
            if self._maximum_log_count > 0.0
            else 0.0
        )
        return log_count, normalized

    def rerank(self, candidates: list[Candidate]) -> list[Candidate]:
        if not candidates:
            return candidates

        ranked: list[tuple[float, int, Candidate]] = []
        for original_rank, candidate in enumerate(candidates, start=1):
            log_count, popularity_norm = self._normalized_count(candidate.asin)
            bonus = self.weight * popularity_norm / 61
            final = candidate.score + bonus
            components = {
                **candidate.components,
                "popularity_log_count": log_count,
                "popularity_norm": popularity_norm,
                "popularity_rank_bonus": bonus,
            }
            ranked.append((
                final,
                original_rank,
                Candidate(candidate.asin, final, components),
            ))

        ranked.sort(key=lambda item: (-item[0], item[1], item[2].asin))
        return [candidate for _score, _rank, candidate in ranked]

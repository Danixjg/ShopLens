from __future__ import annotations

from collections import defaultdict

from src.catalog import Catalog
from src.contracts.retrieval import Candidate, RetrievalQuery
from src.retrieval.text import terms


HARD_PENALTIES = {"material": 4.0, "color": 2.0}
DEFAULT_HARD_PENALTY = 3.0


class ConstraintScorer:
    """Apply recoverable penalties and bonuses; never filter candidates."""

    def __init__(self, catalog: Catalog) -> None:
        self.catalog = catalog
        self._term_cache: dict[str, frozenset[str]] = {}

    def _product_terms(self, asin: str) -> frozenset[str]:
        cached = self._term_cache.get(asin)
        if cached is not None:
            return cached
        product = self.catalog.get(asin)
        value = frozenset(terms(product.searchable_text)) if product else frozenset()
        self._term_cache[asin] = value
        return value

    def score(self, candidates: list[Candidate], query: RetrievalQuery) -> list[Candidate]:
        rescored: list[Candidate] = []
        soft_weight = max(0.25, 1.0 - 0.08 * max(0, query.turn_index - 1))
        # Retain every disclosed value but keep one bounded scoring component
        # per attribute. Otherwise two values in the same broad simulator bucket
        # would double an already dominant penalty/bonus scale.
        hard_terms: dict[str, list[frozenset[str]]] = defaultdict(list)
        soft_terms: dict[str, list[frozenset[str]]] = defaultdict(list)
        exclude_terms: dict[str, list[frozenset[str]]] = defaultdict(list)
        for attribute, value in query.exclude_values:
            exclude_terms[attribute].append(frozenset(terms(_constraint_value(attribute, value))))
        for attribute, value in query.hard:
            hard_terms[attribute].append(frozenset(terms(_constraint_value(attribute, value))))
        for attribute, value in query.soft:
            soft_terms[attribute].append(frozenset(terms(_constraint_value(attribute, value))))
        for candidate in candidates:
            corpus_terms = self._product_terms(candidate.asin)
            adjustment = 0.0
            components = dict(candidate.components)
            for attribute, wanted_values in hard_terms.items():
                matched = bool(wanted_values) and all(
                    bool(wanted) and wanted.issubset(corpus_terms)
                    for wanted in wanted_values
                )
                change = 1.5 if matched else -HARD_PENALTIES.get(attribute, DEFAULT_HARD_PENALTY)
                adjustment += change
                components[f"hard_{attribute}"] = change
            for attribute, wanted_values in soft_terms.items():
                wanted = frozenset().union(*wanted_values)
                overlap = len(wanted & corpus_terms) / max(1, len(wanted))
                change = soft_weight * overlap
                adjustment += change
                components[f"soft_{attribute}"] = change
            # A replaced preference is scored exactly like a soft one with the
            # sign reversed, so it inherits the same turn decay instead of
            # introducing a separately tuned penalty scale.
            for attribute, unwanted_values in exclude_terms.items():
                unwanted = frozenset().union(*unwanted_values)
                overlap = len(unwanted & corpus_terms) / max(1, len(unwanted))
                change = -soft_weight * overlap
                adjustment += change
                components[f"excluded_{attribute}"] = change
            rescored.append(Candidate(candidate.asin, candidate.score + adjustment, components))
        return sorted(rescored, key=lambda item: (-item.score, item.asin))


def _constraint_value(attribute: str, value: str) -> str:
    """Remove evaluator labels such as ``color:`` before token matching."""
    prefix, separator, remainder = value.partition(":")
    if separator and prefix.strip().lower().replace(" ", "_") == attribute:
        return remainder.strip()
    return value

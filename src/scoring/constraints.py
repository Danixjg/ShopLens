from __future__ import annotations

from src.catalog import Catalog
from src.contracts.retrieval import Candidate, RetrievalQuery
from src.retrieval.text import terms


HARD_PENALTIES = {"material": 4.0, "color": 2.0}
DEFAULT_HARD_PENALTY = 3.0


class ConstraintScorer:
    """Apply recoverable penalties and bonuses; never filter candidates."""

    def __init__(self, catalog: Catalog) -> None:
        self.catalog = catalog

    def score(self, candidates: list[Candidate], query: RetrievalQuery) -> list[Candidate]:
        rescored: list[Candidate] = []
        soft_weight = max(0.25, 1.0 - 0.08 * max(0, query.turn_index - 1))
        # Constraint values are identical for every candidate. Tokenize them
        # once per scoring pass instead of once per candidate.
        hard_terms = {
            attribute: frozenset(terms(_constraint_value(attribute, value)))
            for attribute, value in query.hard.items()
        }
        soft_terms = {
            attribute: frozenset(terms(_constraint_value(attribute, value)))
            for attribute, value in query.soft.items()
        }
        for candidate in candidates:
            product = self.catalog.get(candidate.asin)
            corpus_terms = set(terms(product.searchable_text)) if product else set()
            adjustment = 0.0
            components = dict(candidate.components)
            for attribute, wanted in hard_terms.items():
                matched = bool(wanted) and wanted.issubset(corpus_terms)
                change = 1.5 if matched else -HARD_PENALTIES.get(attribute, DEFAULT_HARD_PENALTY)
                adjustment += change
                components[f"hard_{attribute}"] = change
            for attribute, wanted in soft_terms.items():
                overlap = len(wanted & corpus_terms) / max(1, len(wanted))
                change = soft_weight * overlap
                adjustment += change
                components[f"soft_{attribute}"] = change
            rescored.append(Candidate(candidate.asin, candidate.score + adjustment, components))
        return sorted(rescored, key=lambda item: (-item.score, item.asin))


def _constraint_value(attribute: str, value: str) -> str:
    """Remove evaluator labels such as ``color:`` before token matching."""
    prefix, separator, remainder = value.partition(":")
    if separator and prefix.strip().lower().replace(" ", "_") == attribute:
        return remainder.strip()
    return value

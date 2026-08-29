from __future__ import annotations

from collections import Counter
from math import log2

from src.catalog import Catalog, Product
from src.contracts.config import RunConfig
from src.contracts.response import AskAttribute
from src.contracts.retrieval import Candidate
from src.contracts.state import SessionState
from src.retrieval.text import terms


CLARIFICATION_SEQUENCE: tuple[AskAttribute, ...] = ("feature", "material", "color")

# A targeted facet is only worth a turn when it splits the viable pool almost
# perfectly. Binary split entropy is capped at 1.0, so this threshold keeps the
# structured question for the case where it genuinely halves the pool and
# otherwise asks openly, which surfaces any undisclosed constraint instead of
# one bucket's worth.
OPEN_QUESTION_GAIN = 0.9
MIN_FACET_SUPPORT = 0.05
POOL_SAMPLE_LIMIT = 60

_FACET_VALUES: dict[str, frozenset[str]] = {
    "material": frozenset(
        ("cotton", "polyester", "nylon", "leather", "wool", "spandex", "silk", "rayon", "fabric")
    ),
    "color": frozenset(
        ("black", "white", "blue", "red", "pink", "green", "brown", "gray",
         "grey", "purple", "yellow", "orange")
    ),
}
_STRUCTURED_VALUES = frozenset().union(*_FACET_VALUES.values())


def _satisfies_hard_constraints(candidate: Candidate) -> bool:
    """True when no disclosed hard constraint penalised this candidate.

    ``ConstraintScorer`` records a negative ``hard_<attribute>_<n>`` component
    for every violated hard constraint. Candidates without hard components
    (configs that skip constraint scoring) are treated as viable.
    """
    return all(
        value >= 0
        for key, value in candidate.components.items()
        if key.startswith("hard_")
    )


def _facet_values(product: Product, attribute: str) -> set[str]:
    if attribute == "feature":
        return set(terms(product.features)) - _STRUCTURED_VALUES
    return set(terms(product.searchable_text)) & _FACET_VALUES.get(attribute, frozenset())


def _information_gain(attribute: str, products: list[Product]) -> float:
    """Entropy of the best binary split this attribute induces on the pool."""
    size = len(products)
    if size < 2:
        return 0.0
    counts: Counter[str] = Counter()
    for product in products:
        counts.update(_facet_values(product, attribute))
    support = max(1, round(size * MIN_FACET_SUPPORT))
    best = 0.0
    for count in counts.values():
        if not support <= count <= size - support:
            continue
        probability = count / size
        best = max(
            best,
            -probability * log2(probability) - (1.0 - probability) * log2(1.0 - probability),
        )
    return best


class ClarificationPolicy:
    def __init__(self, config: RunConfig, catalog: Catalog | None = None) -> None:
        self.config = config
        self.catalog = catalog

    @staticmethod
    def _covered(state: SessionState) -> set[str]:
        """Attributes the shopper has already spoken to on an active slot.

        Re-asking a covered bucket spends a turn to be told there is no further
        preference, so coverage disqualifies a facet from the targeted branch.
        """
        return {slot.attribute for slot in state.slots if slot.active}

    @staticmethod
    def _just_declined(state: SessionState, attribute: str) -> bool:
        """True when the shopper waved this exact attribute off on the last turn.

        A refusal means "use your judgment here", not a standing veto: the
        shopper answers the following question normally. Deferring by a single
        turn respects the refusal without going silent, which would forfeit
        every remaining turn of a hard 10-turn budget.
        """
        return state.last_declined == attribute

    def _viable_products(self, candidates: list[Candidate]) -> list[Product]:
        if self.catalog is None:
            return []
        products: list[Product] = []
        for candidate in candidates:
            if not _satisfies_hard_constraints(candidate):
                continue
            product = self.catalog.get(candidate.asin)
            if product is not None:
                products.append(product)
            if len(products) >= POOL_SAMPLE_LIMIT:
                break
        return products

    def _fixed_choice(self, state: SessionState) -> AskAttribute | None:
        for attribute in CLARIFICATION_SEQUENCE:
            if attribute not in state.asked_attributes and attribute not in state.declined_attributes:
                return attribute
        return "other" if "other" not in state.asked_attributes else None

    def _information_choice(
        self, state: SessionState, candidates: list[Candidate],
    ) -> AskAttribute | None:
        covered = self._covered(state)
        unasked = [
            attribute for attribute in CLARIFICATION_SEQUENCE
            if attribute not in state.asked_attributes
            and attribute not in state.declined_attributes
            and attribute not in covered
        ]
        if unasked:
            products = self._viable_products(candidates)
            gain, _, attribute = max(
                (_information_gain(name, products), -index, name)
                for index, name in enumerate(unasked)
            )
            if gain >= OPEN_QUESTION_GAIN:
                return attribute
        if not self._just_declined(state, "other"):
            return "other"
        # The open question was just waved off, so spend this turn on the most
        # promising targeted facet instead of falling silent.
        return unasked[0] if unasked else None

    def choose(self, state: SessionState, candidates: list[Candidate]) -> AskAttribute | None:
        if self.config.clarification == "off":
            return None
        # A refusal retires only that attribute; the shopper answers normally
        # afterwards, so the policy must keep asking about everything else.
        if self.config.clarification == "info_gain":
            return self._information_choice(state, candidates)
        return self._fixed_choice(state)

    @staticmethod
    def is_over_general(candidates: list[Candidate], recommendation_limit: int) -> bool:
        """Detect more constraint-satisfying matches than the response can expose.

        The candidate pool passed here is the pre-truncation retrieval depth,
        which is deliberately over-fetched for constraint scoring. Counting the
        raw pool would flag over-generality on nearly every turn, so we count
        only viable matches -- candidates that satisfy every disclosed hard
        constraint (no negative ``hard_*`` scoring component).
        """
        if recommendation_limit <= 0:
            return False
        viable = sum(1 for candidate in candidates if _satisfies_hard_constraints(candidate))
        return viable > recommendation_limit

    @staticmethod
    def message(attribute: AskAttribute | None, over_general: bool = False) -> str:
        if attribute is None:
            return "Here are the closest matches based on what you shared."
        prefix = "I found many plausible matches. " if over_general else ""
        if attribute == "other":
            return prefix + "Is there another requirement that would help narrow these options?"
        return prefix + f"Do you have a {attribute.replace('_', ' ')} preference?"

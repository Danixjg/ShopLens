from __future__ import annotations

from src.contracts.config import RunConfig
from src.contracts.response import AskAttribute
from src.contracts.retrieval import Candidate
from src.contracts.state import SessionState


# Measured simulator prior from Plan.md §2.2. Do not re-derive or reorder.
CLARIFICATION_SEQUENCE: tuple[AskAttribute, ...] = ("feature", "material", "color")


def _satisfies_hard_constraints(candidate: Candidate) -> bool:
    """True when no disclosed hard constraint penalised this candidate.

    ``ConstraintScorer`` records a negative ``hard_<attribute>`` component for
    every violated hard constraint. Candidates without hard components (configs
    that skip constraint scoring) are treated as viable.
    """
    return all(
        value >= 0
        for key, value in candidate.components.items()
        if key.startswith("hard_")
    )


class ClarificationPolicy:
    def __init__(self, config: RunConfig) -> None:
        self.config = config

    def choose(self, state: SessionState, candidates: list[Candidate]) -> AskAttribute | None:
        if self.config.clarification == "off":
            return None
        if state.declined_attributes:
            return None
        for attribute in CLARIFICATION_SEQUENCE:
            if attribute not in state.asked_attributes:
                return attribute
        if "other" not in state.asked_attributes:
            return "other"
        return None

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

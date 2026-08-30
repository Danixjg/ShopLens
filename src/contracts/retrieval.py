from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from .parsing import ConstraintPairs


@dataclass(frozen=True, slots=True)
class RetrievalQuery:
    text: str
    hard: ConstraintPairs = ()
    soft: ConstraintPairs = ()
    exclude: ConstraintPairs = ()
    category: str | None = None
    turn_index: int = 1


@dataclass(frozen=True, slots=True)
class Candidate:
    asin: str
    score: float
    components: dict[str, float] = field(default_factory=dict)


class Retriever(Protocol):
    def search(self, query: RetrievalQuery, k: int) -> list[Candidate]: ...


# Routes whose turns carry an explicit hard constraint, so lexical precision is
# the appropriate evidence. Kept as data in the contracts layer because both the
# retriever and the dynamic scorer answer this same question independently; the
# Buying-only and hard-constraint-symmetric policies are then one flag apart and
# can be measured against each other (findings 6 and 17).
BUYING_PRECISION_INTENTS: frozenset[str] = frozenset({"buying"})
HARD_CONSTRAINT_INTENTS: frozenset[str] = frozenset({"buying", "intent_override"})

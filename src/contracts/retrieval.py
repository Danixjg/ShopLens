from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True, slots=True)
class RetrievalQuery:
    text: str
    hard: dict[str, str] = field(default_factory=dict)
    soft: dict[str, str] = field(default_factory=dict)
    category: str | None = None
    turn_index: int = 1


@dataclass(frozen=True, slots=True)
class Candidate:
    asin: str
    score: float
    components: dict[str, float] = field(default_factory=dict)


class Retriever(Protocol):
    def search(self, query: RetrievalQuery, k: int) -> list[Candidate]: ...

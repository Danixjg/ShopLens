from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias


AskAttribute: TypeAlias = Literal[
    "category", "material", "color", "size", "style", "brand", "budget",
    "feature", "use_case", "other",
]


@dataclass(frozen=True, slots=True)
class Recommendation:
    parent_asin: str
    score: float | None = None

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {"parent_asin": self.parent_asin}
        if self.score is not None:
            result["score"] = float(self.score)
        return result


@dataclass(frozen=True, slots=True)
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "prompt_tokens": max(0, int(self.prompt_tokens)),
            "completion_tokens": max(0, int(self.completion_tokens)),
        }


@dataclass(frozen=True, slots=True)
class AgentReply:
    message: str
    ask_attribute: AskAttribute | None
    recommendations: list[Recommendation]
    usage: Usage | None = None

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "message": str(self.message),
            "ask_attribute": self.ask_attribute,
            "recommendations": [item.to_dict() for item in self.recommendations],
        }
        if self.usage is not None:
            result["usage"] = self.usage.to_dict()
        return result

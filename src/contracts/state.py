from __future__ import annotations

from dataclasses import dataclass, field

from .response import AskAttribute


@dataclass(frozen=True, slots=True)
class UserProfile:
    purchase_frequency: str
    average_prior_rating: float | None
    rating_style: str
    preference_tags: list[str]
    summary: str

    @classmethod
    def from_dict(cls, value: dict) -> "UserProfile":
        rating = value.get("average_prior_rating")
        tags = value.get("preference_tags") or []
        return cls(
            purchase_frequency=str(value.get("purchase_frequency", "")),
            average_prior_rating=float(rating) if isinstance(rating, (int, float)) else None,
            rating_style=str(value.get("rating_style", "")),
            preference_tags=[str(item) for item in tags if item] if isinstance(tags, (list, tuple)) else [],
            summary=str(value.get("summary", "")),
        )


@dataclass(slots=True)
class Slot:
    attribute: str
    value: str
    hard: bool
    source_turn: int
    confidence: float
    active: bool
    updated_at: int


@dataclass(slots=True)
class SessionState:
    slots: list[Slot] = field(default_factory=list)
    intent: str = "browsing"
    turn_index: int = 0
    category: str = ""
    history: list[tuple[str, str]] = field(default_factory=list)
    asked_attributes: list[AskAttribute] = field(default_factory=list)
    declined_attributes: set[str] = field(default_factory=set)
    last_recommendations: list[str] = field(default_factory=list)
    user_profile: UserProfile | None = None

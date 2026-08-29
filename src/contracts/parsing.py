from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class ParsedTurn:
    intent: str
    category: str | None
    hard_constraints: dict[str, str] = field(default_factory=dict)
    soft_preferences: dict[str, str] = field(default_factory=dict)
    requested_action: str | None = None
    is_override: bool = False
    declined_attribute: str | None = None

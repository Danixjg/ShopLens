from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias


# Ordered ``(attribute, value)`` pairs. A turn may disclose several constraints
# that classify into the same attribute bucket, so they cannot be keyed by
# attribute without discarding all but the last.
ConstraintPairs: TypeAlias = tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class ParsedTurn:
    intent: str
    category: str | None
    hard_constraints: ConstraintPairs = ()
    soft_preferences: ConstraintPairs = ()
    requested_action: str | None = None
    is_override: bool = False
    declined_attribute: str | None = None

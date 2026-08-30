from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias


# Ordered ``(attribute, value)`` pairs. A turn may disclose several constraints
# that classify into the same attribute bucket, so they cannot be keyed by
# attribute without discarding all but the last.
ConstraintPairs: TypeAlias = tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class ParsedTurn:
    # ``None`` means the turn carries no intent signal, not "browsing". Ordinary
    # disclosure and decline replies do not re-declare why the customer is here,
    # so they must leave an established route unchanged rather than rely on the
    # state layer to ignore a semantically false event.
    intent: str | None
    category: str | None
    hard_constraints: ConstraintPairs = ()
    soft_preferences: ConstraintPairs = ()
    requested_action: str | None = None
    is_override: bool = False
    declined_attribute: str | None = None

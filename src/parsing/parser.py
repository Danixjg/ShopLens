from __future__ import annotations

import re

from src.attributes import classify_attribute
from src.contracts.parsing import ParsedTurn


OVERRIDE_MARKER = "Actually, ignore my earlier preference. What I need is:"
_BUYING_MARKER = ". A key requirement is:"
_EXPLORE_MARKER = ", but I'm still exploring."
_DISCLOSURE_MARKER = "For that, what matters is:"
_DECLINE_RE = re.compile(
    r"I don't have (?:a|an additional) preference for ([a-z_]+)", re.I,
)
_CONTROL_MESSAGES = frozenset({
    "Those options are not quite right yet. Ask me about one specific attribute.",
})
def _category_from_initial(message: str) -> str | None:
    prefix = "I'm looking for "
    if not message.startswith(prefix):
        return None
    remainder = message[len(prefix):]
    if _BUYING_MARKER in remainder:
        remainder = remainder.split(_BUYING_MARKER, 1)[0]
    elif _EXPLORE_MARKER in remainder:
        remainder = remainder.split(_EXPLORE_MARKER, 1)[0]
    elif ". " in remainder:
        remainder = remainder.split(". ", 1)[0]
    return remainder.strip(" .") or None


class TurnParser:
    """Deterministically parse the simulator's controlled customer language."""

    def parse(self, user_message: str, turn: int) -> ParsedTurn:
        message = str(user_message).strip()
        category = _category_from_initial(message)
        if _BUYING_MARKER in message:
            intent = "buying"
        elif category is not None and _EXPLORE_MARKER not in message:
            intent = "intent_override"
        else:
            intent = "browsing"
        hard: list[tuple[str, str]] = []
        soft: list[tuple[str, str]] = []
        is_override = OVERRIDE_MARKER in message
        declined: str | None = None

        decline_match = _DECLINE_RE.search(message)
        if decline_match:
            declined = decline_match.group(1).lower()

        values: list[str] = []
        if is_override:
            intent = "intent_override"
            value = message.split(OVERRIDE_MARKER, 1)[1].strip(" .")
            if value:
                values.append(value)
        elif _BUYING_MARKER in message:
            value = message.split(_BUYING_MARKER, 1)[1].strip(" .")
            if value:
                values.append(value)
        elif _DISCLOSURE_MARKER in message:
            disclosed = message.split(_DISCLOSURE_MARKER, 1)[1].strip(" .")
            values.extend(item.strip(" .") for item in disclosed.split(";") if item.strip(" ."))
        elif category is not None and ". " in message:
            free_text = message.split(". ", 1)[1].strip(" .")
            if free_text:
                soft.append((classify_attribute(free_text), free_text))
        elif message and declined is None and message not in _CONTROL_MESSAGES:
            # Accept ordinary customer language as a soft retrieval preference.
            soft.append((classify_attribute(message), message))

        for value in values:
            target = hard if is_override or _BUYING_MARKER in message else soft
            target.append((classify_attribute(value), value))

        return ParsedTurn(
            intent=intent,
            category=category,
            hard_constraints=tuple(hard),
            soft_preferences=tuple(soft),
            requested_action=None,
            is_override=is_override,
            declined_attribute=declined,
        )

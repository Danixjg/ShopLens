from __future__ import annotations

import re

from src.contracts.parsing import ParsedTurn
from src.contracts.state import SessionState, Slot


def _identity(attribute: str, value: str) -> tuple[str, str]:
    return attribute.strip().casefold(), re.sub(r"\s+", " ", value).strip().casefold()


def apply_parsed_turn(state: SessionState, parsed: ParsedTurn, user_message: str, turn: int) -> None:
    """Apply one parsed customer turn, preserving the slot-erasure invariants."""
    state.turn_index = max(1, int(turn))
    state.history.append(("user", str(user_message)))
    if parsed.declined_attribute:
        state.declined_attributes.add(parsed.declined_attribute)

    if parsed.category and parsed.category != state.category:
        if state.category:
            for slot in state.slots:
                if slot.active and not slot.hard:
                    slot.active = False
        state.category = parsed.category

    if parsed.is_override:
        state.intent = "intent_override"
        # Retire the original preference, not useful constraints disclosed on
        # later clarification turns. Disclosures now accumulate rather than
        # replace, so the earliest active soft turn is the superseded one.
        soft_turns = [slot.source_turn for slot in state.slots if slot.active and not slot.hard]
        if soft_turns:
            superseded_turn = min(soft_turns)
            for slot in state.slots:
                if slot.active and not slot.hard and slot.source_turn == superseded_turn:
                    slot.active = False
                    slot.superseded = True
    elif parsed.intent is not None:
        # Only a turn that actually declares intent may change the route.
        state.intent = parsed.intent

    for hard, constraints in ((True, parsed.hard_constraints), (False, parsed.soft_preferences)):
        for attribute, value in constraints:
            # Same-attribute disclosures accumulate: the simulator discloses up
            # to two constraints per turn and most classify into one bucket, so
            # replacing by attribute would discard the discriminative evidence
            # the turn was spent acquiring. Only an override erases a slot.
            clean_attribute = str(attribute).strip().casefold()
            clean_value = str(value).strip()
            if not clean_attribute or not clean_value:
                continue
            state.declined_attributes.discard(clean_attribute)
            identity = _identity(clean_attribute, clean_value)
            matches = [
                slot for slot in state.slots
                if slot.active and _identity(slot.attribute, slot.value) == identity
            ]
            if matches:
                # Collapse any historical duplicate slots onto the earliest
                # source while preserving the strongest (hard) interpretation.
                slot = min(matches, key=lambda item: (item.source_turn, item.updated_at))
                for duplicate in matches:
                    if duplicate is not slot:
                        duplicate.active = False
                if hard and not slot.hard:
                    slot.hard = True
                    slot.confidence = 1.0
                elif not hard and slot.hard:
                    slot.confidence = max(slot.confidence, 1.0)
                else:
                    slot.confidence = max(slot.confidence, 1.0 if hard else 0.75)
                slot.updated_at = state.turn_index
                continue
            state.slots.append(Slot(
                attribute=clean_attribute,
                value=clean_value,
                hard=hard,
                source_turn=state.turn_index,
                confidence=1.0 if hard else 0.75,
                active=True,
                updated_at=state.turn_index,
            ))

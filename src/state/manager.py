from __future__ import annotations

from src.contracts.parsing import ParsedTurn
from src.contracts.state import SessionState, Slot


def apply_parsed_turn(state: SessionState, parsed: ParsedTurn, user_message: str, turn: int) -> None:
    """Apply one parsed customer turn, preserving the slot-erasure invariants."""
    state.turn_index = max(1, int(turn))
    state.history.append(("user", str(user_message)))
    state.last_declined = parsed.declined_attribute
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
    elif parsed.intent and (parsed.category is not None or state.turn_index == 1):
        state.intent = parsed.intent

    known = {(slot.attribute, slot.value, slot.hard) for slot in state.slots if slot.active}
    for hard, constraints in ((True, parsed.hard_constraints), (False, parsed.soft_preferences)):
        for attribute, value in constraints:
            # Same-attribute disclosures accumulate: the simulator discloses up
            # to two constraints per turn and most classify into one bucket, so
            # replacing by attribute would discard the discriminative evidence
            # the turn was spent acquiring. Only an override erases a slot.
            if (attribute, value, hard) in known:
                continue
            if hard:
                # A value already volunteered as a preference can be restated as
                # a requirement. Promote it rather than dropping the hard slot,
                # which would forfeit hard scoring and the override route.
                for slot in state.slots:
                    if slot.active and not slot.hard and (slot.attribute, slot.value) == (attribute, value):
                        slot.active = False
            known.add((attribute, value, hard))
            state.slots.append(Slot(
                attribute=attribute,
                value=value,
                hard=hard,
                source_turn=state.turn_index,
                confidence=1.0 if hard else 0.75,
                active=True,
                updated_at=state.turn_index,
            ))

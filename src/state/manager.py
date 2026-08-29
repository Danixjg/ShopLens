from __future__ import annotations

from src.contracts.parsing import ParsedTurn
from src.contracts.state import SessionState, Slot


def _deactivate_attribute(state: SessionState, attribute: str) -> None:
    for slot in state.slots:
        if slot.active and slot.attribute == attribute:
            slot.active = False


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
        # later clarification turns.
        # Include inactive history when locating the original turn. A later
        # clarification may already have replaced its slot in the same bucket.
        soft_turns = [slot.source_turn for slot in state.slots if not slot.hard]
        if soft_turns:
            superseded_turn = min(soft_turns)
            for slot in state.slots:
                if slot.active and not slot.hard and slot.source_turn == superseded_turn:
                    slot.active = False
        replaced = set(parsed.hard_constraints) | set(parsed.soft_preferences)
        for attribute in replaced:
            _deactivate_attribute(state, attribute)
    elif parsed.intent and (parsed.category is not None or state.turn_index == 1):
        state.intent = parsed.intent

    for hard, constraints in ((True, parsed.hard_constraints), (False, parsed.soft_preferences)):
        for attribute, value in constraints.items():
            _deactivate_attribute(state, attribute)
            state.slots.append(Slot(
                attribute=attribute,
                value=value,
                hard=hard,
                source_turn=state.turn_index,
                confidence=1.0 if hard else 0.75,
                active=True,
                updated_at=state.turn_index,
            ))

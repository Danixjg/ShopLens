from __future__ import annotations

from src.contracts.retrieval import RetrievalQuery
from src.contracts.state import SessionState


def build_retrieval_query(
    state: SessionState, *, exclude_superseded: bool = False,
) -> RetrievalQuery:
    """Build the frozen state/retrieval seam from active slots only.

    ``exclude_superseded`` additionally surfaces values the shopper replaced
    during an override. Declined attributes are deliberately not included: a
    question the shopper skipped says nothing about the values behind it.
    """
    active = [slot for slot in state.slots if slot.active]
    hard = tuple((slot.attribute, slot.value) for slot in active if slot.hard)
    soft = tuple((slot.attribute, slot.value) for slot in active if not slot.hard)
    parts: list[str] = []
    if state.category:
        parts.append(state.category)
    parts.extend(slot.value for slot in active)
    exclude = (
        tuple((slot.attribute, slot.value) for slot in state.slots if slot.superseded)
        if exclude_superseded
        else ()
    )
    return RetrievalQuery(
        text=" ".join(part for part in parts if part).strip(),
        hard=hard,
        soft=soft,
        exclude=exclude,
        category=state.category or None,
        turn_index=max(1, state.turn_index),
    )

from __future__ import annotations

from src.contracts.retrieval import RetrievalQuery
from src.contracts.state import SessionState


def build_retrieval_query(state: SessionState) -> RetrievalQuery:
    """Build the frozen state/retrieval seam from active slots only."""
    active = [slot for slot in state.slots if slot.active]
    hard = tuple((slot.attribute, slot.value) for slot in active if slot.hard)
    soft = tuple((slot.attribute, slot.value) for slot in active if not slot.hard)
    parts: list[str] = []
    if state.category:
        parts.append(state.category)
    parts.extend(slot.value for slot in active)
    return RetrievalQuery(
        text=" ".join(part for part in parts if part).strip(),
        hard=hard,
        soft=soft,
        category=state.category or None,
        turn_index=max(1, state.turn_index),
        exclude=frozenset(state.shown_asins),
    )

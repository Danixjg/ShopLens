from __future__ import annotations

from src.contracts.retrieval import HARD_CONSTRAINT_INTENTS, Candidate


class DynamicWeightScorer:
    """Apply the plan's deterministic buying/browsing ranking routes.

    Scoring has always treated every intent that carries an explicit hard
    constraint as high-intent. Retrieval routes only Buying that way by default;
    ``symmetric_intent_routing`` is the flag that closes the gap, and finding 17
    requires the difference to be measured rather than assumed.
    """

    def score(self, candidates: list[Candidate], intent: str) -> list[Candidate]:
        result: list[Candidate] = []
        for candidate in candidates:
            components = dict(candidate.components)
            if intent in HARD_CONSTRAINT_INTENTS:
                route_adjustment = 0.25 * sum(
                    value for key, value in components.items() if key.startswith("hard_")
                )
            else:
                route_adjustment = 0.25 * sum(
                    value for key, value in components.items() if key.startswith("soft_")
                )
            components["dynamic_route"] = route_adjustment
            result.append(Candidate(
                asin=candidate.asin,
                score=candidate.score + route_adjustment,
                components=components,
            ))
        return sorted(result, key=lambda item: (-item.score, item.asin))

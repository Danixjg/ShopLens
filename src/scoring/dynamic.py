from __future__ import annotations

from src.contracts.retrieval import Candidate


class DynamicWeightScorer:
    """Apply the plan's deterministic buying/browsing ranking routes."""

    def score(self, candidates: list[Candidate], intent: str) -> list[Candidate]:
        result: list[Candidate] = []
        for candidate in candidates:
            components = dict(candidate.components)
            if intent in {"buying", "intent_override"}:
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

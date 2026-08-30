"""Deterministic expected-value scoring for clarification attributes.

This is an independent, target-free adaptation of the expected value of
perfect information framing in Rao and Daumé III (ACL 2018),
https://doi.org/10.18653/v1/P18-1255. No upstream code, data, or model weights
are used.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from math import isfinite, log2

from src.catalog import Catalog
from src.contracts.retrieval import Candidate


TARGETED_ATTRIBUTES = ("feature", "material", "color")


def rank_weights(size: int) -> tuple[float, ...]:
    """Return normalized reciprocal-log weights in deterministic rank order."""
    if size <= 0:
        return ()
    raw = tuple(1.0 / log2(rank + 2) for rank in range(size))
    total = sum(raw)
    return tuple(weight / total for weight in raw)


def _normalize_weights(weights: Sequence[float]) -> tuple[float, ...]:
    cleaned = tuple(
        float(weight) if isfinite(float(weight)) and float(weight) > 0.0 else 0.0
        for weight in weights
    )
    total = sum(cleaned)
    return tuple(weight / total for weight in cleaned) if total > 0.0 else cleaned


def expected_question_value(
    answer_buckets: Sequence[Sequence[str]],
    *,
    weights: Sequence[float],
    recommendation_limit: int,
) -> float:
    """Estimate the expected Top-K posterior-mass gain from one question.

    Each candidate's prior mass is divided evenly across its distinct possible
    answers. Missing facets contribute no gain. The utility of an observed
    answer is the posterior probability mass recoverable in the best K
    candidates, so the result is bounded, deterministic, and target-free.
    """
    if len(answer_buckets) != len(weights):
        raise ValueError("expected one weight per answer bucket")
    if not answer_buckets or recommendation_limit <= 0:
        return 0.0

    prior = _normalize_weights(weights)
    if not any(prior):
        return 0.0
    limit = min(recommendation_limit, len(prior))
    prior_utility = sum(sorted(prior, reverse=True)[:limit])
    joint_by_answer: dict[str, list[float]] = {}

    for candidate_index, (candidate_mass, raw_answers) in enumerate(
        zip(prior, answer_buckets),
    ):
        answers = tuple(dict.fromkeys(str(answer) for answer in raw_answers if answer))
        if candidate_mass <= 0.0 or not answers:
            continue
        answer_mass = candidate_mass / len(answers)
        for answer in answers:
            joint = joint_by_answer.setdefault(answer, [0.0] * len(prior))
            joint[candidate_index] += answer_mass

    expected_gain = 0.0
    for joint in joint_by_answer.values():
        answer_probability = sum(joint)
        if answer_probability <= 0.0:
            continue
        posterior = (mass / answer_probability for mass in joint)
        answer_utility = sum(sorted(posterior, reverse=True)[:limit])
        expected_gain += answer_probability * max(0.0, answer_utility - prior_utility)

    return min(1.0, max(0.0, expected_gain))


def score_question_values(
    catalog: Catalog,
    candidates: Sequence[Candidate],
    *,
    active_values: Mapping[str, Collection[str]],
    recommendation_limit: int,
) -> dict[str, float]:
    """Score targeted attributes against a stable view of the candidate pool."""
    ordered = sorted(
        candidates,
        key=lambda candidate: (
            -(candidate.score if isfinite(candidate.score) else float("-inf")),
            candidate.asin,
        ),
    )
    weights = rank_weights(len(ordered))
    values: dict[str, float] = {}
    for attribute in TARGETED_ATTRIBUTES:
        covered = active_values.get(attribute, ())
        buckets = [
            tuple(
                value
                for value in catalog.facet_values(candidate.asin, attribute)
                if value not in covered
            )
            for candidate in ordered
        ]
        values[attribute] = expected_question_value(
            buckets,
            weights=weights,
            recommendation_limit=recommendation_limit,
        )
    return values

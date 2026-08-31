from __future__ import annotations

from collections import Counter
from math import log2

from src.attributes import normalize_ascii
from src.catalog import Catalog
from src.contracts.config import RunConfig
from src.contracts.response import AskAttribute
from src.contracts.retrieval import Candidate
from src.contracts.state import SessionState
from src.retrieval.dense import DenseRetriever, DenseUnavailable

from .question_value import score_question_values


CLARIFICATION_SEQUENCE: tuple[AskAttribute, ...] = ("feature", "material", "color")
# Reached only once CLARIFICATION_SEQUENCE and "other" are exhausted, so it
# changes nothing about early-turn attribute choice. Budget is the only
# addition tested so far; see RunConfig.extended_clarification.
EXTENDED_CLARIFICATION_SEQUENCE: tuple[AskAttribute, ...] = ("feature", "material", "color", "budget")
# The near-miss zone "embedding_promotion" compares against: candidates just
# past the response cutoff, up to this rank, in the pre-truncation pool.
EMBEDDING_PROMOTION_WINDOW = 50


def _satisfies_hard_constraints(candidate: Candidate) -> bool:
    """True when no disclosed hard constraint penalised this candidate.

    ``ConstraintScorer`` records one bounded negative ``hard_<attribute>``
    component for a violated attribute group. Candidates without hard
    components (configs that skip constraint scoring) are treated as viable.
    """
    return all(
        value >= 0
        for key, value in candidate.components.items()
        if key.startswith("hard_")
    )


def _information_gain(buckets: list[tuple[str, ...]]) -> float:
    """Normalized expected entropy reduction for a multiclass facet.

    A missing facet is intentionally uninformative: rather than treating
    ``missing`` as a revealing answer bucket, it leaves the posterior at N.
    """
    size = len(buckets)
    if size < 2:
        return 0.0
    prior = log2(size)
    counts = Counter(bucket for bucket in buckets if bucket)
    empty_count = sum(1 for bucket in buckets if not bucket)
    posterior = (empty_count / size) * prior
    posterior += sum((count / size) * log2(count) for count in counts.values())
    return max(0.0, (prior - posterior) / prior)


class ClarificationPolicy:
    def __init__(self, config: RunConfig, catalog: Catalog | None = None) -> None:
        self.config = config
        self.catalog = catalog
        self._sequence = (
            EXTENDED_CLARIFICATION_SEQUENCE if config.extended_clarification else CLARIFICATION_SEQUENCE
        )
        # Lazily built on first use by "embedding_promotion" only, and never
        # for any other mode. Reuses the on-disk embedding cache the primary
        # retriever already wrote for this catalog/model/text-recipe, so
        # building this second instance costs a cache load, not a re-embed.
        self._embedding_dense: DenseRetriever | None = None
        self._embedding_dense_attempted = False

    @staticmethod
    def _covered(state: SessionState) -> set[str]:
        """Attributes the shopper has already spoken to on an active slot."""
        return {slot.attribute for slot in state.slots if slot.active}

    @staticmethod
    def _active_values(state: SessionState, attribute: str) -> set[str]:
        active: set[str] = set()
        for slot in state.slots:
            if not slot.active or slot.attribute != attribute:
                continue
            label, separator, remainder = slot.value.partition(":")
            value = (
                remainder
                if separator and label.strip().casefold().replace(" ", "_") == attribute
                else slot.value
            )
            active.add(normalize_ascii(value))
        return active

    def _pool(self, candidates: list[Candidate]) -> list[Candidate]:
        """Prefer hard-constraint matches, retaining the full pool as fallback."""
        if self.catalog is None:
            return []
        full = [candidate for candidate in candidates if self.catalog.get(candidate.asin) is not None]
        viable = [candidate for candidate in full if _satisfies_hard_constraints(candidate)]
        return viable if len(viable) >= 2 else full

    def _gain(
        self, state: SessionState, attribute: str, candidates: list[Candidate],
    ) -> float:
        if self.catalog is None:
            return 0.0
        active = self._active_values(state, attribute)
        buckets = [
            tuple(value for value in self.catalog.facet_values(candidate.asin, attribute) if value not in active)
            for candidate in candidates
        ]
        return _information_gain(buckets)

    def _fixed_choice(self, state: SessionState) -> AskAttribute | None:
        covered = self._covered(state) if self.config.skip_covered_attributes else set()
        for attribute in self._sequence:
            if (
                attribute not in state.asked_attributes
                and attribute not in state.declined_attributes
                and attribute not in covered
            ):
                return attribute
        return (
            "other"
            if "other" not in state.asked_attributes and "other" not in state.declined_attributes
            else None
        )

    def _eligible(
        self, unasked: list[str], candidates: list[Candidate],
    ) -> list[str]:
        """Drop facets no candidate can answer, when the gate is enabled.

        A facet may be present in the schema yet unpopulated across the live
        pool, in which case a question about it cannot be answered from the
        catalog and spends a turn for nothing. Gating is skipped without a
        catalog, and never returns an empty list: going silent is worse than
        asking a sparse facet.
        """
        if not self.config.facet_population_gate or self.catalog is None:
            return unasked
        pool = self._pool(candidates)
        populated = [
            attribute for attribute in unasked
            if any(self.catalog.facet_values(candidate.asin, attribute) for candidate in pool)
        ]
        return populated or unasked

    def _information_choice(
        self, state: SessionState, candidates: list[Candidate], over_general: bool,
    ) -> AskAttribute | None:
        covered = self._covered(state) if self.config.skip_covered_attributes else set()
        unasked = [
            attribute for attribute in self._sequence
            if attribute not in state.asked_attributes
            and attribute not in state.declined_attributes
            and attribute not in covered
        ]
        unasked = self._eligible(unasked, candidates)
        if over_general and unasked:
            pool = self._pool(candidates)
            gain, _, attribute = max(
                (self._gain(state, name, pool), -index, name)
                for index, name in enumerate(unasked)
            )
            if gain > 0.0:
                return attribute
        if not over_general and unasked:
            return unasked[0]
        if (
            "other" not in state.asked_attributes
            and "other" not in state.declined_attributes
        ):
            return "other"
        # Once the open question is spent, an over-general pool still benefits
        # from the deterministic next eligible targeted facet.
        return unasked[0] if over_general and unasked else None

    def _expected_value_choice(
        self,
        state: SessionState,
        candidates: list[Candidate],
        over_general: bool,
        recommendation_limit: int,
    ) -> AskAttribute | None:
        covered = self._covered(state) if self.config.skip_covered_attributes else set()
        unasked = [
            attribute for attribute in self._sequence
            if attribute not in state.asked_attributes
            and attribute not in state.declined_attributes
            and attribute not in covered
        ]
        if self.catalog is not None and unasked:
            values = score_question_values(
                self.catalog,
                self._pool(candidates),
                active_values={
                    attribute: self._active_values(state, attribute)
                    for attribute in self._sequence
                },
                recommendation_limit=recommendation_limit,
            )
            value, _, attribute = max(
                (values[name], -index, name)
                for index, name in enumerate(unasked)
            )
            if value > 0.0:
                return attribute
        if not over_general and unasked:
            return unasked[0]
        if (
            "other" not in state.asked_attributes
            and "other" not in state.declined_attributes
        ):
            return "other"
        return unasked[0] if over_general and unasked else None

    def _dense_for_embedding_promotion(self) -> DenseRetriever | None:
        """Build (once) or reuse a DenseRetriever purely for its embedding
        matrix and encoder, independent of self.catalog's retrieval-mode
        retriever. This never touches _gain()/_information_gain() or the
        catalog's discrete facet index -- it is a separate signal entirely.
        """
        if self._embedding_dense_attempted:
            return self._embedding_dense
        self._embedding_dense_attempted = True
        if self.catalog is None:
            return None
        try:
            self._embedding_dense = DenseRetriever(
                self.catalog, text_recipe=self.config.dense_text_recipe,
            )
        except DenseUnavailable:
            self._embedding_dense = None
        return self._embedding_dense

    def _embedding_choice(
        self,
        state: SessionState,
        candidates: list[Candidate],
        over_general: bool,
        recommendation_limit: int,
    ) -> AskAttribute | None:
        """Ask about whichever unasked attribute's question text is most
        similar, by embedding, to the near-miss pool -- candidates ranked
        recommendation_limit..EMBEDDING_PROMOTION_WINDOW of the pre-truncation
        pool, the ones just past this turn's response cutoff. The intent is
        that the answer has the best chance of promoting a real near-miss
        into next turn's Top-K, without touching Top-K membership itself.

        Only acts on an over-general pool: if the boundary is already sharp
        there is no ambiguous near-miss zone this mode is meant to target,
        and it defers to going silent rather than guessing an attribute for
        a reason unrelated to its own rationale.
        """
        if not over_general:
            return None
        candidate_attributes: list[AskAttribute] = [
            attribute for attribute in self._sequence
            if attribute not in state.asked_attributes
            and attribute not in state.declined_attributes
        ]
        if (
            "other" not in state.asked_attributes
            and "other" not in state.declined_attributes
        ):
            candidate_attributes.append("other")
        if not candidate_attributes:
            return None

        dense = self._dense_for_embedding_promotion()
        if dense is None:
            return candidate_attributes[0]

        ordered = sorted(candidates, key=lambda item: (-item.score, item.asin))
        near_miss = ordered[recommendation_limit:EMBEDDING_PROMOTION_WINDOW]
        pool_vectors = [
            vector for vector in (dense.embedding_for(item.asin) for item in near_miss)
            if vector is not None
        ]
        if not pool_vectors:
            return candidate_attributes[0]

        import numpy as np

        pool_matrix = np.asarray(pool_vectors)
        texts = [self.message(attribute, over_general=False) for attribute in candidate_attributes]
        question_vectors = dense.encode_texts(texts)
        mean_similarity = (question_vectors @ pool_matrix.T).mean(axis=1)
        best_index = int(np.argmax(mean_similarity))
        return candidate_attributes[best_index]

    def choose(
        self,
        state: SessionState,
        candidates: list[Candidate],
        over_general: bool = True,
        recommendation_limit: int = 10,
    ) -> AskAttribute | None:
        if self.config.clarification == "off":
            return None
        # A refusal retires only that attribute; the shopper answers normally
        # afterwards, so the policy must keep asking about everything else.
        if self.config.clarification == "info_gain":
            return self._information_choice(state, candidates, over_general)
        if self.config.clarification == "expected_value":
            return self._expected_value_choice(
                state,
                candidates,
                over_general,
                recommendation_limit,
            )
        if self.config.clarification == "embedding_promotion":
            return self._embedding_choice(
                state,
                candidates,
                over_general,
                recommendation_limit,
            )
        return self._fixed_choice(state)

    @staticmethod
    def is_over_general(candidates: list[Candidate], recommendation_limit: int) -> bool:
        """Detect a crowded relevance boundary rather than raw over-fetch depth.

        Hard-constraint violations are excluded first.  Among the remaining
        candidates, the response boundary is ambiguous when its score gap is no
        sharper than the pool's mean adjacent gap.  This turns off after a real
        constraint-induced separation and avoids defining the agent's chosen
        retrieval depth as customer ambiguity.
        """
        if recommendation_limit <= 0:
            return False
        scores = sorted(
            (candidate.score for candidate in candidates if _satisfies_hard_constraints(candidate)),
            reverse=True,
        )
        if len(scores) <= recommendation_limit:
            return False
        span = scores[0] - scores[-1]
        if span <= 0.0:
            return True
        mean_gap = span / (len(scores) - 1)
        boundary_gap = max(0.0, scores[recommendation_limit - 1] - scores[recommendation_limit])
        return boundary_gap <= mean_gap + 1e-12

    @staticmethod
    def message(attribute: AskAttribute | None, over_general: bool = False) -> str:
        if attribute is None:
            return "Here are the closest matches based on what you shared."
        prefix = "I found many plausible matches. " if over_general else ""
        if attribute == "other":
            return prefix + "Is there another requirement that would help narrow these options?"
        return prefix + f"Do you have a {attribute.replace('_', ' ')} preference?"

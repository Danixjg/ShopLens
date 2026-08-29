from __future__ import annotations

from src.attributes import ascii_tokens, classify_attribute
from src.catalog import Catalog
from src.contracts.config import PROFILE_RERANK_WEIGHT
from src.contracts.retrieval import Candidate
from src.contracts.state import SessionState
# Reuse the clarification policy's constraint predicate rather than copying it.
# Two independent implementations of one safety rule can drift apart, and this
# is the rule that stops a prior from promoting a violating product.
from src.policy.clarification import _satisfies_hard_constraints


# Small predeclared grid; the shipped configuration records its selection.
ALLOWED_PROFILE_WEIGHTS = frozenset((0.02, 0.05, 0.08, 0.12))
MAX_TAG_TOKENS = 8


def _matches(tokens: frozenset[str], tag: tuple[str, ...]) -> bool:
    return all(token in tokens for token in tag)


class ProfileReranker:
    """Apply bounded profile evidence to frozen Top-K membership.

    A profile is prior belief about the shopper, not a requirement they stated
    this session, so it is deliberately the weakest signal in the chain:

    * It receives only the already-selected Top-K and cannot add or remove a
      product, so Hit Rate@10 is unreachable from here and only rank can move.
    * A tag is discarded once the shopper has spoken to that attribute. Someone
      who asked for cotton has superseded a generic ``material`` leaning.
    * A candidate violating a disclosed hard constraint earns nothing, so the
      prior can never lift a product the customer ruled out.
    """

    def __init__(self, catalog: Catalog, weight: float = PROFILE_RERANK_WEIGHT) -> None:
        if weight not in ALLOWED_PROFILE_WEIGHTS:
            raise ValueError(
                f"profile rerank weight must be one of {sorted(ALLOWED_PROFILE_WEIGHTS)}"
            )
        self.catalog = catalog
        self.weight = weight

    @staticmethod
    def _disclosed_attributes(state: SessionState) -> set[str]:
        return {slot.attribute for slot in state.slots if slot.active}

    def _usable_tags(self, state: SessionState) -> tuple[tuple[str, ...], ...]:
        """Profile tags that the current turn has not already superseded."""
        profile = state.user_profile
        if profile is None:
            return ()
        disclosed = self._disclosed_attributes(state)
        tags: list[tuple[str, ...]] = []
        seen: set[tuple[str, ...]] = set()
        for tag in profile.preference_tags:
            if classify_attribute(tag) in disclosed:
                continue
            tokens = ascii_tokens(tag)[:MAX_TAG_TOKENS]
            if tokens and tokens not in seen:
                seen.add(tokens)
                tags.append(tokens)
        return tuple(tags)

    def rerank(
        self,
        state: SessionState,
        candidates: list[Candidate],
        pool: list[Candidate],
    ) -> list[Candidate]:
        if not candidates:
            return candidates
        tags = self._usable_tags(state)
        if not tags:
            return candidates

        pool_tokens: dict[str, frozenset[str]] = {}
        for candidate in pool:
            product = self.catalog.get(candidate.asin)
            if product is not None and candidate.asin not in pool_tokens:
                pool_tokens[candidate.asin] = frozenset(ascii_tokens(product.searchable_text))
        pool_size = len(pool_tokens)

        # Pool-local rarity: a tag matching every product separates nothing, and
        # one matching none carries no evidence either.
        frequency = {
            tag: sum(1 for tokens in pool_tokens.values() if _matches(tokens, tag))
            for tag in tags
        }
        selective = {
            tag: count for tag, count in frequency.items() if 0 < count < pool_size
        }

        evidence: list[float] = []
        for candidate in candidates:
            if not _satisfies_hard_constraints(candidate):
                evidence.append(0.0)
                continue
            tokens = pool_tokens.get(candidate.asin, frozenset())
            evidence.append(sum(
                1.0 / count
                for tag, count in selective.items()
                if _matches(tokens, tag)
            ))
        maximum = max(evidence, default=0.0)

        ranked: list[tuple[float, int, Candidate]] = []
        for original_rank, (candidate, raw) in enumerate(zip(candidates, evidence), start=1):
            profile_norm = raw / maximum if maximum > 0.0 else 0.0
            bonus = self.weight * profile_norm / 61
            final = candidate.score + bonus
            components = {
                **candidate.components,
                "profile_evidence": raw,
                "profile_norm": profile_norm,
                "profile_rank_bonus": bonus,
            }
            ranked.append((
                final,
                original_rank,
                Candidate(candidate.asin, final, components),
            ))

        ranked.sort(key=lambda item: (-item[0], item[1], item[2].asin))
        return [candidate for _score, _rank, candidate in ranked]

from __future__ import annotations

from src.attributes import ascii_tokens
from src.catalog import Catalog
from src.contracts.retrieval import Candidate
from src.contracts.state import SessionState


MAX_PHRASE_TOKENS = 32
# Selected once on the 120-session dev split from ALLOWED_LAMBDAS.  Holdout is
# not used to revise this value.
PHRASE_RERANK_WEIGHT = 0.15
ALLOWED_LAMBDAS = frozenset((0.05, 0.10, 0.15, 0.20))


def _tokens(value: str) -> tuple[str, ...]:
    return ascii_tokens(value)


def _slot_phrases(state: SessionState) -> tuple[tuple[str, ...], ...]:
    phrases: list[tuple[str, ...]] = []
    seen: set[tuple[str, ...]] = set()
    for slot in state.slots:
        if not slot.active:
            continue
        value = slot.value
        label, separator, remainder = value.partition(":")
        if separator and label.strip().casefold().replace(" ", "_") == slot.attribute:
            value = remainder
        phrase = _tokens(value)[:MAX_PHRASE_TOKENS]
        if phrase and phrase not in seen:
            seen.add(phrase)
            phrases.append(phrase)
    return tuple(phrases)


def _contains(tokens: tuple[str, ...], phrase: tuple[str, ...]) -> bool:
    width = len(phrase)
    return any(tokens[index:index + width] == phrase for index in range(len(tokens) - width + 1))


class PhraseReranker:
    """Rerank frozen membership using source phrases and pool-local rarity."""

    def __init__(self, catalog: Catalog, weight: float = PHRASE_RERANK_WEIGHT) -> None:
        if weight not in ALLOWED_LAMBDAS:
            raise ValueError(f"phrase rerank weight must be one of {sorted(ALLOWED_LAMBDAS)}")
        self.catalog = catalog
        self.weight = weight

    def rerank(
        self,
        state: SessionState,
        candidates: list[Candidate],
        pool: list[Candidate],
    ) -> list[Candidate]:
        if not candidates:
            return candidates
        phrases = _slot_phrases(state)
        if not phrases:
            return candidates

        pool_tokens: dict[str, tuple[str, ...]] = {}
        for candidate in pool:
            product = self.catalog.get(candidate.asin)
            if product is not None and candidate.asin not in pool_tokens:
                pool_tokens[candidate.asin] = _tokens(product.searchable_text)
        pool_size = len(pool_tokens)

        document_frequency = {
            phrase: sum(_contains(tokens, phrase) for tokens in pool_tokens.values())
            for phrase in phrases
        }
        selective = {
            phrase: frequency
            for phrase, frequency in document_frequency.items()
            if 0 < frequency < pool_size
        }

        evidence: list[float] = []
        for candidate in candidates:
            tokens = pool_tokens.get(candidate.asin, ())
            evidence.append(sum(
                1.0 / frequency
                for phrase, frequency in selective.items()
                if _contains(tokens, phrase)
            ))
        max_evidence = max(evidence, default=0.0)

        ranked: list[tuple[float, int, Candidate]] = []
        for base_rank, (candidate, raw_evidence) in enumerate(zip(candidates, evidence), start=1):
            phrase_norm = raw_evidence / max_evidence if max_evidence > 0.0 else 0.0
            final = 1.0 / (60 + base_rank) + self.weight * phrase_norm / 61
            components = {
                **candidate.components,
                "phrase_rarity": raw_evidence,
                "phrase_rank_bonus": self.weight * phrase_norm / 61,
            }
            ranked.append((final, base_rank, Candidate(candidate.asin, final, components)))
        ranked.sort(key=lambda item: (-item[0], item[1], item[2].asin))
        return [candidate for _score, _rank, candidate in ranked]

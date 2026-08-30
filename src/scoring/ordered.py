from __future__ import annotations

from src.attributes import ascii_tokens
from src.catalog import Catalog
from src.contracts.retrieval import Candidate
from src.contracts.state import SessionState


MAX_PHRASE_TOKENS = 32


def _phrase(value: str, attribute: str) -> tuple[str, ...]:
    """Tokenise a slot value, dropping the evaluator's ``color:`` style label."""
    label, separator, remainder = value.partition(":")
    if separator and label.strip().casefold().replace(" ", "_") == attribute:
        value = remainder
    return ascii_tokens(value)[:MAX_PHRASE_TOKENS]


def disclosed_phrases(state: SessionState) -> tuple[tuple[str, ...], ...]:
    """Active slot phrases in the order the shopper disclosed them."""
    active = sorted(
        (slot for slot in state.slots if slot.active),
        key=lambda slot: (slot.source_turn, slot.updated_at),
    )
    phrases: list[tuple[str, ...]] = []
    seen: set[tuple[str, ...]] = set()
    for slot in active:
        phrase = _phrase(slot.value, slot.attribute)
        if phrase and phrase not in seen:
            seen.add(phrase)
            phrases.append(phrase)
    return tuple(phrases)


def contains(tokens: tuple[str, ...], phrase: tuple[str, ...]) -> bool:
    """Whether ``phrase`` appears in ``tokens`` as a contiguous run."""
    width = len(phrase)
    return any(tokens[index:index + width] == phrase for index in range(len(tokens) - width + 1))


class OrderedConstraintReranker:
    """Rank a frozen Top-K by which disclosures a candidate satisfies.

    The phrase reranker sums inverse pool frequency, so a candidate matching
    two common disclosures can outrank one matching every disclosure. Ranking
    lexicographically removes that trade: satisfying more of what the shopper
    actually said always wins, and the disclosure order only breaks ties among
    candidates that satisfy different subsets.

    Membership is preserved. This reorders the frozen set and never adds to it.
    """

    def __init__(self, catalog: Catalog) -> None:
        self.catalog = catalog
        self._token_cache: dict[str, tuple[str, ...]] = {}

    def _tokens(self, asin: str) -> tuple[str, ...]:
        cached = self._token_cache.get(asin)
        if cached is None:
            product = self.catalog.get(asin)
            cached = ascii_tokens(product.searchable_text) if product is not None else ()
            self._token_cache[asin] = cached
        return cached

    def rerank(self, state: SessionState, candidates: list[Candidate]) -> list[Candidate]:
        if not candidates:
            return candidates
        phrases = disclosed_phrases(state)
        if not phrases:
            return candidates

        ranked: list[tuple[tuple[int, ...], int, Candidate]] = []
        for base_rank, candidate in enumerate(candidates, start=1):
            tokens = self._tokens(candidate.asin)
            # 0 sorts before 1, so a satisfied leading disclosure wins outright
            # and the rest only separate candidates it could not.
            matches = tuple(0 if contains(tokens, phrase) else 1 for phrase in phrases)
            ranked.append((matches, base_rank, candidate))
        ranked.sort(key=lambda item: (item[0], item[1], item[2].asin))

        # Rebuild scores from position, on the same reciprocal-rank scale the
        # retriever and the popularity prior already share.
        return [
            Candidate(
                candidate.asin,
                1.0 / (60 + position),
                {
                    **candidate.components,
                    "ordered_matches": float(len(phrases) - sum(matches)),
                    "ordered_rank": float(position),
                },
            )
            for position, (matches, _base_rank, candidate) in enumerate(ranked, start=1)
        ]

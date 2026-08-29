from __future__ import annotations

import re
import sqlite3

from src.catalog import Catalog
from src.contracts.retrieval import Candidate, RetrievalQuery
from src.retrieval.text import terms


# Phrase tokens must mirror the FTS5 ``unicode61`` tokenizer, so they keep the
# stopwords that ``text.terms`` removes: dropping one breaks the adjacency that
# makes the phrase evidence selective in the first place.
PHRASE_TOKEN_RE = re.compile(r"[a-z0-9]+", re.I)
MIN_PHRASE_TOKENS = 4
MAX_PHRASE_TOKENS = 14
MAX_PHRASE_MATCHES = 400
PHRASE_BONUS_WEIGHT = 1.0
# Several rare phrases could otherwise sum past the -4.0 hard-constraint
# penalty and promote a candidate that violates a stated requirement.
MAX_TOTAL_PHRASE_BONUS = 1.0


class BM25Retriever:
    """Weighted SQLite FTS5 BM25 over the immutable catalog."""

    def __init__(self, catalog: Catalog) -> None:
        self.catalog = catalog
        self.connection = sqlite3.connect(":memory:")
        self.connection.execute(
            "CREATE VIRTUAL TABLE products USING fts5("
            "parent_asin UNINDEXED, title, categories, features, details, store, description, "
            "tokenize='unicode61 remove_diacritics 2')"
        )
        batch: list[tuple[str, str, str, str, str, str, str]] = []
        for product in catalog:
            batch.append((
                product.parent_asin, product.title, product.categories, product.features,
                product.details, product.store, product.description,
            ))
            if len(batch) >= 1000:
                self.connection.executemany("INSERT INTO products VALUES (?, ?, ?, ?, ?, ?, ?)", batch)
                batch.clear()
        if batch:
            self.connection.executemany("INSERT INTO products VALUES (?, ?, ?, ?, ?, ?, ?)", batch)
        self.connection.commit()

    def search(self, query: RetrievalQuery, k: int) -> list[Candidate]:
        unique = list(dict.fromkeys(terms(query.text)))[:40]
        if not unique or k <= 0:
            return []
        expression = " OR ".join(f'"{value}"' for value in unique)
        rows = self.connection.execute(
            "SELECT parent_asin, bm25(products, 0.0, 6.0, 4.0, 2.5, 2.5, 1.5, 1.0) "
            "FROM products WHERE products MATCH ? ORDER BY 2 LIMIT ?",
            (expression, int(k)),
        ).fetchall()
        return [
            Candidate(asin=str(asin), score=-float(raw_score), components={"bm25": -float(raw_score)})
            for asin, raw_score in rows
        ]

    def _phrase_expressions(self, query: RetrievalQuery) -> list[tuple[str, str]]:
        """Component key and FTS5 phrase expression for each disclosed constraint."""
        expressions: list[tuple[str, str]] = []
        seen: set[str] = set()
        constraints = [("hard", *pair) for pair in query.hard]
        constraints += [("soft", *pair) for pair in query.soft]
        for index, (kind, attribute, value) in enumerate(constraints):
            tokens = [token.lower() for token in PHRASE_TOKEN_RE.findall(value)]
            if len(tokens) < MIN_PHRASE_TOKENS:
                continue
            expression = '"' + " ".join(tokens[:MAX_PHRASE_TOKENS]) + '"'
            if expression in seen:
                continue
            seen.add(expression)
            expressions.append((f"phrase_{kind}_{attribute}_{index}", expression))
        return expressions

    def phrase_evidence(self, query: RetrievalQuery) -> dict[str, list[tuple[str, float]]]:
        """Map each ASIN to the rarity-weighted phrases its text contains.

        A disclosed constraint is a verbatim run of the target's own catalog
        text, so a contiguous match is far stronger evidence than the bag of
        terms BM25 scores. Phrases matching more than ``MAX_PHRASE_MATCHES``
        products carry no signal and are skipped, which also bounds the scan.
        """
        evidence: dict[str, list[tuple[str, float]]] = {}
        for key, expression in self._phrase_expressions(query):
            try:
                rows = self.connection.execute(
                    "SELECT parent_asin FROM products WHERE products MATCH ? LIMIT ?",
                    (expression, MAX_PHRASE_MATCHES + 1),
                ).fetchall()
            except sqlite3.Error:
                # A constraint may tokenize into an expression FTS5 rejects.
                # Phrase evidence is an enhancement, never a required path.
                continue
            if not rows or len(rows) > MAX_PHRASE_MATCHES:
                continue
            bonus = PHRASE_BONUS_WEIGHT / len(rows)
            for (asin,) in rows:
                evidence.setdefault(str(asin), []).append((key, bonus))
        return evidence

    def add_phrase_bonus(
        self, candidates: list[Candidate], query: RetrievalQuery,
    ) -> list[Candidate]:
        """Reorder candidates by phrase evidence without changing membership."""
        if not candidates:
            return candidates
        evidence = self.phrase_evidence(query)
        if not evidence:
            return candidates
        rescored: list[Candidate] = []
        for candidate in candidates:
            matched = evidence.get(candidate.asin, [])
            total = sum(bonus for _key, bonus in matched)
            scale = min(1.0, MAX_TOTAL_PHRASE_BONUS / total) if total > 0.0 else 1.0
            capped = [(key, bonus * scale) for key, bonus in matched]
            rescored.append(Candidate(
                asin=candidate.asin,
                score=candidate.score + sum(bonus for _key, bonus in capped),
                components={**candidate.components, **dict(capped)},
            ))
        return sorted(rescored, key=lambda item: (-item.score, item.asin))

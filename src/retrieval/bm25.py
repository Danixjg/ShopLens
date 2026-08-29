from __future__ import annotations

import sqlite3

from src.catalog import Catalog
from src.contracts.retrieval import Candidate, RetrievalQuery
from src.retrieval.text import terms


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

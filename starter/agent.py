from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)

# Clarification sequence: feature → material → color, then fall back to "other".
# After all targeted attributes are asked once, only "other" is used.
CLARIFICATION_SEQUENCE: tuple[str, ...] = ("feature", "material", "color")
# Keep this constant for backward compatibility with existing tests.
CLARIFICATION_CYCLE: tuple[str, ...] = ("feature", "material", "color")

# Exact deterministic override marker (published in evaluation spec).
OVERRIDE_MARKER = "Actually, ignore my earlier preference. What I need is:"

# Fallback catalog ASINs returned when no BM25 results are found and no prior
# session results exist.  These are the first 10 products in insertion order.
_FALLBACK_LIMIT = 10
_TOP_K_MIN = 1
_TOP_K_MAX = 10

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "from",
    "i", "in", "is", "it", "me", "my", "of", "on", "or", "please", "some",
    "that", "the", "this", "to", "want", "with", "would", "you", "looking",
}


def _text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        return " ".join(f"{key} {item}" for key, item in value.items())
    if isinstance(value, list):
        return " ".join(str(item) for item in value)
    return str(value)


def _terms(text: str) -> list[str]:
    return [
        token.lower()
        for token in TOKEN_RE.findall(text)
        if len(token) > 1 and token.lower() not in STOPWORDS
    ]


def _clamp_top_k(top_k: int) -> int:
    """Clamp top_k to the contract-safe range [1, 10]."""
    return max(_TOP_K_MIN, min(_TOP_K_MAX, top_k))


@dataclass
class _SessionState:
    """Per-session mutable state."""
    # Accumulated active query text (concatenation of all message chunks after override handling).
    active_query: str = ""
    # Which targeted attributes have already been asked.
    asked_attributes: list[str] = field(default_factory=list)
    # Last non-empty recommendation list from any previous turn.
    last_non_empty: list[dict] = field(default_factory=list)


class Agent:
    """Stateful BM25 retrieval with override detection and safe fallbacks."""

    def __init__(self, catalog_path: str | Path = "data/catalog.jsonl") -> None:
        self.catalog_path = Path(catalog_path)
        self.connection = sqlite3.connect(":memory:")
        self._sessions: dict[str, _SessionState] = {}
        self._build_index()
        # Eagerly cache the fallback list once the index is built.
        self._fallback_list: list[dict] = self._build_fallback()

    def _build_index(self) -> None:
        cursor = self.connection.cursor()
        cursor.execute(
            "CREATE VIRTUAL TABLE products USING fts5("
            "parent_asin UNINDEXED, title, categories, features, details, store, description, "
            "tokenize='unicode61 remove_diacritics 2')"
        )
        batch: list[tuple[str, str, str, str, str, str, str]] = []
        with self.catalog_path.open(encoding="utf-8") as handle:
            for line in handle:
                product = json.loads(line)
                batch.append(
                    (
                        str(product["parent_asin"]),
                        _text(product.get("title")),
                        _text(product.get("categories")),
                        _text(product.get("features")),
                        _text(product.get("details")),
                        _text(product.get("store")),
                        _text(product.get("description")),
                    )
                )
                if len(batch) >= 1000:
                    cursor.executemany("INSERT INTO products VALUES (?, ?, ?, ?, ?, ?, ?)", batch)
                    batch.clear()
        if batch:
            cursor.executemany("INSERT INTO products VALUES (?, ?, ?, ?, ?, ?, ?)", batch)
        self.connection.commit()

    def _build_fallback(self) -> list[dict]:
        """Return the first _FALLBACK_LIMIT products from the catalog (insertion order)."""
        rows = self.connection.execute(
            "SELECT parent_asin FROM products LIMIT ?",
            (_FALLBACK_LIMIT,),
        ).fetchall()
        return [{"parent_asin": str(row[0])} for row in rows]

    def reset(self, session_id: str, user_profile: dict) -> None:
        """Initialise (or reinitialise) a session.  user_profile is anonymised."""
        self._sessions[session_id] = _SessionState()

    def _next_ask_attribute(self, state: _SessionState) -> str:
        """Return the next clarification attribute to ask.

        Sequence: feature → material → color; after all three are asked, use "other".
        """
        for attr in CLARIFICATION_SEQUENCE:
            if attr not in state.asked_attributes:
                return attr
        return "other"

    def _bm25_search(self, query: str, top_k: int) -> list[dict]:
        """Run BM25 search and return up to top_k results."""
        unique_terms = list(dict.fromkeys(_terms(query)))[:40]
        if not unique_terms:
            return []
        expression = " OR ".join(f'"{term}"' for term in unique_terms)
        rows = self.connection.execute(
            "SELECT parent_asin FROM products WHERE products MATCH ? "
            "ORDER BY bm25(products, 0.0, 6.0, 4.0, 2.5, 2.5, 1.5, 1.0) LIMIT ?",
            (expression, top_k),
        ).fetchall()
        return [{"parent_asin": str(row[0])} for row in rows]

    def respond(
        self,
        session_id: str,
        user_message: str,
        turn: int,
        top_k: int,
    ) -> dict:
        if session_id not in self._sessions:
            raise RuntimeError("reset must be called before respond")

        # Clamp top_k and validate turn to contract-safe bounds.
        safe_k = _clamp_top_k(top_k)
        # Turn is expected 1-10; clamp to avoid negative modular surprises.
        safe_turn = max(1, turn)

        state = self._sessions[session_id]

        # ── Override detection ──────────────────────────────────────────────
        # If the exact published marker is present, discard all prior query
        # text and use only the text that follows the marker.
        if OVERRIDE_MARKER in user_message:
            after_marker = user_message[user_message.index(OVERRIDE_MARKER) + len(OVERRIDE_MARKER):]
            state.active_query = after_marker.strip()
        else:
            # Ordinary turn: accumulate message into the active query.
            if state.active_query:
                state.active_query = state.active_query + " " + user_message
            else:
                state.active_query = user_message

        # ── BM25 retrieval on accumulated query ─────────────────────────────
        recommendations = self._bm25_search(state.active_query, safe_k)

        # ── Fallback chain ──────────────────────────────────────────────────
        # 1. BM25 results (already populated above).
        # 2. Session's last non-empty results (re-capped to safe_k).
        # 3. Deterministic catalog fallback capped at safe_k.
        if not recommendations:
            if state.last_non_empty:
                recommendations = state.last_non_empty[:safe_k]
            else:
                recommendations = self._fallback_list[:safe_k]

        # Update session's last non-empty results.
        if recommendations:
            state.last_non_empty = recommendations

        # ── Clarification attribute ─────────────────────────────────────────
        ask_attribute = self._next_ask_attribute(state)
        # Record this attribute as asked so it won't repeat.
        if ask_attribute != "other" and ask_attribute not in state.asked_attributes:
            state.asked_attributes.append(ask_attribute)

        return {
            "message": "Here are the closest matches I found.",
            "ask_attribute": ask_attribute,
            "recommendations": recommendations,
            "usage": {"prompt_tokens": 0, "completion_tokens": 0},
        }

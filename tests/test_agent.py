"""
Focused tests for starter/agent.py — deterministic clarification cycling.

Uses a tiny temporary catalog so no released data asset is required.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from starter.agent import Agent, CLARIFICATION_CYCLE

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CATALOG_ROWS = [
    {
        "parent_asin": "P001",
        "title": "Blue cotton running shoe",
        "categories": ["Clothing", "Shoes"],
        "features": ["lightweight", "breathable"],
        "details": {"department": "unisex"},
        "store": "SportShop",
        "description": ["great for running"],
    },
    {
        "parent_asin": "P002",
        "title": "Black leather winter boot",
        "categories": ["Clothing", "Boots"],
        "features": ["waterproof", "insulated"],
        "details": {"department": "womens"},
        "store": "BootWorld",
        "description": ["warm winter boot"],
    },
    {
        "parent_asin": "P003",
        "title": "Red polyester hiking jacket",
        "categories": ["Clothing", "Jackets"],
        "features": ["windproof", "durable"],
        "details": {"department": "mens"},
        "store": "OutdoorGear",
        "description": ["ideal for hiking"],
    },
]

_PROFILE = {
    "purchase_frequency": "monthly",
    "average_prior_rating": 4.2,
    "rating_style": "critical",
    "preference_tags": ["outdoor", "sport"],
    "summary": "Active outdoor shopper",
}


def _make_agent() -> tuple[Agent, str]:
    """Create an Agent backed by a tiny temp catalog and return (agent, tmpdir)."""
    tmpdir = tempfile.mkdtemp()
    catalog_path = Path(tmpdir) / "catalog.jsonl"
    catalog_path.write_text(
        "".join(json.dumps(row) + "\n" for row in _CATALOG_ROWS), encoding="utf-8"
    )
    return Agent(catalog_path), tmpdir


# ---------------------------------------------------------------------------
# Tests: clarification attribute cycle
# ---------------------------------------------------------------------------


class TestClarificationCycle(unittest.TestCase):
    def setUp(self) -> None:
        self.agent, _ = _make_agent()
        self.agent.reset("s1", _PROFILE)

    def test_turn1_returns_feature(self) -> None:
        response = self.agent.respond("s1", "I want a shoe", turn=1, top_k=10)
        self.assertEqual(response["ask_attribute"], "feature")

    def test_turn2_returns_material(self) -> None:
        response = self.agent.respond("s1", "I want a shoe", turn=2, top_k=10)
        self.assertEqual(response["ask_attribute"], "material")

    def test_turn3_returns_color(self) -> None:
        response = self.agent.respond("s1", "I want a shoe", turn=3, top_k=10)
        self.assertEqual(response["ask_attribute"], "color")

    def test_three_turn_attribute_order(self) -> None:
        """Exact sequence over turns 1–3 must be feature, material, color."""
        expected = ["feature", "material", "color"]
        actual = [
            self.agent.respond("s1", "I want shoes", turn=t, top_k=10)["ask_attribute"]
            for t in range(1, 4)
        ]
        self.assertEqual(actual, expected)

    def test_turn4_repeats_feature(self) -> None:
        """Turn 4 should cycle back to 'feature'."""
        response = self.agent.respond("s1", "show me more", turn=4, top_k=10)
        self.assertEqual(response["ask_attribute"], "feature")

    def test_turn5_repeats_material(self) -> None:
        response = self.agent.respond("s1", "show me more", turn=5, top_k=10)
        self.assertEqual(response["ask_attribute"], "material")

    def test_turn6_repeats_color(self) -> None:
        response = self.agent.respond("s1", "show me more", turn=6, top_k=10)
        self.assertEqual(response["ask_attribute"], "color")

    def test_cycle_repeats_deterministically(self) -> None:
        """Turns 1–9 should produce three full cycles of feature/material/color."""
        expected = (["feature", "material", "color"] * 3)
        actual = [
            self.agent.respond("s1", "test", turn=t, top_k=10)["ask_attribute"]
            for t in range(1, 10)
        ]
        self.assertEqual(actual, expected)


# ---------------------------------------------------------------------------
# Tests: interleaved sessions do not leak state
# ---------------------------------------------------------------------------


class TestInterleavedSessions(unittest.TestCase):
    def setUp(self) -> None:
        self.agent, _ = _make_agent()
        self.agent.reset("sA", _PROFILE)
        self.agent.reset("sB", _PROFILE)

    def test_interleaved_sessions_independent(self) -> None:
        """
        Calling respond on alternating sessions must not affect each other's
        attribute cycle — the cycle is purely turn-number-based and stateless.
        """
        # Both sessions, turn 1 → feature
        rA1 = self.agent.respond("sA", "shoe", turn=1, top_k=10)
        rB1 = self.agent.respond("sB", "boot", turn=1, top_k=10)
        self.assertEqual(rA1["ask_attribute"], "feature")
        self.assertEqual(rB1["ask_attribute"], "feature")

        # Both sessions, turn 2 → material
        rA2 = self.agent.respond("sA", "shoe", turn=2, top_k=10)
        rB2 = self.agent.respond("sB", "boot", turn=2, top_k=10)
        self.assertEqual(rA2["ask_attribute"], "material")
        self.assertEqual(rB2["ask_attribute"], "material")

    def test_high_turn_number_is_deterministic(self) -> None:
        """A turn > 3 always maps to the same attribute regardless of session."""
        # turn 7 → (7-1) % 3 = 0 → feature
        rA = self.agent.respond("sA", "jacket", turn=7, top_k=10)
        rB = self.agent.respond("sB", "jacket", turn=7, top_k=10)
        self.assertEqual(rA["ask_attribute"], "feature")
        self.assertEqual(rB["ask_attribute"], "feature")


# ---------------------------------------------------------------------------
# Tests: response structure
# ---------------------------------------------------------------------------


class TestResponseStructure(unittest.TestCase):
    def setUp(self) -> None:
        self.agent, _ = _make_agent()
        self.agent.reset("s1", _PROFILE)

    def test_response_has_string_message(self) -> None:
        response = self.agent.respond("s1", "running shoe", turn=1, top_k=10)
        self.assertIsInstance(response["message"], str)

    def test_ask_attribute_is_allowed(self) -> None:
        """ask_attribute must be one of the CLARIFICATION_CYCLE values (all in ALLOWED_ATTRIBUTES)."""
        allowed = {"category", "material", "color", "size", "style", "brand",
                   "budget", "feature", "use_case", "other"}
        for turn in range(1, 4):
            response = self.agent.respond("s1", "shoe", turn=turn, top_k=10)
            self.assertIn(response["ask_attribute"], allowed,
                          f"turn {turn}: unexpected ask_attribute {response['ask_attribute']!r}")

    def test_recommendations_are_ordered_objects(self) -> None:
        response = self.agent.respond("s1", "running shoe", turn=1, top_k=10)
        recs = response["recommendations"]
        self.assertIsInstance(recs, list)
        for rec in recs:
            self.assertIsInstance(rec, dict)
            self.assertIn("parent_asin", rec)
            self.assertIsInstance(rec["parent_asin"], str)

    def test_usage_non_negative(self) -> None:
        response = self.agent.respond("s1", "boot", turn=1, top_k=10)
        usage = response["usage"]
        self.assertGreaterEqual(usage["prompt_tokens"], 0)
        self.assertGreaterEqual(usage["completion_tokens"], 0)

    def test_zero_token_usage(self) -> None:
        """BM25 starter must return zero token usage."""
        response = self.agent.respond("s1", "jacket", turn=2, top_k=10)
        self.assertEqual(response["usage"]["prompt_tokens"], 0)
        self.assertEqual(response["usage"]["completion_tokens"], 0)

    def test_recommendations_capped_at_top_k(self) -> None:
        response = self.agent.respond("s1", "clothing", turn=1, top_k=2)
        self.assertLessEqual(len(response["recommendations"]), 2)

    def test_empty_query_returns_no_recommendations(self) -> None:
        """A message that strips to no terms should return an empty recommendations list."""
        # All stopwords → no search terms → empty results
        response = self.agent.respond("s1", "a the in", turn=1, top_k=10)
        self.assertEqual(response["recommendations"], [])
        # ask_attribute still cycles normally
        self.assertEqual(response["ask_attribute"], "feature")


# ---------------------------------------------------------------------------
# Tests: error path — respond before reset
# ---------------------------------------------------------------------------


class TestResetGuard(unittest.TestCase):
    def test_respond_before_reset_raises(self) -> None:
        agent, _ = _make_agent()
        with self.assertRaises(RuntimeError):
            agent.respond("unknown-session", "shoe", turn=1, top_k=10)


# ---------------------------------------------------------------------------
# Tests: CLARIFICATION_CYCLE constant is correct
# ---------------------------------------------------------------------------


class TestClarificationCycleConstant(unittest.TestCase):
    def test_cycle_has_exactly_three_entries(self) -> None:
        self.assertEqual(len(CLARIFICATION_CYCLE), 3)

    def test_cycle_order(self) -> None:
        self.assertEqual(tuple(CLARIFICATION_CYCLE), ("feature", "material", "color"))


if __name__ == "__main__":
    unittest.main()

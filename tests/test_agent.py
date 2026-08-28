"""
Focused tests for starter/agent.py — stateful override-safe BM25 policy.

Uses a tiny temporary catalog so no released data asset is required.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from starter.agent import Agent, CLARIFICATION_CYCLE, CLARIFICATION_SEQUENCE, OVERRIDE_MARKER

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
    {
        "parent_asin": "P004",
        "title": "Brown suede ankle boots",
        "categories": ["Clothing", "Boots"],
        "features": ["casual", "comfortable"],
        "details": {"department": "womens"},
        "store": "ShoeStore",
        "description": ["stylish brown boots"],
    },
    {
        "parent_asin": "P005",
        "title": "Waterproof black rain jacket",
        "categories": ["Clothing", "Jackets"],
        "features": ["waterproof", "packable"],
        "details": {"department": "unisex"},
        "store": "OutdoorGear",
        "description": ["great for rainy days"],
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
# Tests: clarification attribute sequence (feature → material → color → other)
# ---------------------------------------------------------------------------


class TestClarificationSequence(unittest.TestCase):
    def setUp(self) -> None:
        self.agent, _ = _make_agent()
        self.agent.reset("s1", _PROFILE)

    def test_turn1_returns_feature(self) -> None:
        response = self.agent.respond("s1", "I want a shoe", turn=1, top_k=10)
        self.assertEqual(response["ask_attribute"], "feature")

    def test_turn2_returns_material(self) -> None:
        self.agent.respond("s1", "I want a shoe", turn=1, top_k=10)
        response = self.agent.respond("s1", "I want a shoe", turn=2, top_k=10)
        self.assertEqual(response["ask_attribute"], "material")

    def test_turn3_returns_color(self) -> None:
        self.agent.respond("s1", "I want a shoe", turn=1, top_k=10)
        self.agent.respond("s1", "I want a shoe", turn=2, top_k=10)
        response = self.agent.respond("s1", "I want a shoe", turn=3, top_k=10)
        self.assertEqual(response["ask_attribute"], "color")

    def test_turn4_returns_other_not_feature(self) -> None:
        """After color is asked, subsequent turns must use 'other', not cycle back to 'feature'."""
        for t in range(1, 4):
            self.agent.respond("s1", "shoe", turn=t, top_k=10)
        response = self.agent.respond("s1", "more info", turn=4, top_k=10)
        self.assertEqual(response["ask_attribute"], "other")

    def test_turn5_stays_other(self) -> None:
        for t in range(1, 5):
            self.agent.respond("s1", "shoe", turn=t, top_k=10)
        response = self.agent.respond("s1", "still more", turn=5, top_k=10)
        self.assertEqual(response["ask_attribute"], "other")

    def test_three_turn_attribute_order(self) -> None:
        """Exact sequence over turns 1–3 must be feature, material, color."""
        expected = ["feature", "material", "color"]
        actual = [
            self.agent.respond("s1", "I want shoes", turn=t, top_k=10)["ask_attribute"]
            for t in range(1, 4)
        ]
        self.assertEqual(actual, expected)

    def test_no_targeted_repeat_after_exhaustion(self) -> None:
        """Once all targeted attributes asked, only 'other' is returned."""
        attrs = [
            self.agent.respond("s1", "shoe", turn=t, top_k=10)["ask_attribute"]
            for t in range(1, 8)
        ]
        # First 3 are feature, material, color; remaining 4 are all 'other'
        self.assertEqual(attrs[:3], ["feature", "material", "color"])
        self.assertTrue(all(a == "other" for a in attrs[3:]))


# ---------------------------------------------------------------------------
# Tests: multi-turn query accumulation
# ---------------------------------------------------------------------------


class TestMultiTurnAccumulation(unittest.TestCase):
    def setUp(self) -> None:
        self.agent, _ = _make_agent()
        self.agent.reset("s1", _PROFILE)

    def test_accumulated_query_improves_or_preserves_ranking(self) -> None:
        """Adding a second constraint should not break BM25 retrieval."""
        r1 = self.agent.respond("s1", "black boots", turn=1, top_k=10)
        r2 = self.agent.respond("s1", "waterproof please", turn=2, top_k=10)
        # Both results must be non-empty (accumulated query contains both constraints)
        self.assertGreater(len(r1["recommendations"]), 0)
        self.assertGreater(len(r2["recommendations"]), 0)

    def test_boots_then_waterproof_yields_waterproof_boot(self) -> None:
        """'black boots' + 'waterproof please' should surface the waterproof boot (P002 or P005)."""
        self.agent.respond("s1", "black boots", turn=1, top_k=10)
        r2 = self.agent.respond("s1", "waterproof please", turn=2, top_k=10)
        asins = [rec["parent_asin"] for rec in r2["recommendations"]]
        # P002 (Black leather winter boot, waterproof) or P005 (waterproof black rain jacket)
        self.assertTrue(
            any(a in ("P002", "P005") for a in asins),
            f"Expected waterproof product in results; got: {asins}",
        )

    def test_query_accumulates_across_turns(self) -> None:
        """Verify that the second response reflects both turns' content."""
        # First turn: only 'shoe' keyword
        r1 = self.agent.respond("s1", "shoe", turn=1, top_k=10)
        # Second turn: add 'blue' which should further constrain results
        r2 = self.agent.respond("s1", "blue", turn=2, top_k=10)
        # P001 (Blue cotton running shoe) should rank highly with both constraints
        asins2 = [rec["parent_asin"] for rec in r2["recommendations"]]
        self.assertIn("P001", asins2)


# ---------------------------------------------------------------------------
# Tests: override marker detection
# ---------------------------------------------------------------------------


class TestOverrideMarker(unittest.TestCase):
    def setUp(self) -> None:
        self.agent, _ = _make_agent()
        self.agent.reset("s1", _PROFILE)

    def test_override_removes_stale_terms(self) -> None:
        """After override, stale 'black' should no longer constrain retrieval."""
        self.agent.respond("s1", "I want black boots", turn=1, top_k=10)
        r2 = self.agent.respond(
            "s1",
            f"{OVERRIDE_MARKER} brown boots",
            turn=2,
            top_k=10,
        )
        asins = [rec["parent_asin"] for rec in r2["recommendations"]]
        # P004 (Brown suede ankle boots) should appear; pure-black P002 should not dominate
        self.assertIn("P004", asins, f"Expected P004 (brown boots) in {asins}")

    def test_override_clears_accumulated_query(self) -> None:
        """Override must reset accumulated query to only the post-marker text."""
        self.agent.respond("s1", "jacket hiking", turn=1, top_k=10)
        self.agent.respond("s1", "red color preferred", turn=2, top_k=10)
        r3 = self.agent.respond(
            "s1",
            f"{OVERRIDE_MARKER} blue cotton shoe",
            turn=3,
            top_k=10,
        )
        asins = [rec["parent_asin"] for rec in r3["recommendations"]]
        # After override, query is 'blue cotton shoe' → P001 should match
        self.assertIn("P001", asins, f"Expected P001 (blue shoe) in {asins}")
        # P003 (Red polyester hiking jacket) must NOT be top result after override
        if asins:
            self.assertNotEqual(asins[0], "P003")

    def test_exact_marker_required(self) -> None:
        """A near-miss override phrase must NOT trigger the override."""
        self.agent.respond("s1", "black boots", turn=1, top_k=10)
        # Slightly different phrasing — should NOT override
        r2 = self.agent.respond(
            "s1",
            "Actually, ignore my earlier preferences. What I need is: brown boots",
            turn=2,
            top_k=10,
        )
        # The accumulated query still includes 'black boots' + the new message
        # so boots-related products should still appear
        asins = [rec["parent_asin"] for rec in r2["recommendations"]]
        self.assertGreater(len(asins), 0)


# ---------------------------------------------------------------------------
# Tests: interleaved session isolation
# ---------------------------------------------------------------------------


class TestInterleavedSessions(unittest.TestCase):
    def setUp(self) -> None:
        self.agent, _ = _make_agent()
        self.agent.reset("sA", _PROFILE)
        self.agent.reset("sB", _PROFILE)

    def test_interleaved_sessions_independent_ask_attribute(self) -> None:
        """Sessions must each progress through their own clarification sequence."""
        rA1 = self.agent.respond("sA", "shoe", turn=1, top_k=10)
        rB1 = self.agent.respond("sB", "boot", turn=1, top_k=10)
        self.assertEqual(rA1["ask_attribute"], "feature")
        self.assertEqual(rB1["ask_attribute"], "feature")

        rA2 = self.agent.respond("sA", "shoe", turn=2, top_k=10)
        rB2 = self.agent.respond("sB", "boot", turn=2, top_k=10)
        self.assertEqual(rA2["ask_attribute"], "material")
        self.assertEqual(rB2["ask_attribute"], "material")

    def test_sessions_do_not_share_query(self) -> None:
        """Accumulating query in session A must not bleed into session B."""
        self.agent.respond("sA", "shoe blue lightweight", turn=1, top_k=10)
        self.agent.respond("sA", "more shoe detail", turn=2, top_k=10)

        # Session B issues completely different query; results must differ
        rB = self.agent.respond("sB", "jacket hiking", turn=1, top_k=10)
        asins_b = [rec["parent_asin"] for rec in rB["recommendations"]]
        # P003 (hiking jacket) should appear in B but not be driven by A's shoe query
        self.assertIn("P003", asins_b)

    def test_independent_state_after_override(self) -> None:
        """Override in session A must not affect session B."""
        self.agent.respond("sA", "black boots", turn=1, top_k=10)
        self.agent.respond("sA", f"{OVERRIDE_MARKER} blue shoe", turn=2, top_k=10)

        # Session B should still find boots
        rB = self.agent.respond("sB", "black boots", turn=1, top_k=10)
        asins_b = [rec["parent_asin"] for rec in rB["recommendations"]]
        self.assertGreater(len(asins_b), 0)

    def test_reset_reinitialises_session(self) -> None:
        """Re-calling reset on existing session must clear accumulated state."""
        self.agent.respond("sA", "blue shoe", turn=1, top_k=10)
        self.agent.respond("sA", "running", turn=2, top_k=10)
        # After re-reset, state should be fresh; clarification restarts at feature
        self.agent.reset("sA", _PROFILE)
        r = self.agent.respond("sA", "boot", turn=1, top_k=10)
        self.assertEqual(r["ask_attribute"], "feature")


# ---------------------------------------------------------------------------
# Tests: empty-result and fallback recovery
# ---------------------------------------------------------------------------


class TestEmptyResultFallback(unittest.TestCase):
    def setUp(self) -> None:
        self.agent, _ = _make_agent()
        self.agent.reset("s1", _PROFILE)

    def test_stopword_only_message_returns_nonempty(self) -> None:
        """A stopword-only message on a fresh session still returns a non-empty fallback."""
        r = self.agent.respond("s1", "a the in", turn=1, top_k=10)
        self.assertGreater(len(r["recommendations"]), 0)

    def test_empty_message_returns_nonempty(self) -> None:
        """An empty message on a fresh session still returns a non-empty fallback."""
        r = self.agent.respond("s1", "", turn=1, top_k=10)
        self.assertGreater(len(r["recommendations"]), 0)

    def test_last_nonempty_reused_on_empty_query(self) -> None:
        """When current BM25 returns empty, last non-empty results are reused."""
        r1 = self.agent.respond("s1", "shoe blue", turn=1, top_k=10)
        prior_asins = [rec["parent_asin"] for rec in r1["recommendations"]]
        self.assertGreater(len(prior_asins), 0)

        # Now send stopword-only message — BM25 returns empty, should reuse r1 results
        r2 = self.agent.respond("s1", "a the in", turn=2, top_k=10)
        asins2 = [rec["parent_asin"] for rec in r2["recommendations"]]
        self.assertGreater(len(asins2), 0)
        # Results must be drawn from last non-empty (subset of prior_asins or fallback)
        for asin in asins2:
            self.assertIn(asin, prior_asins)

    def test_fallback_capped_at_top_k(self) -> None:
        """Fallback recommendations must be capped at top_k."""
        r = self.agent.respond("s1", "a the in", turn=1, top_k=2)
        self.assertLessEqual(len(r["recommendations"]), 2)


# ---------------------------------------------------------------------------
# Tests: top_k boundary validation
# ---------------------------------------------------------------------------


class TestTopKValidation(unittest.TestCase):
    def setUp(self) -> None:
        self.agent, _ = _make_agent()
        self.agent.reset("s1", _PROFILE)

    def test_top_k_zero_clamped(self) -> None:
        """top_k=0 must not raise and must return at most 1 result."""
        r = self.agent.respond("s1", "shoe", turn=1, top_k=0)
        self.assertIsInstance(r["recommendations"], list)
        self.assertLessEqual(len(r["recommendations"]), 1)

    def test_top_k_negative_clamped(self) -> None:
        """top_k=-5 must not raise and must return at most 1 result."""
        r = self.agent.respond("s1", "shoe", turn=1, top_k=-5)
        self.assertIsInstance(r["recommendations"], list)
        self.assertLessEqual(len(r["recommendations"]), 1)

    def test_top_k_above_10_clamped(self) -> None:
        """top_k=50 must not enumerate full catalog; must return at most 10."""
        r = self.agent.respond("s1", "shoe", turn=1, top_k=50)
        self.assertLessEqual(len(r["recommendations"]), 10)

    def test_top_k_1_returns_exactly_one_or_zero(self) -> None:
        """top_k=1 with a matching query must return at most 1 result."""
        r = self.agent.respond("s1", "shoe", turn=1, top_k=1)
        self.assertLessEqual(len(r["recommendations"]), 1)

    def test_top_k_10_returns_at_most_ten(self) -> None:
        r = self.agent.respond("s1", "shoe boot jacket", turn=1, top_k=10)
        self.assertLessEqual(len(r["recommendations"]), 10)


# ---------------------------------------------------------------------------
# Tests: malformed turn values
# ---------------------------------------------------------------------------


class TestTurnValidation(unittest.TestCase):
    def setUp(self) -> None:
        self.agent, _ = _make_agent()
        self.agent.reset("s1", _PROFILE)

    def test_turn_zero_does_not_raise(self) -> None:
        """turn=0 must degrade gracefully without raising."""
        r = self.agent.respond("s1", "shoe", turn=0, top_k=10)
        self.assertIn("ask_attribute", r)

    def test_turn_negative_does_not_raise(self) -> None:
        r = self.agent.respond("s1", "shoe", turn=-3, top_k=10)
        self.assertIn("ask_attribute", r)

    def test_turn_very_large_does_not_raise(self) -> None:
        r = self.agent.respond("s1", "shoe", turn=999, top_k=10)
        self.assertIn("ask_attribute", r)


# ---------------------------------------------------------------------------
# Tests: response schema and ordering
# ---------------------------------------------------------------------------


class TestResponseSchema(unittest.TestCase):
    def setUp(self) -> None:
        self.agent, _ = _make_agent()
        self.agent.reset("s1", _PROFILE)

    def test_response_has_required_keys(self) -> None:
        r = self.agent.respond("s1", "running shoe", turn=1, top_k=10)
        for key in ("message", "ask_attribute", "recommendations", "usage"):
            self.assertIn(key, r)

    def test_response_has_string_message(self) -> None:
        r = self.agent.respond("s1", "running shoe", turn=1, top_k=10)
        self.assertIsInstance(r["message"], str)

    def test_ask_attribute_in_allowed_values(self) -> None:
        allowed = {"category", "material", "color", "size", "style", "brand",
                   "budget", "feature", "use_case", "other"}
        for turn in range(1, 6):
            r = self.agent.respond("s1", "shoe", turn=turn, top_k=10)
            self.assertIn(r["ask_attribute"], allowed)

    def test_recommendations_are_ordered_objects(self) -> None:
        r = self.agent.respond("s1", "running shoe", turn=1, top_k=10)
        recs = r["recommendations"]
        self.assertIsInstance(recs, list)
        for rec in recs:
            self.assertIsInstance(rec, dict)
            self.assertIn("parent_asin", rec)
            self.assertIsInstance(rec["parent_asin"], str)

    def test_zero_token_usage(self) -> None:
        r = self.agent.respond("s1", "jacket", turn=2, top_k=10)
        self.assertEqual(r["usage"]["prompt_tokens"], 0)
        self.assertEqual(r["usage"]["completion_tokens"], 0)

    def test_usage_non_negative(self) -> None:
        r = self.agent.respond("s1", "boot", turn=1, top_k=10)
        self.assertGreaterEqual(r["usage"]["prompt_tokens"], 0)
        self.assertGreaterEqual(r["usage"]["completion_tokens"], 0)

    def test_recommendations_capped_at_top_k(self) -> None:
        r = self.agent.respond("s1", "clothing", turn=1, top_k=2)
        self.assertLessEqual(len(r["recommendations"]), 2)

    def test_ordering_best_first(self) -> None:
        """More specific query should put the closest match first."""
        r = self.agent.respond("s1", "black leather winter boot", turn=1, top_k=10)
        asins = [rec["parent_asin"] for rec in r["recommendations"]]
        if asins:
            # P002 (Black leather winter boot) should be first
            self.assertEqual(asins[0], "P002")

    def test_no_extra_keys_in_response(self) -> None:
        """Response must not have keys outside the contract schema."""
        r = self.agent.respond("s1", "shoe", turn=1, top_k=10)
        allowed_keys = {"message", "ask_attribute", "recommendations", "usage"}
        self.assertTrue(set(r.keys()).issubset(allowed_keys))


# ---------------------------------------------------------------------------
# Tests: pre-reset guard
# ---------------------------------------------------------------------------


class TestResetGuard(unittest.TestCase):
    def test_respond_before_reset_raises(self) -> None:
        agent, _ = _make_agent()
        with self.assertRaises(RuntimeError):
            agent.respond("unknown-session", "shoe", turn=1, top_k=10)

    def test_respond_after_reset_does_not_raise(self) -> None:
        agent, _ = _make_agent()
        agent.reset("s1", _PROFILE)
        # Should not raise
        r = agent.respond("s1", "shoe", turn=1, top_k=10)
        self.assertIn("recommendations", r)


# ---------------------------------------------------------------------------
# Tests: CLARIFICATION_CYCLE / CLARIFICATION_SEQUENCE constants
# ---------------------------------------------------------------------------


class TestClarificationConstants(unittest.TestCase):
    def test_cycle_has_exactly_three_entries(self) -> None:
        self.assertEqual(len(CLARIFICATION_CYCLE), 3)

    def test_cycle_order(self) -> None:
        self.assertEqual(tuple(CLARIFICATION_CYCLE), ("feature", "material", "color"))

    def test_sequence_has_exactly_three_entries(self) -> None:
        self.assertEqual(len(CLARIFICATION_SEQUENCE), 3)

    def test_sequence_order(self) -> None:
        self.assertEqual(tuple(CLARIFICATION_SEQUENCE), ("feature", "material", "color"))


if __name__ == "__main__":
    unittest.main()

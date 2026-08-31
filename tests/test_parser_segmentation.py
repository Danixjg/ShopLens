"""Disclosure segmentation must follow catalog values, not raw semicolons.

The simulator joins disclosed constraints with "; ", but catalog text uses ";"
as ordinary punctuation, so a single feature bullet can look like several
constraints. Splitting it inflates the ordered-rerank match vector and dilutes
the soft-term union that scores it.
"""

from __future__ import annotations

import json
import re
from dataclasses import fields
from pathlib import Path

import pytest

from evaluator.local_evaluator import (
    COLOR_RE,
    MATERIALS,
    _clean_constraint,
    _flatten_values as evaluator_flatten,
    intent_card,
)
from src.contracts.config import CONFIGS
from src.parsing.parser import TurnParser
from src.parsing.segmentation import (
    COLOR_TOKENS,
    CONSTRAINT_LIMIT,
    MATERIAL_TOKENS,
    _flatten_values,
    build_constraint_index,
    normalize_constraint,
    segment,
)

ROOT = Path(__file__).resolve().parents[1]
OFFICIAL_CATALOG = ROOT / "data/catalog.jsonl"

# Verbatim from catalog row B08P4SSFX4: one feature bullet, two semicolons.
COMPOUND = (
    "Solid colors: 100% Cotton; Heather Grey: 90% Cotton, 10% Polyester; "
    "All Other Heathers: 50% Cotton, 50% Polyester"
)
# Verbatim from B01LWOGORL: 71 characters, so length is not what breaks it.
SHORT_COMPOUND = "100-hour chronograph with lap & split times; month, day & date calendar"

ROWS = [
    {
        "parent_asin": "B08P4SSFX4",
        "title": "Grandma Tee",
        "features": [COMPOUND, "Imported", "Machine Wash"],
        "details": {"Package Dimensions": "10 x 10 x 2 inches; 8 Ounces"},
        "price": 19.99,
    },
    {
        "parent_asin": "B01LWOGORL",
        "title": "Chronograph Watch",
        "features": [SHORT_COMPOUND, "Gold-tone band"],
        "details": {},
        "price": 49.0,
    },
]


@pytest.fixture()
def index() -> frozenset[int]:
    return build_constraint_index(ROWS)


def _disclose(parser: TurnParser, *constraints: str):
    """Parse the exact message the simulator builds for these constraints."""
    message = "For that, what matters is: " + "; ".join(constraints) + "."
    parsed = parser.parse(message, turn=2)
    return [value for _attribute, value in (*parsed.hard_constraints, *parsed.soft_preferences)]


# --- the regression cases, verbatim from the public catalog ------------------

def test_compound_feature_bullet_stays_one_constraint(index: frozenset[int]) -> None:
    """Two semicolons inside one catalog value must not become three slots."""
    assert _disclose(TurnParser(index), COMPOUND) == [COMPOUND]


def test_short_compound_value_also_stays_whole(index: frozenset[int]) -> None:
    """71 characters: the trigger is the separator, not the length."""
    assert _disclose(TurnParser(index), SHORT_COMPOUND) == [SHORT_COMPOUND]


def test_detail_value_with_a_semicolon_stays_whole(index: frozenset[int]) -> None:
    value = "Package Dimensions: 10 x 10 x 2 inches; 8 Ounces"
    assert _disclose(TurnParser(index), value) == [value]


def test_two_genuine_constraints_still_split(index: frozenset[int]) -> None:
    assert _disclose(TurnParser(index), "Imported", "Machine Wash") == [
        "Imported", "Machine Wash",
    ]


def test_synthesized_material_token_splits_from_a_compound_value(index: frozenset[int]) -> None:
    """The simulator injects a bare material token that is in no feature list.

    Without it in the index the pair fails to validate and both constraints
    merge, trading an over-split for an under-split.
    """
    assert _disclose(TurnParser(index), "cotton", COMPOUND) == ["cotton", COMPOUND]


def test_synthesized_color_and_budget_are_known(index: frozenset[int]) -> None:
    assert _disclose(TurnParser(index), "color: grey", "Imported") == [
        "color: grey", "Imported",
    ]
    assert _disclose(TurnParser(index), "budget around $19.99", "Imported") == [
        "budget around $19.99", "Imported",
    ]


def test_unknown_compound_is_never_shattered(index: frozenset[int]) -> None:
    """A value absent from the index stays whole rather than fragmenting."""
    unknown = "Some phrase; another phrase"
    assert _disclose(TurnParser(index), unknown) == [unknown]


# --- the historical path must be untouched ----------------------------------

def test_without_an_index_every_semicolon_still_splits() -> None:
    """Config O builds no index, so its parsing must be bit-identical."""
    assert _disclose(TurnParser(), COMPOUND) == [
        "Solid colors: 100% Cotton",
        "Heather Grey: 90% Cotton, 10% Polyester",
        "All Other Heathers: 50% Cotton, 50% Polyester",
    ]


def test_submission_config_builds_no_index() -> None:
    assert CONFIGS["O"].catalog_grounded_segmentation is False


def test_config_m_is_o_plus_one_flag() -> None:
    differing = {
        item.name
        for item in fields(CONFIGS["M"])
        if getattr(CONFIGS["M"], item.name) != getattr(CONFIGS["O"], item.name)
    }
    assert differing == {"name", "catalog_grounded_segmentation"}


# --- parity with the simulator, which the runtime may not import ------------

def test_normalization_is_idempotent() -> None:
    """Lookups arrive already truncated; the index is built from raw values.

    The simulator finishes with rstrip(), so a cut at the limit can leave a
    trailing comma. If normalizing twice differed from normalizing once, a
    valid constraint would hash differently on each side and look unknown.
    """
    for value in (COMPOUND, SHORT_COMPOUND, "x" * 300, "trailing comma," + "y" * 300):
        once = normalize_constraint(value)
        assert normalize_constraint(once) == once


def test_normalization_agrees_on_raw_and_emitted_forms() -> None:
    """A constraint must hash the same whether built from the catalog or read
    back off the wire after the simulator has already cleaned it."""
    for row in ROWS:
        for value in (*row["features"], *evaluator_flatten(row["details"])):
            emitted = _clean_constraint(value, CONSTRAINT_LIMIT)
            assert normalize_constraint(emitted) == normalize_constraint(value)


def test_mirrored_vocabularies_match_the_simulator() -> None:
    assert set(MATERIAL_TOKENS) == set(MATERIALS)
    pattern = COLOR_RE.pattern
    assert set(COLOR_TOKENS) == set(re.findall(r"[a-z]+", pattern.split("(")[1].split(")")[0]))


def test_flatten_matches_the_simulator() -> None:
    cases: list[object] = [
        {"a": "1", "b": ["x", "y"], "c": "", "d": []},
        ["p", "", "q"],
        "plain",
        None,
        "",
    ]
    for case in cases:
        assert _flatten_values(case) == evaluator_flatten(case)


# --- the property test that would have caught this originally ---------------

@pytest.mark.skipif(
    not OFFICIAL_CATALOG.exists(),
    reason="official catalog is not committed; see README for the download step",
)
def test_public_intent_cards_round_trip_within_a_bounded_error() -> None:
    """Disclosures the simulator can build must parse back to what it sent.

    A small residue is irreducible: a two-constraint disclosure can coincide
    exactly with a catalog value that itself contains a semicolon, and neither
    reading is distinguishable from the text alone. Measured over 20,000 rows,
    preferring the split leaves 16 such misreads in 196,680 disclosures, against
    3,786 for the opposite preference. Under-splitting must stay at zero: it is
    the failure this change exists to avoid trading into.
    """
    raws = [json.loads(line) for line in OFFICIAL_CATALOG.open(encoding="utf-8")]
    valid = build_constraint_index(raws)
    exact = over = under = 0
    for raw in raws[:2000]:
        card = intent_card(raw)
        pool = [*card["hard_constraints"], *card["soft_preferences"]]
        sent_cases = [[value] for value in pool]
        sent_cases += [
            [pool[first], pool[second]]
            for first in range(len(pool))
            for second in range(first + 1, len(pool))
        ]
        for sent in sent_cases:
            got = len(segment("; ".join(sent), valid))
            if got == len(sent):
                exact += 1
            elif got > len(sent):
                over += 1
            else:
                under += 1

    total = exact + over + under
    assert total > 1000
    assert under == 0
    assert exact / total >= 0.999

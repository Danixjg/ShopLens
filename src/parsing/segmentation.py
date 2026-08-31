"""Catalog-grounded segmentation of a multi-constraint disclosure.

The simulator joins the constraints it discloses with ``"; "``, but catalog text
uses ``;`` as ordinary punctuation, so splitting on the separator shatters a
single field value into several constraints. ``Solid colors: 100% Cotton;
Heather Grey: 90% Cotton, 10% Polyester`` is one feature bullet, not two
preferences.

Every real constraint is a whole catalog field value, so the ambiguity is
resolvable: build the set of values the disclosure could have been assembled
from, and keep only a segmentation whose every part is one of them.

The disclosure carries at most two constraints, so at most one semicolon is a
true boundary. That bounds the search to one candidate per semicolon.

This module deliberately mirrors the simulator's constraint construction rather
than importing it: the agent must not depend on ``evaluator/`` at runtime. A
parity test pins the mirrored constants to the originals.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator

CONSTRAINT_LIMIT = 180

# Mirrors of the simulator's material and colour vocabularies. The simulator
# injects one lowercase material token and one ``color: <value>`` constraint
# that appear in no catalog field, so a segmentation grounded only in field
# values would reject them.
MATERIAL_TOKENS: tuple[str, ...] = (
    "cotton", "polyester", "nylon", "leather", "wool", "spandex", "silk",
    "rayon", "fabric",
)
COLOR_TOKENS: tuple[str, ...] = (
    "black", "white", "blue", "red", "pink", "green", "brown", "gray", "grey",
    "purple", "yellow", "orange",
)

_WHITESPACE_RE = re.compile(r"\s+")
_STRIP_CHARS = " -;,.\t\n"


def normalize_constraint(value: str, limit: int = CONSTRAINT_LIMIT) -> str:
    """Reduce a value the way the simulator does before disclosing it.

    The simulator finishes with ``rstrip()``, so truncating at ``limit`` can
    leave a trailing comma. Stripping the same characters at both ends instead
    makes this idempotent, which matters because the index is built from raw
    catalog values while lookups arrive already truncated: without it the two
    sides normalize to different strings and a valid constraint looks unknown.
    """
    collapsed = _WHITESPACE_RE.sub(" ", value)
    return collapsed.strip(_STRIP_CHARS)[:limit].strip(_STRIP_CHARS)


def _flatten_values(value: object) -> list[str]:
    """Mirror the simulator's per-field expansion, keys included for objects."""
    if isinstance(value, dict):
        return [f"{key}: {item}" for key, item in value.items() if item not in (None, "", [])]
    if isinstance(value, list):
        return [str(item) for item in value if item not in (None, "")]
    return [str(value)] if value not in (None, "") else []


def constraint_candidates(raw: dict) -> Iterator[str]:
    """Every string this product could contribute to a disclosure."""
    # A product with no usable feature or detail falls back to its title, so
    # the title is disclosable even though it is not a facet.
    yield str(raw.get("title") or "product")
    yield from _flatten_values(raw.get("features"))
    yield from _flatten_values(raw.get("details"))
    yield from MATERIAL_TOKENS
    yield from (f"color: {color}" for color in COLOR_TOKENS)
    price = raw.get("price")
    if price not in (None, ""):
        yield f"budget around ${price}"


def index_key(value: str) -> int:
    """Hash a normalized constraint.

    The index holds hashes rather than strings: roughly 13MB against 80MB for
    the full catalog, and reportable runs record peak RSS. Process-local by
    construction, so the built-in hash is sufficient; a persisted index would
    need a stable digest instead.
    """
    return hash(normalize_constraint(value))


def build_constraint_index(records: Iterable[dict]) -> frozenset[int]:
    return frozenset(
        index_key(candidate)
        for raw in records
        for candidate in constraint_candidates(raw)
    )


def candidate_segmentations(disclosed: str, valid: frozenset[int]) -> list[list[str]]:
    """Segmentations of ``disclosed`` whose every part is a known constraint.

    A disclosure holds at most two constraints, so at most one semicolon
    separates them; the rest belong to the text. Each semicolon is tried as
    that single boundary.
    """
    found: list[list[str]] = []
    if index_key(disclosed) in valid:
        found.append([disclosed])
    for match in re.finditer(";", disclosed):
        left = disclosed[: match.start()].strip(" .")
        right = disclosed[match.end():].strip(" .")
        if not left or not right:
            continue
        if index_key(left) in valid and index_key(right) in valid:
            found.append([left, right])
    return found


def segment(disclosed: str, valid: frozenset[int] | None) -> list[str]:
    """Split a disclosure into the constraints it was assembled from.

    Without an index, or when nothing validates, the disclosure is returned
    whole: merging two constraints costs one slot, while shattering one costs
    a slot per fragment and dilutes the soft-term union that scores it.
    """
    if valid is None:
        return [part.strip(" .") for part in disclosed.split(";") if part.strip(" .")]
    if ";" not in disclosed:
        return [disclosed] if disclosed else []
    found = candidate_segmentations(disclosed, valid)
    if not found:
        return [disclosed]
    # Both readings can validate, when a two-constraint disclosure happens to
    # coincide with a catalog value that itself contains a semicolon. Measured
    # over the first 20,000 catalog rows (196,680 disclosures, 3,803 of them
    # ambiguous): preferring the split misreads 16, preferring the whole
    # misreads 3,786. Almost every ambiguous disclosure is genuinely two.
    return max(found, key=len)

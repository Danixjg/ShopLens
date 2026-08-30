"""Pure text helpers shared by parsing and catalog-derived clarification facets."""

from __future__ import annotations

import re


MATERIALS = (
    "cotton", "polyester", "nylon", "leather", "wool", "spandex", "silk", "rayon", "fabric",
)
ANSWERABLE_COLORS = ("black", "white", "blue", "red", "pink", "green")
ASCII_TOKEN_RE = re.compile(r"[a-z0-9]+", re.I)


def ascii_tokens(value: str) -> tuple[str, ...]:
    return tuple(token.casefold() for token in ASCII_TOKEN_RE.findall(str(value)))


def normalize_ascii(value: str) -> str:
    return " ".join(ascii_tokens(value))


def classify_attribute(value: str) -> str:
    """Classify controlled catalog constraints without importing evaluator code."""
    lowered = str(value).casefold()
    if "budget" in lowered or re.search(r"(?:\$|<=|under)\s*\d", lowered):
        return "budget"
    if any(material in lowered for material in MATERIALS):
        return "material"
    if "color" in lowered or any(color in lowered for color in ANSWERABLE_COLORS):
        return "color"
    if any(word in lowered for word in ("size", "sizing", "width", "wide", "narrow")):
        return "size"
    if any(word in lowered for word in ("department", "style", "fit", "sleeve", "neck")):
        return "style"
    if any(word in lowered for word in ("hiking", "running", "gym", "winter", "outdoor", "work")):
        return "use_case"
    return "feature"

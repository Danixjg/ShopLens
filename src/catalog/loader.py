from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from src.attributes import ANSWERABLE_COLORS, MATERIALS, classify_attribute, normalize_ascii
from src.parsing.segmentation import constraint_candidates, index_key


SEARCH_FIELDS = ("title", "features", "details", "description", "categories", "store")
FACET_ATTRIBUTES = ("feature", "material", "color")
FACET_INDEX = {attribute: index for index, attribute in enumerate(FACET_ATTRIBUTES)}
OFFICIAL_CATALOG_PATH = Path(__file__).resolve().parents[2] / "data/catalog.jsonl"
OFFICIAL_CATALOG_SHA256 = "da979b05a68af864cb0dcf9ee6a81c010c7e66a57978ad286c7a2e005fc69a67"


def _pieces(value: object) -> Iterator[str]:
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from _pieces(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _pieces(item)
    elif value not in (None, ""):
        yield str(value)


def flatten_text(value: object) -> str:
    return " ".join(_pieces(value)).strip()


def _facet_pieces(value: object) -> Iterator[str]:
    """Yield catalog-provided values without turning object keys into values."""
    if isinstance(value, dict):
        for item in value.values():
            yield from _facet_pieces(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _facet_pieces(item)
    elif value not in (None, ""):
        text = " ".join(str(value).split()).strip()
        if text:
            yield text


_MATERIAL_TOKEN_RE = re.compile(
    r"\b(" + "|".join(MATERIALS) + r")\b", re.I,
)
_COLOR_TOKEN_RE = re.compile(r"\b(" + "|".join(ANSWERABLE_COLORS) + r")\b", re.I)


def _raw_entries(raw: dict[str, object]) -> tuple[str, ...]:
    """Preserve feature and detail entries as separate source observations."""
    entries = list(_facet_pieces(raw.get("features")))
    details = raw.get("details")
    if isinstance(details, dict):
        for key, value in details.items():
            for piece in _facet_pieces(value):
                entries.append(f"{key}: {piece}")
    for attribute in FACET_ATTRIBUTES:
        entries.extend(f"{attribute}: {piece}" for piece in _facet_pieces(raw.get(attribute)))
    return tuple(entries)


def _raw_facets(entries: tuple[str, ...]) -> tuple[tuple[str, ...], ...]:
    """Retain raw catalog facet values separately from the Product contract.

    Only explicit source fields and labelled detail values are used.  In
    particular, colors and materials are not guessed from searchable text;
    doing that would turn ordinary words into synthetic labels and inflate
    clarification gain.
    """
    collected: dict[str, list[str]] = {attribute: [] for attribute in FACET_ATTRIBUTES}
    for entry in entries:
        label = entry.partition(":")[0].casefold() if ":" in entry else ""
        labelled_attribute: str | None = None
        if "material" in label or "fabric" in label:
            labelled_attribute = "material"
        elif "color" in label or "colour" in label:
            labelled_attribute = "color"
        elif "feature" in label:
            labelled_attribute = "feature"
        value = entry.partition(":")[2].strip() if labelled_attribute else entry
        if labelled_attribute is not None:
            attribute = labelled_attribute
        else:
            attribute = classify_attribute(entry)

        materials = _MATERIAL_TOKEN_RE.findall(value)
        colors = _COLOR_TOKEN_RE.findall(value)
        if attribute == "feature":
            collected["feature"].append(value)
        elif attribute == "material" and not materials:
            collected["material"].append(value)
        elif attribute == "color" and not colors:
            collected["color"].append(value)
        collected["material"].extend(materials)
        collected["color"].extend(colors)

    facets: list[tuple[str, ...]] = []
    for attribute, values in collected.items():
        normalized = (normalize_ascii(value) for value in values)
        distinct = dict.fromkeys(value for value in normalized if value)
        facets.append(tuple(distinct)[:2])
    return tuple(facets)


def catalog_sha256(path: str | Path) -> str:
    """Return the SHA-256 of the bytes that are currently on disk.

    A cryptographic identity must never be inferred from mutable filesystem
    metadata.  Callers that need to reuse a digest should retain the digest on
    the immutable object built from those bytes instead of caching by path,
    size, or modification time.
    """
    digest = hashlib.sha256()
    with Path(path).resolve().open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class Product:
    parent_asin: str
    title: str
    features: str
    description: str
    price: float | None
    categories: str
    details: str
    average_rating: float | None
    rating_number: int
    store: str

    @property
    def searchable_text(self) -> str:
        return " ".join(
            part for part in (
                self.title, self.categories, self.features, self.details,
                self.store, self.description,
            ) if part
        )

    @property
    def compact_text(self) -> str:
        """High-signal fields only, mirroring the BM25 column weights.

        The lexical index already ranks these fields highest (title 6.0,
        categories 4.0, features 2.5) and `details`, `store` and `description`
        lowest. The dense encoder had no such distinction: it embedded the flat
        concatenation, where the median product spends most of its budget on
        those low-weight tails. Because the vendored encoder truncates at 256
        word pieces and mean-pools what survives, the tails both overflow the
        window and pull the vector toward a generic centroid.
        """
        return " ".join(
            part for part in (self.title, self.categories, self.features) if part
        )



DENSE_TEXT_RECIPES = ("full", "compact")


def dense_text(product: Product, recipe: str) -> str:
    """Text the dense encoder indexes for one product under a named recipe.

    An unrecognised recipe falls back to the historical full concatenation, so
    a malformed config can never quietly index something new.
    """
    return product.compact_text if recipe == "compact" else product.searchable_text

@dataclass(frozen=True, slots=True)
class _CatalogRecord:
    product: Product
    facets: tuple[tuple[str, ...], ...]


class Catalog:
    """Immutable in-memory view of the organizer's JSONL catalog."""

    def __init__(
        self,
        path: str | Path,
        expected_sha256: str | None = None,
        *,
        build_facets: bool = True,
        build_constraint_index: bool = False,
    ) -> None:
        self.path = Path(path).resolve()
        records: list[_CatalogRecord] = []
        seen: set[str] = set()
        # Accumulated inside the existing pass: the loop already decodes and
        # parses every record, so the index costs no extra read.
        constraint_keys: set[int] = set()
        digest = hashlib.sha256()
        # Hash the exact byte stream being parsed.  This avoids a check/use race
        # between a separate checksum pass and catalog construction.
        with self.path.open("rb") as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                digest.update(raw_line)
                if not raw_line.strip():
                    continue
                try:
                    line = raw_line.decode("utf-8")
                except UnicodeDecodeError as exc:
                    raise ValueError(f"invalid UTF-8 on catalog line {line_number}") from exc
                raw = json.loads(line)
                asin = str(raw.get("parent_asin", "")).strip()
                if not asin:
                    raise ValueError(f"missing parent_asin on catalog line {line_number}")
                if asin in seen:
                    raise ValueError(f"duplicate parent_asin in catalog: {asin}")
                seen.add(asin)
                if build_constraint_index:
                    constraint_keys.update(
                        index_key(value) for value in constraint_candidates(raw)
                    )
                product_facets = _raw_facets(_raw_entries(raw)) if build_facets else ()
                raw_price = raw.get("price")
                raw_rating = raw.get("average_rating")
                raw_count = raw.get("rating_number")
                product = Product(
                    parent_asin=asin,
                    title=flatten_text(raw.get("title")),
                    features=flatten_text(raw.get("features")),
                    description=flatten_text(raw.get("description")),
                    price=float(raw_price) if isinstance(raw_price, (int, float)) else None,
                    categories=flatten_text(raw.get("categories")),
                    details=flatten_text(raw.get("details")),
                    average_rating=float(raw_rating) if isinstance(raw_rating, (int, float)) else None,
                    rating_number=int(raw_count) if isinstance(raw_count, (int, float)) else 0,
                    store=flatten_text(raw.get("store")),
                )
                records.append(_CatalogRecord(product, product_facets))
        actual = digest.hexdigest()
        if expected_sha256 is not None and actual.lower() != expected_sha256.strip().lower():
            raise ValueError(f"catalog checksum mismatch: expected {expected_sha256}, got {actual}")
        if not records:
            raise ValueError("catalog is empty")
        self.sha256 = actual
        self._records = tuple(records)
        self._by_asin = {record.product.parent_asin: record for record in records}
        self.constraint_index: frozenset[int] | None = (
            frozenset(constraint_keys) if build_constraint_index else None
        )

    def __len__(self) -> int:
        return len(self._records)

    def __iter__(self) -> Iterator[Product]:
        return (record.product for record in self._records)

    def get(self, asin: str) -> Product | None:
        record = self._by_asin.get(asin)
        return record.product if record is not None else None

    def facet_values(self, asin: str, attribute: str) -> tuple[str, ...]:
        """Return immutable source facet values held outside Product."""
        record = self._by_asin.get(asin)
        index = FACET_INDEX.get(attribute)
        return (
            record.facets[index]
            if record is not None and index is not None and len(record.facets) == len(FACET_ATTRIBUTES)
            else ()
        )

    @property
    def fallback_asins(self) -> list[str]:
        return [record.product.parent_asin for record in self._records[:10]]

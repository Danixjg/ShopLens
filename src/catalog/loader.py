from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


SEARCH_FIELDS = ("title", "features", "details", "description", "categories", "store")
OFFICIAL_CATALOG_PATH = Path("data/catalog.jsonl")
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


def catalog_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
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


class Catalog:
    """Immutable in-memory view of the organizer's JSONL catalog."""

    def __init__(self, path: str | Path, expected_sha256: str | None = None) -> None:
        self.path = Path(path)
        if expected_sha256 is not None:
            actual = catalog_sha256(self.path)
            if actual.lower() != expected_sha256.strip().lower():
                raise ValueError(f"catalog checksum mismatch: expected {expected_sha256}, got {actual}")
        products: list[Product] = []
        seen: set[str] = set()
        with self.path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                raw = json.loads(line)
                asin = str(raw.get("parent_asin", "")).strip()
                if not asin:
                    raise ValueError(f"missing parent_asin on catalog line {line_number}")
                if asin in seen:
                    raise ValueError(f"duplicate parent_asin in catalog: {asin}")
                seen.add(asin)
                raw_price = raw.get("price")
                raw_rating = raw.get("average_rating")
                raw_count = raw.get("rating_number")
                products.append(Product(
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
                ))
        if not products:
            raise ValueError("catalog is empty")
        self._products = tuple(products)
        self._by_asin = {item.parent_asin: item for item in products}

    def __len__(self) -> int:
        return len(self._products)

    def __iter__(self) -> Iterator[Product]:
        return iter(self._products)

    def get(self, asin: str) -> Product | None:
        return self._by_asin.get(asin)

    @property
    def fallback_asins(self) -> list[str]:
        return [item.parent_asin for item in self._products[:10]]

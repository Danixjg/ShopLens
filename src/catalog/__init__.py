"""Catalog loading and normalization."""

from .loader import (
    DENSE_TEXT_RECIPES,
    OFFICIAL_CATALOG_PATH,
    OFFICIAL_CATALOG_SHA256,
    Catalog,
    Product,
    catalog_sha256,
    dense_text,
    flatten_text,
)

__all__ = [
    "DENSE_TEXT_RECIPES", "OFFICIAL_CATALOG_PATH", "OFFICIAL_CATALOG_SHA256",
    "Catalog", "Product", "catalog_sha256", "dense_text", "flatten_text",
]

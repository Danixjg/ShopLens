"""Config W: what the dense encoder indexes, and the cache key that protects it."""
from __future__ import annotations

from dataclasses import replace

import pytest

from src.catalog import Product, dense_text
from src.contracts.config import CONFIGS
from src.retrieval.dense import cache_fingerprint


def _product(**overrides: object) -> Product:
    base = dict(
        parent_asin="B000TEST01",
        title="Merino Wool Hiking Sock",
        features="cushioned arch reinforced heel",
        description="LOREM " * 400,
        price=19.99,
        categories="Clothing Socks Athletic",
        details="Package Dimensions 5 x 4 x 1 inches Item Weight 2 ounces ASIN B000TEST01",
        average_rating=4.4,
        rating_number=812,
        store="GenericBrandStore",
    )
    base.update(overrides)
    return Product(**base)  # type: ignore[arg-type]


def test_compact_recipe_keeps_the_fields_bm25_weights_highest() -> None:
    """Title, categories and features carry the signal; BM25 already says so.

    The vendored encoder truncates at 256 word pieces and mean-pools, so the
    details, store and description tails both overflow the window and pull the
    vector toward a generic centroid.
    """
    product = _product()

    compact = product.compact_text

    assert "Merino Wool Hiking Sock" in compact
    assert "Clothing Socks Athletic" in compact
    assert "cushioned arch reinforced heel" in compact
    assert "GenericBrandStore" not in compact
    assert "Package Dimensions" not in compact
    assert "LOREM" not in compact


def test_compact_recipe_is_materially_shorter_than_the_full_blob() -> None:
    product = _product()

    assert len(product.compact_text.split()) < len(product.searchable_text.split()) / 10


def test_compact_recipe_survives_products_missing_every_optional_field() -> None:
    product = _product(categories="", features="", details="", store="", description="")

    assert product.compact_text == "Merino Wool Hiking Sock"


def test_dense_text_selects_the_recipe_and_defaults_to_full() -> None:
    product = _product()

    assert dense_text(product, "compact") == product.compact_text
    assert dense_text(product, "full") == product.searchable_text


def test_cache_fingerprint_changes_when_the_text_recipe_changes() -> None:
    """The guarantee that makes W safe to evaluate.

    Before this key existed, the cache was validated on catalog, model and
    runtime alone. Changing what gets encoded would have silently reused
    embeddings built from the previous recipe, and the run would have measured
    the old text under the new config's name.
    """
    shared = dict(
        catalog_sha256="a" * 64,
        model_sha256="b" * 64,
        model_revision="rev",
        runtime_signature="sig",
    )

    assert cache_fingerprint(text_recipe="full", **shared) != cache_fingerprint(
        text_recipe="compact", **shared
    )


def test_cache_fingerprint_is_stable_for_identical_inputs() -> None:
    shared = dict(
        catalog_sha256="a" * 64,
        model_sha256="b" * 64,
        model_revision="rev",
        runtime_signature="sig",
        text_recipe="compact",
    )

    assert cache_fingerprint(**shared) == cache_fingerprint(**shared)


@pytest.mark.parametrize("field", ["catalog_sha256", "model_sha256", "model_revision", "runtime_signature"])
def test_cache_fingerprint_still_covers_the_pre_existing_identity(field: str) -> None:
    shared = dict(
        catalog_sha256="a" * 64,
        model_sha256="b" * 64,
        model_revision="rev",
        runtime_signature="sig",
        text_recipe="full",
    )

    assert cache_fingerprint(**shared) != cache_fingerprint(**{**shared, field: "changed"})


def test_config_w_is_t_with_only_the_dense_text_recipe_changed() -> None:
    """W must be attributable: one flag apart from T, or its score means nothing."""
    assert CONFIGS["W"].dense_text_recipe == "compact"
    assert CONFIGS["T"].dense_text_recipe == "full"
    assert replace(CONFIGS["W"], name="T", dense_text_recipe="full") == CONFIGS["T"]

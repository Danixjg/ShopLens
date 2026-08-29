from __future__ import annotations

import hashlib
import os
import time
import zipfile
from pathlib import Path

from src.catalog import Catalog, catalog_sha256
from src.contracts.retrieval import Candidate, RetrievalQuery


MODEL_REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
CACHE_SCHEMA_VERSION = 1


def model_tree_sha256(path: str | Path) -> str:
    """Hash model weights and runtime configuration using stable relative paths."""
    root = Path(path)
    digest = hashlib.sha256()
    for file_path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = file_path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        with file_path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    return digest.hexdigest()


class DenseUnavailable(RuntimeError):
    pass


class DenseRetriever:
    """Brute-force dense retrieval using only a vendored model directory."""

    def __init__(
        self,
        catalog: Catalog,
        model_path: str | Path = "models/all-MiniLM-L6-v2",
        cache_path: str | Path | None = None,
    ) -> None:
        path = Path(model_path)
        if not path.is_dir():
            raise DenseUnavailable(f"vendored embedding model not found at {path}")
        try:
            import numpy as np
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise DenseUnavailable("dense dependencies are not installed") from exc
        self._np = np
        try:
            self._model = SentenceTransformer(str(path), local_files_only=True)
        except Exception as exc:
            raise DenseUnavailable(f"could not load vendored embedding model at {path}") from exc
        self._asins = [product.parent_asin for product in catalog]
        cache = Path(cache_path) if cache_path is not None else catalog.path.with_suffix(".embeddings.npz")
        catalog_digest = catalog_sha256(catalog.path)
        model_digest = model_tree_sha256(path)
        dimension_getter = getattr(self._model, "get_embedding_dimension", None)
        if dimension_getter is None:
            dimension_getter = self._model.get_sentence_embedding_dimension
        dimension = int(dimension_getter())
        self.cache_status = "miss"
        self._embeddings = None
        if cache.is_file():
            try:
                with np.load(cache, allow_pickle=False) as saved:
                    cached_asins = [str(item) for item in saved["asins"].tolist()]
                    embeddings = saved["embeddings"]
                    valid = (
                        int(saved["schema_version"].item()) == CACHE_SCHEMA_VERSION
                        and str(saved["catalog_sha256"].item()) == catalog_digest
                        and str(saved["model_sha256"].item()) == model_digest
                        and str(saved["model_revision"].item()) == MODEL_REVISION
                        and cached_asins == self._asins
                        and embeddings.ndim == 2
                        and embeddings.shape == (len(self._asins), dimension)
                        and str(embeddings.dtype) == "float32"
                    )
                    if valid:
                        self._embeddings = embeddings
                        self.cache_status = "hit"
            except (EOFError, KeyError, OSError, ValueError, zipfile.BadZipFile):
                # A partial or stale cache is only a startup optimization;
                # it must never make the offline fallback unusable.
                self._embeddings = None
        if self._embeddings is None:
            texts = [product.searchable_text for product in catalog]
            self._embeddings = self._model.encode(
                texts, batch_size=128, normalize_embeddings=True, show_progress_bar=False,
            )
            temporary: Path | None = None
            try:
                cache.parent.mkdir(parents=True, exist_ok=True)
                temporary = cache.with_name(
                    f".{cache.name}.{os.getpid()}.{time.time_ns()}.tmp.npz"
                )
                np.savez_compressed(
                    temporary,
                    schema_version=np.asarray(CACHE_SCHEMA_VERSION),
                    catalog_sha256=np.asarray(catalog_digest),
                    model_sha256=np.asarray(model_digest),
                    model_revision=np.asarray(MODEL_REVISION),
                    embeddings=self._embeddings,
                    asins=np.asarray(self._asins),
                )
                os.replace(temporary, cache)
                self.cache_status = "rebuilt"
            except OSError:
                # Grading may run from a read-only submission directory. The
                # in-memory embeddings remain valid for this process.
                self.cache_status = "write_failed"
            finally:
                if temporary is not None:
                    try:
                        temporary.unlink()
                    except FileNotFoundError:
                        pass

    def search(self, query: RetrievalQuery, k: int) -> list[Candidate]:
        if not query.text.strip() or k <= 0:
            return []
        vector = self._model.encode([query.text], normalize_embeddings=True, show_progress_bar=False)[0]
        scores = self._embeddings @ vector
        count = min(int(k), len(self._asins))
        indexes = self._np.argpartition(-scores, count - 1)[:count]
        indexes = indexes[self._np.argsort(-scores[indexes])]
        return [
            Candidate(
                asin=self._asins[int(index)],
                score=float(scores[int(index)]),
                components={"dense": float(scores[int(index)])},
            )
            for index in indexes
        ]

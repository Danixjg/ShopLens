from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import platform
import tempfile
import time
import zipfile
from pathlib import Path

from src.catalog import Catalog, dense_text
from src.contracts.retrieval import Candidate, RetrievalQuery


MODEL_REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
CACHE_SCHEMA_VERSION = 3
OFFICIAL_DEVICE = "cpu"
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
OFFICIAL_MODEL_PATH = REPOSITORY_ROOT / "models/all-MiniLM-L6-v2"
OFFICIAL_MODEL_TREE_SHA256 = "d58305c87500d602cd0d8965c3e60a87628d7a5753069d007c79f05b10fc29fa"
ENCODER_DISTRIBUTIONS = (
    "numpy", "sentence-transformers", "torch", "transformers", "tokenizers",
)


def model_tree_sha256(path: str | Path) -> str:
    """Hash a symlink-free model tree from stable relative paths and bytes."""
    requested = Path(path)
    if requested.is_symlink():
        raise ValueError(f"model root must not be a symlink: {requested}")
    root_path = requested.resolve()
    if not root_path.is_dir():
        raise ValueError(f"model root is not a directory: {root_path}")
    files: list[Path] = []
    for item in root_path.rglob("*"):
        if item.is_symlink():
            raise ValueError(f"model tree must not contain symlinks: {item}")
        if item.is_file():
            files.append(item)
        elif not item.is_dir():
            raise ValueError(f"model tree contains a non-regular entry: {item}")
    digest = hashlib.sha256()
    # Order by case-sensitive relative parts rather than by Path comparison.
    # WindowsPath compares case-folded while PosixPath does not, so the same
    # byte-identical tree would otherwise hash differently off Linux and every
    # check there would report a false mismatch indistinguishable from content
    # corruption. The relative parts are what the digest already commits to.
    for file_path in sorted(files, key=lambda item: item.relative_to(root_path).parts):
        relative = file_path.relative_to(root_path).as_posix()
        rel_bytes = relative.encode("utf-8")
        digest.update(len(rel_bytes).to_bytes(4, "big"))
        digest.update(rel_bytes)
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(file_path, flags)
        with os.fdopen(descriptor, "rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    return digest.hexdigest()


def _file_sha256(path: Path) -> str:
    if path.is_symlink():
        raise ValueError(f"file must not be a symlink: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _distribution_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def cache_fingerprint(
    *,
    catalog_sha256: str,
    model_sha256: str,
    model_revision: str,
    runtime_signature: str,
    text_recipe: str,
) -> tuple[int, str, str, str, str, str]:
    """Everything that must match for cached vectors to be reusable.

    ``text_recipe`` is part of the identity because the cache stores vectors,
    not the text they came from. Without it a recipe change reuses embeddings
    built from the previous text and the run measures the old recipe under the
    new config's name.
    """
    return (
        CACHE_SCHEMA_VERSION,
        catalog_sha256,
        model_sha256,
        model_revision,
        runtime_signature,
        text_recipe,
    )


def encoder_runtime_signature(device: str = OFFICIAL_DEVICE) -> str:
    """Stable cache provenance for the code that creates/query-encodes vectors."""
    payload = {
        "python": platform.python_version(),
        "device": device,
        "packages": {name: _distribution_version(name) for name in ENCODER_DISTRIBUTIONS},
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


class DenseUnavailable(RuntimeError):
    pass


class DenseRetriever:
    """Brute-force dense retrieval using only a vendored model directory."""

    def __init__(
        self,
        catalog: Catalog,
        model_path: str | Path = OFFICIAL_MODEL_PATH,
        cache_path: str | Path | None = None,
        text_recipe: str = "full",
    ) -> None:
        requested_model = Path(model_path)
        if not requested_model.is_absolute():
            requested_model = REPOSITORY_ROOT / requested_model
        if requested_model.is_symlink():
            raise DenseUnavailable(f"vendored embedding model must not be a symlink: {requested_model}")
        path = requested_model.resolve()
        try:
            model_digest = model_tree_sha256(requested_model)
        except (OSError, ValueError) as exc:
            raise DenseUnavailable(f"invalid vendored embedding model at {path}") from exc
        official_model = path == OFFICIAL_MODEL_PATH.resolve()
        if official_model and model_digest != OFFICIAL_MODEL_TREE_SHA256:
            raise DenseUnavailable(
                "official embedding model checksum mismatch: "
                f"expected {OFFICIAL_MODEL_TREE_SHA256}, got {model_digest}"
            )
        try:
            import numpy as np
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise DenseUnavailable("dense dependencies are not installed") from exc
        self._np = np
        self.device = OFFICIAL_DEVICE
        try:
            self._model = SentenceTransformer(
                str(path), device=self.device, local_files_only=True,
            )
        except Exception as exc:
            raise DenseUnavailable(f"could not load vendored embedding model at {path}") from exc
        actual_device = str(getattr(self._model, "device", "")).lower()
        parameter_devices = {
            str(parameter.device).split(":", 1)[0].lower()
            for parameter in self._model.parameters()
        }
        if actual_device.split(":", 1)[0] != OFFICIAL_DEVICE or any(
            device != OFFICIAL_DEVICE for device in parameter_devices
        ):
            raise DenseUnavailable(
                f"embedding model did not remain on CPU (reported {actual_device or 'unknown'})"
            )
        try:
            model_digest_after_load = model_tree_sha256(requested_model)
        except (OSError, ValueError) as exc:
            raise DenseUnavailable("embedding model changed while it was loading") from exc
        if model_digest_after_load != model_digest:
            raise DenseUnavailable("embedding model changed while it was loading")
        self.model_path = path
        self.official_model_verified = official_model
        self._asins = [product.parent_asin for product in catalog]
        self._asin_index = {asin: index for index, asin in enumerate(self._asins)}
        if cache_path is None:
            cache = catalog.path.with_suffix(".embeddings.npz")
        else:
            cache = Path(cache_path)
            if not cache.is_absolute():
                cache = REPOSITORY_ROOT / cache
        if cache.is_symlink():
            raise DenseUnavailable(f"embedding cache must not be a symlink: {cache}")
        catalog_digest = catalog.sha256
        runtime_signature = encoder_runtime_signature(self.device)
        self.catalog_sha256 = catalog_digest
        self.model_sha256 = model_digest
        self.runtime_signature = runtime_signature
        self.text_recipe = text_recipe
        expected_fingerprint = cache_fingerprint(
            catalog_sha256=catalog_digest,
            model_sha256=model_digest,
            model_revision=MODEL_REVISION,
            runtime_signature=runtime_signature,
            text_recipe=text_recipe,
        )
        self.cache_path = cache.resolve()
        self.cache_sha256: str | None = None
        self.embeddings_sha256: str | None = None
        self.rebuilt_in_process = False
        self.trusted_for_reporting = False
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
                    saved_fingerprint = cache_fingerprint(
                        catalog_sha256=str(saved["catalog_sha256"].item()),
                        model_sha256=str(saved["model_sha256"].item()),
                        model_revision=str(saved["model_revision"].item()),
                        runtime_signature=str(saved["runtime_signature"].item()),
                        text_recipe=str(saved["text_recipe"].item()),
                    )
                    valid = (
                        int(saved["schema_version"].item()) == CACHE_SCHEMA_VERSION
                        and saved_fingerprint == expected_fingerprint
                        and cached_asins == self._asins
                        and embeddings.ndim == 2
                        and embeddings.shape == (len(self._asins), dimension)
                        and self._valid_embeddings(embeddings, len(self._asins), dimension)
                    )
                    if valid:
                        self._embeddings = embeddings
                        self.cache_status = "hit"
                        self.cache_sha256 = _file_sha256(cache)
            except (EOFError, KeyError, OSError, ValueError, zipfile.BadZipFile):
                # A partial or stale cache is only a startup optimization;
                # it must never make the offline fallback unusable.
                self._embeddings = None
        if self._embeddings is None:
            texts = [dense_text(product, text_recipe) for product in catalog]
            generated = self._model.encode(
                texts,
                batch_size=128,
                device=OFFICIAL_DEVICE,
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            if not self._valid_embeddings(generated, len(self._asins), dimension):
                raise DenseUnavailable("model generated invalid catalog embeddings")
            self._embeddings = self._np.ascontiguousarray(generated)
            self.rebuilt_in_process = True
            temporary: Path | None = None
            try:
                cache.parent.mkdir(parents=True, exist_ok=True)
                descriptor, temporary_name = tempfile.mkstemp(
                    prefix=f".{cache.name}.{os.getpid()}.{time.time_ns()}.",
                    suffix=".tmp.npz",
                    dir=cache.parent,
                )
                temporary = Path(temporary_name)
                with os.fdopen(descriptor, "wb") as handle:
                    np.savez_compressed(
                        handle,
                        schema_version=np.asarray(CACHE_SCHEMA_VERSION),
                        catalog_sha256=np.asarray(catalog_digest),
                        model_sha256=np.asarray(model_digest),
                        model_revision=np.asarray(MODEL_REVISION),
                        runtime_signature=np.asarray(runtime_signature),
                        text_recipe=np.asarray(text_recipe),
                        embeddings=self._embeddings,
                        asins=np.asarray(self._asins),
                    )
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, cache)
                self.cache_status = "rebuilt"
                self.cache_sha256 = _file_sha256(cache)
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
        self.embeddings_sha256 = self._embedding_content_sha256(self._embeddings)
        self.trusted_for_reporting = self.rebuilt_in_process and self.official_model_verified
        self.cache_provenance = {
            "path": str(self.cache_path),
            "status": self.cache_status,
            "cache_sha256": self.cache_sha256,
            "embeddings_sha256": self.embeddings_sha256,
            "catalog_sha256": self.catalog_sha256,
            "model_sha256": self.model_sha256,
            "runtime_signature": self.runtime_signature,
            "text_recipe": self.text_recipe,
            "rebuilt_in_process": self.rebuilt_in_process,
            "official_model_verified": self.official_model_verified,
            "trusted_for_reporting": self.trusted_for_reporting,
        }

    def _valid_embeddings(self, value: object, rows: int, dimension: int) -> bool:
        array = self._np.asarray(value)
        if array.ndim != 2 or array.shape != (rows, dimension):
            return False
        if array.dtype != self._np.dtype("float32") or not self._np.isfinite(array).all():
            return False
        norms = self._np.linalg.norm(array, axis=1)
        return bool(self._np.allclose(norms, 1.0, rtol=1e-3, atol=1e-3))

    def _embedding_content_sha256(self, embeddings: object) -> str:
        array = self._np.ascontiguousarray(embeddings)
        digest = hashlib.sha256()
        dtype = array.dtype.str.encode("ascii")
        shape = json.dumps(array.shape, separators=(",", ":")).encode("ascii")
        digest.update(len(dtype).to_bytes(2, "big"))
        digest.update(dtype)
        digest.update(len(shape).to_bytes(2, "big"))
        digest.update(shape)
        digest.update(memoryview(array).cast("B"))
        return digest.hexdigest()

    def embedding_for(self, asin: str):
        """The catalog's already-computed vector for one asin, or None.

        Reuses the in-memory matrix built once for the whole catalog; callers
        needing a candidate's vector should never re-encode its text.
        """
        index = self._asin_index.get(asin)
        return None if index is None else self._embeddings[index]

    def encode_texts(self, texts: list[str]):
        """Encode arbitrary text with the same vendored model and settings
        used for query encoding, for callers comparing against catalog
        vectors without indexing the text into the catalog store."""
        if not texts:
            return self._np.empty((0, self._embeddings.shape[1]), dtype="float32")
        generated = self._model.encode(
            texts,
            device=OFFICIAL_DEVICE,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return self._np.asarray(generated)

    def search(self, query: RetrievalQuery, k: int) -> list[Candidate]:
        try:
            count = min(max(0, int(k)), len(self._asins))
        except (TypeError, ValueError, OverflowError):
            return []
        if not query.text.strip() or count == 0:
            return []
        generated = self._model.encode(
            [query.text],
            device=OFFICIAL_DEVICE,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        if not self._valid_embeddings(generated, 1, self._embeddings.shape[1]):
            raise DenseUnavailable("model generated an invalid query embedding")
        vector = self._np.asarray(generated)[0]
        scores = self._embeddings @ vector
        if not self._np.isfinite(scores).all():
            raise DenseUnavailable("dense scoring produced a non-finite value")
        if count == len(self._asins):
            selected = range(len(self._asins))
        else:
            boundary = self._np.partition(scores, len(scores) - count)[len(scores) - count]
            above = [int(index) for index in self._np.flatnonzero(scores > boundary)]
            tied = sorted(
                (int(index) for index in self._np.flatnonzero(scores == boundary)),
                key=lambda index: self._asins[index],
            )
            selected = [*above, *tied[:count - len(above)]]
        indexes = sorted(
            selected,
            key=lambda index: (-float(scores[index]), self._asins[index]),
        )
        return [
            Candidate(
                asin=self._asins[int(index)],
                score=float(scores[int(index)]),
                components={"dense": float(scores[int(index)])},
            )
            for index in indexes
        ]

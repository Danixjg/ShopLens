from __future__ import annotations

from pathlib import Path

from src.catalog import Catalog
from src.contracts.retrieval import Candidate, RetrievalQuery


class LocalCrossEncoderReranker:
    """Optional local-only cross encoder; preserves order when unavailable."""

    def __init__(self, catalog: Catalog, model_path: str | Path = "models/cross-encoder") -> None:
        self.catalog = catalog
        self._model = None
        path = Path(model_path)
        if path.is_dir():
            try:
                from sentence_transformers import CrossEncoder
                self._model = CrossEncoder(str(path), local_files_only=True)
            except Exception:
                self._model = None

    def rerank(self, query: RetrievalQuery, candidates: list[Candidate]) -> list[Candidate]:
        if self._model is None or not candidates:
            return candidates
        pairs = []
        for item in candidates:
            product = self.catalog.get(item.asin)
            pairs.append((query.text, product.searchable_text if product else ""))
        scores = self._model.predict(pairs, show_progress_bar=False)
        result = [
            Candidate(item.asin, float(score), {**item.components, "cross_encoder": float(score)})
            for item, score in zip(candidates, scores)
        ]
        return sorted(result, key=lambda item: (-item.score, item.asin))

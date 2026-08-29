from __future__ import annotations

from unittest.mock import patch

from src.agent import Agent
from src.contracts.config import RunConfig
from src.contracts.retrieval import Candidate, RetrievalQuery
from src.retrieval.bm25 import BM25Retriever
from src.retrieval.hybrid import build_retriever
from src.scoring.constraints import ConstraintScorer


class _Product:
    searchable_text = "black waterproof cotton running shoe"


class _Catalog:
    fallback_asins = ["A1"]

    def get(self, asin: str) -> _Product | None:
        return _Product() if asin == "A1" else None


def test_constraint_scoring_preserves_expected_components() -> None:
    scorer = ConstraintScorer(_Catalog())
    query = RetrievalQuery(
        text="running shoe",
        hard=(("material", "cotton"), ("color", "red")),
        soft=(("feature", "waterproof breathable"),),
        turn_index=2,
    )

    result = scorer.score([Candidate("A1", 5.0, {"bm25": 5.0})], query)

    assert len(result) == 1
    assert result[0].components == {
        "bm25": 5.0,
        "hard_material_0": 1.5,
        "hard_color_1": -2.0,
        "soft_feature_0": 0.46,
    }
    assert result[0].score == 4.96


def test_phrase_bonus_is_capped_below_the_hard_constraint_penalty() -> None:
    retriever = object.__new__(BM25Retriever)
    retriever.phrase_evidence = lambda _query: {
        "A": [(f"phrase_soft_feature_{index}", 1.0) for index in range(4)],
    }
    candidates = [
        Candidate("A", -4.0, {"hard_material_0": -4.0}),
        Candidate("B", 1.5, {"hard_material_0": 1.5}),
    ]

    result = BM25Retriever.add_phrase_bonus(retriever, candidates, RetrievalQuery(""))

    assert {candidate.asin for candidate in result} == {"A", "B"}
    assert next(item for item in result if item.asin == "A").score == -3.0
    assert result[0].asin == "B"


def test_disabled_reranker_is_not_constructed() -> None:
    catalog = _Catalog()
    with (
        patch("src.agent.Catalog", return_value=catalog),
        patch("src.agent.build_retriever", return_value=object()),
        patch("src.agent.ConstraintScorer"),
        patch("src.agent.LocalCrossEncoderReranker") as reranker,
    ):
        agent = Agent(config=RunConfig(reranker="none"))

    reranker.assert_not_called()
    assert agent.reranker is None


def test_dense_only_mode_does_not_build_lexical_index() -> None:
    config = RunConfig(retrieval_mode="dense")
    dense = object()
    with (
        patch("src.retrieval.hybrid.DenseRetriever", return_value=dense) as dense_factory,
        patch("src.retrieval.hybrid.BM25Retriever") as lexical_factory,
    ):
        result = build_retriever(_Catalog(), config)

    assert result is dense
    dense_factory.assert_called_once()
    lexical_factory.assert_not_called()

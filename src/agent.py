from __future__ import annotations

import os
from pathlib import Path

from src.catalog import OFFICIAL_CATALOG_PATH, OFFICIAL_CATALOG_SHA256, Catalog
from src.contracts.config import RunConfig, get_run_config
from src.contracts.response import AgentReply, Recommendation, Usage
from src.contracts.retrieval import Candidate, RetrievalQuery
from src.contracts.state import SessionState, UserProfile
from src.parsing import TurnParser
from src.policy import ClarificationPolicy
from src.retrieval import HybridRetriever, build_retriever
from src.scoring import ConstraintScorer, DynamicWeightScorer, LocalCrossEncoderReranker
from src.state import apply_parsed_turn, build_retrieval_query


class Agent:
    """Offline, stateful ShopLens implementation of the organizer contract."""

    def __init__(
        self,
        catalog_path: str | Path = "data/catalog.jsonl",
        config: RunConfig | str | None = None,
    ) -> None:
        self.config = config if isinstance(config, RunConfig) else get_run_config(config)
        expected_checksum = os.getenv("SHOPLENS_CATALOG_SHA256") or None
        skip_pinned_check = os.getenv("SHOPLENS_SKIP_CATALOG_VERIFY", "").lower() in {
            "1", "true", "yes",
        }
        catalog = Path(catalog_path)
        if (
            expected_checksum is None
            and not skip_pinned_check
            and catalog.resolve() == OFFICIAL_CATALOG_PATH.resolve()
        ):
            expected_checksum = OFFICIAL_CATALOG_SHA256
        self.catalog = Catalog(catalog, expected_sha256=expected_checksum)
        self.retriever = build_retriever(self.catalog, self.config)
        self.constraint_scorer = ConstraintScorer(self.catalog)
        self.dynamic_scorer = DynamicWeightScorer()
        self.reranker = (
            LocalCrossEncoderReranker(self.catalog)
            if self.config.reranker == "local_cross_encoder"
            else None
        )
        self.parser = TurnParser()
        self.policy = ClarificationPolicy(self.config)
        self._sessions: dict[str, SessionState] = {}

    def reset(self, session_id: str, user_profile: dict) -> None:
        self._sessions[str(session_id)] = SessionState(
            user_profile=UserProfile.from_dict(user_profile if isinstance(user_profile, dict) else {})
        )

    def _state_for(self, session_id: str) -> SessionState:
        return self._sessions.setdefault(str(session_id), SessionState())

    def _fallback_asins(self, state: SessionState, k: int) -> list[str]:
        if state.last_recommendations:
            return state.last_recommendations[:k]
        return self.catalog.fallback_asins[:k]

    def _search(
        self, state: SessionState, query: RetrievalQuery, k: int,
    ) -> list[Candidate]:
        if self.config.dynamic_weights and isinstance(self.retriever, HybridRetriever):
            return self.retriever.search_for_intent(query, k, state.intent)
        return self.retriever.search(query, k)

    def _respond(self, session_id: str, user_message: str, turn: int, top_k: int) -> dict:
        state = self._state_for(session_id)
        safe_turn = max(1, min(10, int(turn)))
        safe_k = max(1, min(10, int(top_k)))
        parsed = self.parser.parse(str(user_message), safe_turn)
        if not self.config.session_memory:
            for slot in state.slots:
                slot.active = False
        apply_parsed_turn(state, parsed, str(user_message), safe_turn)
        query = build_retrieval_query(state)

        depth = max(50, safe_k * 10) if self.config.constraint_scoring else safe_k
        candidates = self._search(state, query, depth)
        if not candidates and query.category and query.text != query.category:
            # Relax disclosed constraints before falling back to a prior/global
            # list. Hard constraints remain available to penalty scoring below.
            relaxed = RetrievalQuery(
                text=query.category,
                category=query.category,
                turn_index=query.turn_index,
            )
            candidates = self._search(state, relaxed, depth)
        if self.config.constraint_scoring:
            candidates = self.constraint_scorer.score(candidates, query)
        if self.config.dynamic_weights:
            candidates = self.dynamic_scorer.score(candidates, state.intent)
        over_general = self.policy.is_over_general(candidates, safe_k)
        # Reranking may improve reciprocal rank but must not change Top-K
        # membership and therefore Hit Rate@10.
        candidates = sorted(candidates, key=lambda item: (-item.score, item.asin))[:safe_k]
        if self.reranker is not None:
            candidates = self.reranker.rerank(query, candidates)
        candidates = sorted(candidates, key=lambda item: (-item.score, item.asin))[:safe_k]

        asins = [item.asin for item in candidates]
        if not asins:
            asins = self._fallback_asins(state, safe_k)
        if asins:
            state.last_recommendations = list(asins)

        ask_attribute = self.policy.choose(state, candidates)
        if ask_attribute is not None and ask_attribute not in state.asked_attributes:
            state.asked_attributes.append(ask_attribute)
        return AgentReply(
            message=self.policy.message(ask_attribute, over_general),
            ask_attribute=ask_attribute,
            recommendations=[Recommendation(parent_asin=asin) for asin in asins],
            usage=Usage(),
        ).to_dict()

    def respond(self, session_id: str, user_message: str, turn: int, top_k: int) -> dict:
        try:
            return self._respond(session_id, user_message, turn, top_k)
        except Exception:
            state = self._state_for(session_id)
            safe_k = max(1, min(10, top_k if isinstance(top_k, int) else 10))
            asins = self._fallback_asins(state, safe_k)
            return AgentReply(
                message="Here are reliable catalog options while I refine the search.",
                ask_attribute=None if self.config.clarification == "off" else "other",
                recommendations=[Recommendation(parent_asin=asin) for asin in asins],
                usage=Usage(),
            ).to_dict()

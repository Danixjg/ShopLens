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
from src.scoring.ordered import OrderedConstraintReranker
from src.scoring import (
    ConstraintScorer,
    DynamicWeightScorer,
    LocalCrossEncoderReranker,
    PhraseReranker,
    PopularityReranker,
    ProfileAffinityReranker,
)
from src.state import apply_parsed_turn, build_retrieval_query


def rerank_window_size(recommendation_limit: int, window: int) -> int:
    """How many candidates the rerankers may reorder before final truncation.

    A window of zero keeps the historical behaviour, where membership is frozen
    at the recommendation limit and reranking can only reorder what already
    survived. A wider window lets a rerank signal recover a product that lost
    the cut by a hairline, which is the only way reranking can move HitRate@10.
    A window narrower than the limit is clamped up, so a misconfigured value can
    never return fewer products than asked for.
    """
    return max(int(recommendation_limit), int(window))


class Agent:
    """Offline, stateful TrippyShoppy implementation of the organizer contract."""

    def __init__(
        self,
        catalog_path: str | Path = "data/catalog.jsonl",
        config: RunConfig | str | None = None,
    ) -> None:
        self.config = config if isinstance(config, RunConfig) else get_run_config(config)
        explicit_checksum = os.getenv("TRIPPYSHOPPY_CATALOG_SHA256") or None
        requested_catalog = Path(catalog_path)
        uses_default_path = requested_catalog == Path("data/catalog.jsonl")
        catalog = OFFICIAL_CATALOG_PATH if uses_default_path else requested_catalog
        uses_official_path = catalog.resolve() == OFFICIAL_CATALOG_PATH.resolve()
        self.catalog, self.catalog_checksum_verified = self._load_catalog(
            catalog,
            explicit_checksum,
            uses_default_path or uses_official_path,
            build_facets=self.config.clarification in {"info_gain", "expected_value"},
            build_constraint_index=self.config.catalog_grounded_segmentation,
        )
        self.retriever = build_retriever(self.catalog, self.config)
        # Constraint magnitudes come from the config so a fitted variant (O+)
        # can override them; the defaults reproduce the shipped magnitudes.
        self.constraint_scorer = ConstraintScorer(
            self.catalog,
            penalties={
                "material": self.config.penalty_material,
                "color": self.config.penalty_color,
            },
            default_penalty=self.config.default_penalty,
            match_bonus=self.config.match_bonus,
            soft_decay=self.config.soft_decay,
            soft_floor=self.config.soft_floor,
        )
        self.dynamic_scorer = DynamicWeightScorer()
        self.reranker = (
            LocalCrossEncoderReranker(self.catalog)
            if self.config.reranker == "local_cross_encoder"
            else None
        )
        self.phrase_reranker = PhraseReranker(self.catalog) if self.config.phrase_rerank else None
        self.ordered_reranker = (
            OrderedConstraintReranker(self.catalog) if self.config.ordered_rerank else None
        )
        self.popularity_reranker = (
            PopularityReranker(self.catalog, self.config.popularity_rerank_weight)
            if self.config.popularity_rerank
            else None
        )
        self.profile_reranker = (
            ProfileAffinityReranker(self.catalog, self.config.profile_rerank_weight)
            if self.config.profile_rerank
            else None
        )
        # A catalog built without the index yields None, which is the
        # historical split-on-every-semicolon behaviour.
        self.parser = TurnParser(getattr(self.catalog, "constraint_index", None))
        self.policy = ClarificationPolicy(self.config, self.catalog)
        self._sessions: dict[str, SessionState] = {}
        self.exception_count = 0

    @staticmethod
    def _load_catalog(
        path: Path,
        explicit_checksum: str | None,
        enforce_official_checksum: bool,
        *,
        build_facets: bool,
        build_constraint_index: bool = False,
    ) -> tuple[Catalog, bool | None]:
        """Load a catalog while enforcing every checksum that applies.

        The organizer catalog is frozen, so accepting different bytes at its
        official path would make both recommendations and reported metrics
        unverifiable. Custom paths may supply their own explicit checksum for
        local diagnostics.
        """
        if enforce_official_checksum:
            return Catalog(
                path,
                expected_sha256=OFFICIAL_CATALOG_SHA256,
                build_facets=build_facets,
                build_constraint_index=build_constraint_index,
            ), True
        if explicit_checksum is not None:
            return Catalog(
                path,
                expected_sha256=explicit_checksum,
                build_facets=build_facets,
                build_constraint_index=build_constraint_index,
            ), True
        return Catalog(
            path,
            build_facets=build_facets,
            build_constraint_index=build_constraint_index,
        ), None

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

    @staticmethod
    def _turn_limit_reply() -> dict:
        return AgentReply(
            message="This session has reached the 10-turn limit.",
            ask_attribute=None,
            recommendations=[],
            usage=Usage(),
        ).to_dict()

    def _respond(self, session_id: str, user_message: str, turn: int, top_k: int) -> dict:
        requested_turn = int(turn)
        if requested_turn > 10:
            return self._turn_limit_reply()
        state = self._state_for(session_id)
        if state.turn_index >= 10:
            return self._turn_limit_reply()
        safe_turn = max(1, requested_turn)
        safe_k = max(1, min(10, int(top_k)))
        if state.turn_index >= safe_turn:
            return AgentReply(
                message="Ignoring a duplicate or out-of-order turn for this session.",
                ask_attribute=None,
                recommendations=[
                    Recommendation(parent_asin=asin)
                    for asin in self._fallback_asins(state, safe_k)
                ],
                usage=Usage(),
            ).to_dict()
        parsed = self.parser.parse(str(user_message), safe_turn)
        if not self.config.session_memory:
            for slot in state.slots:
                slot.active = False
        apply_parsed_turn(state, parsed, str(user_message), safe_turn)
        query = build_retrieval_query(
            state, exclude_superseded=self.config.negative_preference,
        )

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
        if self.config.exclude_shown and query.exclude:
            # Withhold products already offered. Recall is unaffected because a
            # session that reached this turn proves none of them was the target.
            # If that empties the pool, keep the unfiltered one rather than
            # returning nothing.
            filtered = [item for item in candidates if item.asin not in query.exclude]
            if filtered:
                candidates = filtered
        if self.config.fusion_scale != 1.0:
            # Amplify the fused retrieval score before constraint scoring so it
            # competes with the constraint magnitudes rather than being a
            # negligible prior. 1.0 (every config except O+) is a no-op.
            candidates = [
                Candidate(item.asin, item.score * self.config.fusion_scale, item.components)
                for item in candidates
            ]
        if self.config.constraint_scoring:
            candidates = self.constraint_scorer.score(candidates, query)
        if self.config.dynamic_weights:
            candidates = self.dynamic_scorer.score(candidates, state.intent)
        # The pre-truncation pool drives clarification: it measures how many
        # products still satisfy the disclosed constraints, not how many fit in
        # one response.
        pool = candidates
        over_general = self.policy.is_over_general(pool, safe_k)
        # Reranking may improve reciprocal rank but must not change Top-K
        # membership and therefore Hit Rate@10.
        window = rerank_window_size(safe_k, self.config.rerank_window)
        candidates = sorted(candidates, key=lambda item: (-item.score, item.asin))[:window]
        if self.reranker is not None:
            candidates = self.reranker.rerank(query, candidates)
        if self.ordered_reranker is not None:
            # Replaces the phrase reranker rather than stacking on it: both
            # order the same frozen set from the same disclosures.
            candidates = self.ordered_reranker.rerank(state, candidates)
        elif self.phrase_reranker is not None:
            candidates = self.phrase_reranker.rerank(state, candidates, pool)
        if self.config.rerank_window_scope == "evidence":
            # Freeze membership before the population-level priors. Popularity
            # and profile weights were fitted across sessions, so they are not
            # evidence about this shopper: they may reorder a Top-K the
            # disclosures already chose, but may not decide who is in it. A
            # no-op unless the window is wider than the recommendation limit.
            candidates = candidates[:safe_k]
        if self.popularity_reranker is not None:
            candidates = self.popularity_reranker.rerank(candidates)
        if self.profile_reranker is not None:
            # Applied last and inside frozen membership: the supplied profile may
            # break a tie the disclosed constraints left open, never outrank them.
            candidates = self.profile_reranker.rerank(state, candidates)
        # Truncate last: with the default window this is a no-op, and with a
        # wider one it is the point where reranking is allowed to decide
        # membership rather than only order.
        candidates = candidates[:safe_k]

        asins = [item.asin for item in candidates]
        if not asins:
            asins = self._fallback_asins(state, safe_k)
        if asins:
            state.last_recommendations = list(asins)
            if self.config.exclude_shown:
                # Every asin returned is scored by the evaluator, so reaching the
                # next turn proves none of them was the target.
                state.shown_asins.update(asins)

        ask_attribute = self.policy.choose(
            state,
            pool,
            over_general,
            recommendation_limit=safe_k,
        )
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
            self.exception_count += 1
            state = self._state_for(session_id)
            safe_k = max(1, min(10, top_k if isinstance(top_k, int) else 10))
            asins = self._fallback_asins(state, safe_k)
            ask_attribute = (
                "other"
                if self.config.clarification != "off"
                and "other" not in state.asked_attributes
                and "other" not in state.declined_attributes
                else None
            )
            if ask_attribute is not None:
                state.asked_attributes.append(ask_attribute)
            return AgentReply(
                message="Here are reliable catalog options while I refine the search.",
                ask_attribute=ask_attribute,
                recommendations=[Recommendation(parent_asin=asin) for asin in asins],
                usage=Usage(),
            ).to_dict()

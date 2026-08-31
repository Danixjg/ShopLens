"""Turn-by-turn error analysis for ShopLens.

The organizer's evaluator only reports hit/miss + rank per session, not *why*
a session failed. This script re-plays the exact same conversation logic
(reusing the real customer-simulation helpers from evaluator.local_evaluator,
so the transcript is faithful to what the official evaluator actually does)
and prints/saves the full turn-by-turn transcript for every session that
either missed entirely, or hit but ranked worse than --max-rank.

Usage:
    python3 -m scripts.error_analysis --config P --split dev
    python3 -m scripts.error_analysis --config P --split dev --max-rank 5 --limit 25
    python3 -m scripts.error_analysis --config P --split holdout --output holdout_errors.json

Notes:
    - Requires data/catalog.jsonl to already be downloaded per the main README.
    - --config selects the same named ablation configs defined in
      src/contracts/config.py (A, B, C, ..., P). Defaults to "P", the current
      best frozen configuration.
    - This does not change scores or write to results.jsonl; it's a read-only
      diagnostic tool for the Error Analysis Note deliverable.
"""

from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path

from evaluator.local_evaluator import (
    MAX_TURNS,
    TOP_K,
    catalog_index,
    coarse_category,
    customer_reply,
    initial_message,
    load_jsonl,
    materialize_hidden_fields,
    normalize_recommendations,
)
from src.agent import Agent
from src.contracts.config import get_run_config
from src.eval.split import stratified_dev_holdout_split


class FreezeRecorder:
    """Capture the score every candidate held when Top-K membership was frozen.

    The agent sorts and truncates to Top-K, then hands that frozen list to the
    reranking chain, which reorders it and rebuilds the scores from rank. The
    scores that decided *membership* are therefore gone by the time a response
    is returned. This records the first reranker's input each turn, which is
    exactly the frozen list before anything reorders it.
    """

    STAGES = ("reranker", "ordered_reranker", "phrase_reranker", "popularity_reranker")

    def __init__(self, agent: Agent) -> None:
        self.scores: dict[str, float] = {}
        self._captured = False
        for name in self.STAGES:
            stage = getattr(agent, name, None)
            if stage is not None:
                self._wrap(stage)

    def _wrap(self, stage: object) -> None:
        original = stage.rerank

        def rerank(*args, **kwargs):
            # The candidate list is the only list argument these stages take.
            for value in args:
                if isinstance(value, list):
                    self.capture(value)
                    break
            return original(*args, **kwargs)

        stage.rerank = rerank

    def capture(self, candidates: list) -> None:
        if self._captured:
            return
        self.scores = {item.asin: float(item.score) for item in candidates}
        self._captured = True

    def start_turn(self) -> None:
        self.scores = {}
        self._captured = False


def session_constraints(agent: Agent, session_id: str) -> dict:
    """The constraint state the agent is retrieving against, after this turn."""
    state = agent._sessions.get(session_id)
    if state is None:
        return {}
    return {
        "intent": state.intent,
        "category": state.category or None,
        "active": [
            {
                "attribute": slot.attribute,
                "value": slot.value,
                "hard": slot.hard,
                "source_turn": slot.source_turn,
            }
            for slot in state.slots
            if slot.active
        ],
        "retired": [
            {"attribute": slot.attribute, "value": slot.value, "source_turn": slot.source_turn}
            for slot in state.slots
            if not slot.active
        ],
        "asked_attributes": list(state.asked_attributes),
        "declined_attributes": sorted(state.declined_attributes),
        "withheld_count": len(getattr(state, "shown_asins", ()) or ()),
    }


def trace_session(
    agent: Agent,
    sample: dict,
    catalog_ids: set[str],
    categories: dict[str, list[str]],
    products: dict[str, dict],
    recorder: "FreezeRecorder | None" = None,
) -> dict:
    """Replay one session turn-by-turn, recording everything the evaluator discards."""
    session_id = f"trace_{uuid.uuid4().hex}"
    agent.reset(session_id, sample["user_profile"])
    target = str(sample["ground_truth"]["parent_asin"])
    effective_intent_card, effective_behavior = materialize_hidden_fields(sample, products)
    effective_sample = {**sample, "intent_card": effective_intent_card, "behavior": effective_behavior}
    disclosed: set[str] = set()
    boundary_used = False
    override_applied = sample["scenario_type"] != "intent_override"
    user_message = initial_message(
        effective_sample, coarse_category(categories.get(target, [])), disclosed
    )

    transcript: list[dict] = []
    hit_turn: int | None = None
    best_rank: int | None = None

    for turn in range(1, MAX_TURNS + 1):
        if recorder is not None:
            recorder.start_turn()
        try:
            response = agent.respond(session_id, user_message, turn, TOP_K)
        except Exception as exc:  # pragma: no cover - diagnostic path only
            response = {
                "message": f"<agent raised {type(exc).__name__}: {exc}>",
                "ask_attribute": None,
                "recommendations": [],
            }
        if not isinstance(response, dict):
            response = {"message": "<invalid response shape>", "ask_attribute": None, "recommendations": []}

        ranked = normalize_recommendations(response.get("recommendations"), catalog_ids)
        rank = ranked.index(target) + 1 if target in ranked else None

        frozen = recorder.scores if recorder is not None else {}
        transcript.append(
            {
                "turn": turn,
                "customer_said": user_message,
                "agent_message": response.get("message"),
                "agent_asked": response.get("ask_attribute"),
                "recommendations": ranked,
                # Positionally aligned with "recommendations". These are the
                # scores that decided Top-K membership, not the post-rerank
                # order, so they are deliberately not monotonic.
                "scores": [frozen.get(asin) for asin in ranked],
                "constraints": session_constraints(agent, session_id),
                "target_rank_this_turn": rank,
            }
        )

        if override_applied and rank is not None:
            hit_turn, best_rank = turn, rank
            break
        if turn == MAX_TURNS:
            break

        override = effective_sample.get("behavior", {}).get("override") or {}
        if not override_applied and turn + 1 == int(override.get("turn", 3)):
            override_applied = True
            new_value = str(override.get("new_value", ""))
            if new_value:
                disclosed.add(new_value)
            user_message = str(override.get("message", "Actually, please ignore my earlier preference."))
        else:
            user_message, boundary_used = customer_reply(
                effective_sample, response.get("ask_attribute"), disclosed, boundary_used
            )

    return {
        "sample_id": sample["sample_id"],
        "scenario_type": sample["scenario_type"],
        "target": target,
        "target_title": (products.get(target) or {}).get("title"),
        "hit_turn": hit_turn,
        "best_rank": best_rank,
        "transcript": transcript,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Trace failing/low-ranked ShopLens sessions turn-by-turn")
    parser.add_argument("--catalog", default="data/catalog.jsonl")
    parser.add_argument("--dataset", default="data/public_set.jsonl")
    parser.add_argument("--config", default="P")
    parser.add_argument("--split", choices=("dev", "holdout", "all"), default="dev")
    parser.add_argument(
        "--max-rank",
        type=int,
        default=3,
        help="flag sessions that missed OR whose best rank was worse than this",
    )
    parser.add_argument("--limit", type=int, default=15, help="how many flagged transcripts to print")
    parser.add_argument("--output", default="error_analysis.json")
    args = parser.parse_args()

    samples = load_jsonl(args.dataset)
    dev, holdout = stratified_dev_holdout_split(samples)
    selected = {"dev": dev, "holdout": holdout, "all": samples}[args.split]

    catalog_ids, categories, products = catalog_index(args.catalog)
    agent = Agent(args.catalog, config=get_run_config(args.config))
    recorder = FreezeRecorder(agent)

    flagged = []
    for sample in selected:
        trace = trace_session(agent, sample, catalog_ids, categories, products, recorder)
        is_miss = trace["best_rank"] is None
        is_low_rank = trace["best_rank"] is not None and trace["best_rank"] > args.max_rank
        if is_miss or is_low_rank:
            flagged.append(trace)

    # Worst first: misses (None sorts first), then by rank descending.
    flagged.sort(key=lambda t: (t["best_rank"] is not None, -(t["best_rank"] or 0)))

    print(f"{len(flagged)} of {len(selected)} sessions missed or ranked worse than {args.max_rank}\n")
    by_scenario: dict[str, int] = {}
    for trace in flagged:
        by_scenario[trace["scenario_type"]] = by_scenario.get(trace["scenario_type"], 0) + 1
    print("breakdown by scenario:", by_scenario, "\n")

    for trace in flagged[: args.limit]:
        outcome = "MISS" if trace["best_rank"] is None else f"hit at rank {trace['best_rank']} on turn {trace['hit_turn']}"
        print("=" * 88)
        print(f"{trace['sample_id']}  [{trace['scenario_type']}]  target={trace['target']}  ({trace['target_title']})")
        print(f"result: {outcome}")
        for t in trace["transcript"]:
            print(f"  turn {t['turn']}: customer said: {t['customer_said']!r}")
            print(f"           agent asked: {t['agent_asked']!r}  |  message: {t['agent_message']!r}")
            constraints = t.get("constraints") or {}
            active = constraints.get("active") or []
            print(f"           constraints: intent={constraints.get('intent')!r} "
                  f"category={constraints.get('category')!r} withheld={constraints.get('withheld_count')}")
            for slot in active:
                kind = "hard" if slot["hard"] else "soft"
                print(f"             - [{kind} t{slot['source_turn']}] {slot['attribute']}: {slot['value'][:70]}")
            if not active:
                print("             - (none disclosed yet)")
            print(f"           recs: {t['recommendations']}  (target rank this turn: {t['target_rank_this_turn']})")
            scores = t.get("scores") or []
            shown = ", ".join("None" if v is None else f"{v:.4f}" for v in scores)
            print(f"           freeze scores: [{shown}]")
        print()

    Path(args.output).write_text(json.dumps(flagged, indent=2))
    print(f"Full trace list for all {len(flagged)} flagged sessions written to {args.output}")


if __name__ == "__main__":
    main()
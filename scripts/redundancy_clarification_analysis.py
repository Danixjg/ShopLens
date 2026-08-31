"""Read-only diagnostic: Top-10 redundancy and clarification timing for config O.

Reuses the real customer-simulation helpers from evaluator.local_evaluator so
the replayed transcript matches what the official evaluator actually does.
Does not modify src/, does not write to results.jsonl, does not open a
holdout-only path (it evaluates all 200 public sessions, dev + holdout
combined, since both are development data per the competition rules).

Instrumentation is done by monkeypatching the *live* ClarificationPolicy
instance's bound `choose` method at runtime, from this script only -- no file
under src/ is edited. This captures the pre-truncation candidate pool size
(`len(candidates)` at the point `_respond` calls `self.policy.choose(...)`),
which is exactly what src/agent.py's own comment describes as driving the
clarification decision.

Usage:
    python3 scripts/redundancy_clarification_analysis.py
"""

from __future__ import annotations

import json
import re
import statistics
import uuid
from collections import defaultdict
from difflib import SequenceMatcher
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

ROOT = Path(__file__).resolve().parent.parent
CATALOG_PATH = ROOT / "data" / "catalog.jsonl"
DATASET_PATH = ROOT / "data" / "public_set.jsonl"

COLOR_RE = re.compile(
    r"\b(black|white|blue|navy|red|pink|green|brown|tan|beige|khaki|gray|grey|"
    r"purple|yellow|orange|gold|silver|charcoal|maroon|burgundy|teal|olive|"
    r"ivory|cream|multicolor)\b",
    re.I,
)
SIZE_RE = re.compile(
    r"\b(xx-?small|xx-?large|x-?small|x-?large|small|medium|large|xxs|xxl|xl|xs|"
    r"one size|\d{1,2}(?:\.\d)?\s*(?:x\s*\d{1,2}(?:\.\d)?)?)\b",
    re.I,
)


def normalize_core(title: str) -> list[str]:
    text = title.lower()
    text = COLOR_RE.sub(" ", text)
    text = SIZE_RE.sub(" ", text)
    text = re.sub(r"[^a-z0-9 ]", " ", text)
    return [tok for tok in text.split() if len(tok) > 1]


def token_jaccard(a: list[str], b: list[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


CORE_JACCARD_THRESHOLD = 0.82
RAW_TITLE_RATIO_THRESHOLD = 0.90


def redundant_slot_count(asins: list[str], products: dict[str, dict]) -> tuple[int, list[dict]]:
    """Union-find clustering of near-duplicate items in one Top-K list.

    Two slots are linked if their normalized core tokens (title with color and
    size words stripped) overlap heavily, or if the raw titles are near-
    identical text. "Wasted slots" = total items minus number of distinct
    clusters, i.e. every item beyond the first in each duplicate cluster.
    """
    n = len(asins)
    titles = [str((products.get(a) or {}).get("title") or "") for a in asins]
    cores = [normalize_core(t) for t in titles]
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: int, y: int) -> None:
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[rx] = ry

    pair_evidence = []
    for i in range(n):
        for j in range(i + 1, n):
            jac = token_jaccard(cores[i], cores[j])
            raw = SequenceMatcher(None, titles[i].lower(), titles[j].lower()).ratio()
            if jac >= CORE_JACCARD_THRESHOLD or raw >= RAW_TITLE_RATIO_THRESHOLD:
                union(i, j)
                pair_evidence.append(
                    {
                        "asin_a": asins[i],
                        "asin_b": asins[j],
                        "title_a": titles[i],
                        "title_b": titles[j],
                        "core_jaccard": round(jac, 3),
                        "raw_title_ratio": round(raw, 3),
                    }
                )

    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(n):
        groups[find(i)].append(i)
    wasted = sum(len(g) - 1 for g in groups.values() if len(g) > 1)
    return wasted, pair_evidence


def main() -> None:
    catalog_ids, categories, products = catalog_index(CATALOG_PATH)
    samples = load_jsonl(DATASET_PATH)

    config = get_run_config("O")
    agent = Agent(CATALOG_PATH, config=config)
    print("effective retriever:", type(agent.retriever).__name__)

    capture: dict = {"session_id": None, "turn": None, "records": []}
    original_choose = agent.policy.choose

    def instrumented_choose(state, candidates, over_general=True, recommendation_limit=10):
        pool_size = len(candidates)
        result = original_choose(state, candidates, over_general, recommendation_limit)
        capture["records"].append(
            {
                "session_id": capture["session_id"],
                "turn": capture["turn"],
                "pool_size": pool_size,
                "over_general": over_general,
                "ask_attribute": result,
            }
        )
        return result

    agent.policy.choose = instrumented_choose

    session_reports = []

    for sample in samples:
        session_id = f"analysis_{uuid.uuid4().hex}"
        agent.reset(session_id, sample["user_profile"])
        target = str(sample["ground_truth"]["parent_asin"])
        effective_intent_card, effective_behavior = materialize_hidden_fields(sample, products)
        effective_sample = {**sample, "intent_card": effective_intent_card, "behavior": effective_behavior}
        disclosed: set[str] = set()
        boundary_used = False
        override_applied = sample["scenario_type"] != "intent_override"
        user_message = initial_message(effective_sample, coarse_category(categories.get(target, [])), disclosed)
        hit_turn = None
        best_rank = None
        turn_records = []

        for turn in range(1, MAX_TURNS + 1):
            capture["session_id"] = sample["sample_id"]
            capture["turn"] = turn
            try:
                response = agent.respond(session_id, user_message, turn, TOP_K)
            except Exception:
                response = {"message": "", "ask_attribute": None, "recommendations": []}
            if not isinstance(response, dict) or not isinstance(response.get("message"), str):
                response = {"message": "", "ask_attribute": None, "recommendations": []}
            ranked = normalize_recommendations(response.get("recommendations"), catalog_ids)
            wasted, pair_evidence = redundant_slot_count(ranked, products)
            pool_record = capture["records"][-1] if capture["records"] and capture["records"][-1]["turn"] == turn else None
            turn_records.append(
                {
                    "turn": turn,
                    "recommendations": ranked,
                    "wasted_slots": wasted,
                    "list_size": len(ranked),
                    "wasted_fraction": (wasted / len(ranked)) if ranked else 0.0,
                    "duplicate_pairs": pair_evidence,
                    "pool_size": pool_record["pool_size"] if pool_record else None,
                    "over_general": pool_record["over_general"] if pool_record else None,
                    "ask_attribute": response.get("ask_attribute"),
                }
            )
            if override_applied and target in ranked:
                best_rank = ranked.index(target) + 1
                hit_turn = turn
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

        session_reports.append(
            {
                "sample_id": sample["sample_id"],
                "scenario_type": sample["scenario_type"],
                "hit": hit_turn is not None,
                "first_hit_turn": hit_turn,
                "best_rank": best_rank,
                "turns": turn_records,
            }
        )

    out_path = Path(
        r"C:\Users\thaqi\AppData\Local\Temp\claude\C--Users-thaqi-TrippyShoppy\2a991697-c7a4-418d-a76d-dbe7f1cf4889\scratchpad\redundancy_clarification.json"
    )
    with out_path.open("w", encoding="utf-8") as handle:
        json.dump(session_reports, handle)
    print("wrote", out_path, "sessions:", len(session_reports))


if __name__ == "__main__":
    main()

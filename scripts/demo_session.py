"""Print a deterministic multi-turn ShopLens walkthrough."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Runnable both as `python3 scripts/demo_session.py` and as
# `python3 -m scripts.demo_session`; only the latter puts the repository root
# on the path automatically.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent import Agent  # noqa: E402
from src.retrieval import HybridRetriever  # noqa: E402
from src.retrieval.dense import DenseRetriever  # noqa: E402


DEMO_PROFILE = {
    "purchase_frequency": "3-4 prior purchases",
    "average_prior_rating": 4.0,
    "rating_style": "mixed",
    "preference_tags": ["comfort", "material", "fit"],
    "summary": "Prior purchases emphasize comfort, material, and fit.",
}

DEMO_MESSAGES = (
    "I'm looking for Shoes, but I'm still exploring.",
    "For that, what matters is: waterproof; leather.",
    "Actually, ignore my earlier preference. What I need is: cotton.",
)

TITLE_WIDTH = 64


def effective_retrieval_mode(agent: Agent) -> str:
    """The retrieval actually built, which may differ from the one requested."""
    retriever = agent.retriever
    if isinstance(retriever, HybridRetriever):
        return "hybrid" if isinstance(retriever.dense, DenseRetriever) else "bm25"
    if isinstance(retriever, DenseRetriever):
        return "dense"
    return "bm25"


def require_requested_retrieval(agent: Agent) -> str:
    """Refuse to demonstrate a configuration this environment cannot run.

    Missing dense dependencies degrade hybrid retrieval to BM25 without raising,
    which is correct for serving but wrong for a demonstration: the walkthrough
    would narrate one configuration while showing another.
    """
    requested = agent.config.retrieval_mode
    effective = effective_retrieval_mode(agent)
    if requested != effective:
        raise SystemExit(
            f"config {agent.config.name} requests {requested} retrieval but this "
            f"interpreter provides {effective}.\n"
            f"Install the reference environment and rerun with that interpreter:\n"
            f"    python3 -m pip install -r requirements-dense.lock.txt"
        )
    return effective


def render_turn(agent: Agent, turn: int, message: str, response: dict) -> None:
    print(f"\n─── turn {turn} " + "─" * 58)
    print(f"customer : {message}")
    print(f"agent    : {response['message']}")
    print(f"asks     : {response.get('ask_attribute') or '(none)'}")
    recommendations = response.get("recommendations", [])
    if not recommendations:
        print("top      : (none)")
        return
    print(f"top {len(recommendations)}   :")
    for rank, item in enumerate(recommendations, start=1):
        asin = str(item["parent_asin"])
        product = agent.catalog.get(asin)
        title = product.title if product is not None else "(not in catalog)"
        if len(title) > TITLE_WIDTH:
            title = title[: TITLE_WIDTH - 1] + "…"
        print(f"  {rank:>2}. {title:<{TITLE_WIDTH}} {asin}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a ShopLens multi-turn demo")
    parser.add_argument("--catalog", default="data/catalog.jsonl")
    parser.add_argument("--config", default="P")
    args = parser.parse_args()

    agent = Agent(args.catalog, config=args.config)
    effective = require_requested_retrieval(agent)
    print(
        f"config {agent.config.name} | retrieval {effective} | "
        f"clarification {agent.config.clarification} | "
        f"catalog {len(agent.catalog)} products"
    )

    session_id = "shoplens-demo"
    agent.reset(session_id, DEMO_PROFILE)
    for turn, message in enumerate(DEMO_MESSAGES, start=1):
        response = agent.respond(session_id, message, turn, 10)
        render_turn(agent, turn, message, response)

    usage = response.get("usage")
    if usage is not None:
        print(
            f"\ntokens   : prompt {usage['prompt_tokens']}, "
            f"completion {usage['completion_tokens']} (fully offline)"
        )


if __name__ == "__main__":
    main()

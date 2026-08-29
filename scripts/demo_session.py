"""Print a deterministic multi-turn ShopLens API walkthrough."""

from __future__ import annotations

import argparse
import json

from agent import Agent


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


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a ShopLens multi-turn demo")
    parser.add_argument("--catalog", default="data/catalog.jsonl")
    parser.add_argument("--config", default="F")
    args = parser.parse_args()

    agent = Agent(args.catalog, config=args.config)
    session_id = "shoplens-demo"
    agent.reset(session_id, DEMO_PROFILE)
    for turn, message in enumerate(DEMO_MESSAGES, start=1):
        response = agent.respond(session_id, message, turn, 10)
        print(json.dumps({"turn": turn, "customer": message, "agent": response}, indent=2))


if __name__ == "__main__":
    main()

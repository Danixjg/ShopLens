"""Fit Config O's eight scoring weights instead of guessing them (Config O+).

This reproduces how the weights frozen into ``CONFIGS["O+"]`` were derived. It
searches ``fusion_scale``, ``precision_lexical_weight``, ``match_bonus``, the
three hard penalties, ``soft_decay`` and ``soft_floor`` to maximise the public
TechnicalScore on a training split, using random search followed by a
Nelder-Mead refinement. The objective is evaluated through the real Agent
pipeline (the same ``RunConfig`` fields the shipped agent reads), so a fitted
result can be dropped straight into ``config.py``.

Reproducibility note: ``--split random0`` reproduces the exact random 120/80
split (``random.Random(0)``) the shipped O+ weights were fitted on; ``--split
official`` uses the deterministic stratified dev/holdout instead.

    python -m scripts.learn_config_o --split random0
"""

from __future__ import annotations

import argparse
import json
import random
import time
from dataclasses import replace

import numpy as np
from scipy.optimize import minimize

from evaluator.local_evaluator import catalog_index, evaluate, load_jsonl
from src.agent import Agent
from src.contracts.config import CONFIGS
from src.eval.split import stratified_dev_holdout_split
from src.scoring import ConstraintScorer

# search order: [log10(fusion), plw, bonus, pen_material, pen_color, default_pen, soft_decay, soft_floor]
BOUNDS = [(0.0, 3.0), (0.0, 1.0), (0.0, 5.0), (0.0, 10.0), (0.0, 10.0), (0.0, 10.0), (0.0, 0.30), (0.0, 1.0)]
SHIPPED = [0.0, 0.75, 1.5, 4.0, 2.0, 3.0, 0.08, 0.25]
NAMES = ["fusion_scale", "precision_lexical_weight", "match_bonus", "penalty_material",
         "penalty_color", "default_penalty", "soft_decay", "soft_floor"]


def clip(x):
    return [min(hi, max(lo, xi)) for xi, (lo, hi) in zip(x, BOUNDS)]


def as_params(x):
    x = clip(x)
    return {
        "fusion_scale": 10.0 ** x[0],
        "precision_lexical_weight": x[1],
        "match_bonus": x[2],
        "penalty_material": x[3],
        "penalty_color": x[4],
        "default_penalty": x[5],
        "soft_decay": x[6],
        "soft_floor": x[7],
    }


def apply(agent, params):
    """Point a prebuilt agent at a candidate weight vector (fast; no rebuild)."""
    agent.config = replace(agent.config, **params)
    agent.retriever.precision_lexical_weight = params["precision_lexical_weight"]
    agent.constraint_scorer = ConstraintScorer(
        agent.catalog,
        penalties={"material": params["penalty_material"], "color": params["penalty_color"]},
        default_penalty=params["default_penalty"],
        match_bonus=params["match_bonus"],
        soft_decay=params["soft_decay"],
        soft_floor=params["soft_floor"],
    )


def make_split(samples, which):
    if which == "official":
        return stratified_dev_holdout_split(samples)
    seed = int(which.replace("random", "") or 0)
    idx = list(range(len(samples)))
    random.Random(seed).shuffle(idx)
    return [samples[i] for i in idx[:120]], [samples[i] for i in idx[120:]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="random0", help="random<seed> (fitted split) or official")
    ap.add_argument("--n-random", type=int, default=50)
    ap.add_argument("--nm-maxfev", type=int, default=30)
    ap.add_argument("--out", default="data/learned_params.json")
    args = ap.parse_args()

    t = time.time()
    agent = Agent("data/catalog.jsonl", config=CONFIGS["O"])
    samples = load_jsonl("data/public_set.jsonl")
    cid, cats, prods = catalog_index("data/catalog.jsonl")
    train, test = make_split(samples, args.split)
    print(f"[{time.time()-t:.0f}s] built; split={args.split} train={len(train)} test={len(test)}", flush=True)

    cache: dict = {}

    def objective(x):
        key = tuple(round(v, 4) for v in clip(x))
        if key not in cache:
            apply(agent, as_params(x))
            cache[key] = evaluate(agent, train, cid, cats, prods)["recommended_technical_score"]
        return cache[key]

    rng = random.Random(1000)
    best_x, best_s = SHIPPED[:], objective(SHIPPED)
    for i in range(args.n_random):
        x = [rng.uniform(lo, hi) for lo, hi in BOUNDS]
        s = objective(x)
        if s > best_s:
            best_s, best_x = s, x
        if (i + 1) % 10 == 0:
            print(f"  random {i+1}/{args.n_random} best={best_s:.4f} ({time.time()-t:.0f}s)", flush=True)
    res = minimize(lambda x: -objective(x), np.array(best_x), method="Nelder-Mead",
                   options={"maxfev": args.nm_maxfev, "xatol": 1e-3, "fatol": 1e-5})
    if -res.fun > best_s:
        best_x = list(res.x)

    params = as_params(best_x)
    apply(agent, params)

    def metrics(sub):
        r = evaluate(agent, sub, cid, cats, prods)
        return {k: r[k] for k in ("sample_count", "hit_rate_at_10", "mrr", "mttc",
                                  "efficiency", "recommended_technical_score")}

    out = {"split": args.split, "evals": len(cache),
           "learned_params": {k: round(v, 4) for k, v in params.items()},
           "train": metrics(train), "test": metrics(test), "all": metrics(samples)}
    with open(args.out, "w") as f:
        json.dump(out, f, indent=2)
    print(json.dumps(out, indent=2), flush=True)
    print(f"\nwrote {args.out}", flush=True)


if __name__ == "__main__":
    main()

from __future__ import annotations

import random
from collections import defaultdict


def stratified_dev_holdout_split(
    samples: list[dict],
    dev_fraction: float = 0.6,
    seed: int = 2026,
) -> tuple[list[dict], list[dict]]:
    """Deterministic scenario-stratified 60/40 split (120/80 for public data)."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for sample in samples:
        groups[str(sample.get("scenario_type", "unknown"))].append(sample)
    rng = random.Random(seed)
    dev: list[dict] = []
    holdout: list[dict] = []
    for scenario in sorted(groups):
        group = sorted(groups[scenario], key=lambda item: str(item.get("sample_id", "")))
        rng.shuffle(group)
        boundary = round(len(group) * dev_fraction)
        dev.extend(group[:boundary])
        holdout.extend(group[boundary:])
    dev.sort(key=lambda item: str(item.get("sample_id", "")))
    holdout.sort(key=lambda item: str(item.get("sample_id", "")))
    return dev, holdout

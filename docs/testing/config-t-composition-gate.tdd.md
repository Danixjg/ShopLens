# Config T composition gate

## Status: frozen before any run

At the time this file is committed, `results.jsonl` contains **zero** rows for
config `T`. The decision rule below is fixed now so it cannot be chosen after
seeing a result. Config `T` itself is already implemented and is not modified
by this document.

## What T is

`T` is `P` plus the three component flags that each independently cleared the
retention gate against `P` on both splits:

| Component | Flag added to P | Dev score | Holdout score |
|---|---|---|---|
| `R` | `symmetric_intent_routing=True` | 0.823304 | 0.846396 |
| `S` | `profile_rerank=True`, weight `0.05` | 0.823050 | 0.846896 |
| `Q` | `popularity_rerank=True`, weight `0.15` | 0.862083 | 0.880321 (exploratory) |
| `P` | baseline | 0.819939 | 0.843958 |

`T` sets all three at once. The registry comment states the research question
directly: the components pass individually, and `T` measures whether they
compose.

The premise was verified before freezing: replaying the same gate over
`results.jsonl` confirms `R`, `S`, and `Q` each pass on dev **and** holdout
against `P`, with zero exceptions.

## Retention gate, frozen before any run

`T` may be evaluated once on the deterministic 120-session dev split from a
clean commit in the reference environment. Mirroring the gate `R`, `S`, and
`Q` each passed:

- dev TechnicalScore must be at least P's canonical `0.819939`;
- dev HitRate@10 must be at least P's canonical `0.941667`;
- no scenario TechnicalScore may regress by more than `0.02` versus P, i.e.
  `boundary >= 0.839167`, `browsing >= 0.837904`, `buying >= 0.781674`,
  `intent_override >= 0.734325`;
- agent exceptions, evaluator exceptions, and invalid responses must all be
  zero; and
- no implementation or parameter tuning may occur after inspecting dev. In
  particular `POPULARITY_RERANK_WEIGHT` (`0.15`) and `PROFILE_RERANK_WEIGHT`
  (`0.05`) are frozen at the values already selected on dev for `Q` and `S`;
  they may not be re-tuned for the combination.

## Composition criterion, frozen before any run

Clearing the retention gate is not sufficient to retain `T`, because `T` is
only worth its extra complexity if combining beats the best single component.
Declared now:

- **`T` dev TechnicalScore must be at least `0.862083`**, the best single
  component dev score (`Q`).

The three outcomes are fixed in advance:

1. **Retention gate fails** → `T` is rejected, no holdout run, and the
   reportable dev row still stands as a recorded negative result.
2. **Retention gate passes, composition criterion fails** → the components do
   not compose beneficially. `T` is not retained, and the honest conclusion is
   to prefer the best single component over the combination. A holdout run is
   not spent on it.
3. **Both pass** → the combination genuinely composes, and `T` may be opened
   on holdout once.

A tie with `Q` counts as a composition failure: adding two more flags for no
measurable gain is complexity without benefit, which is the same conclusion
already recorded for config `V`.

## Holdout label, fixed in advance

`T` contains `Q`'s popularity prior. `Q`'s holdout is exploratory rather than
statistically untouched, because the popularity hypothesis followed an
aggregate review of target rating counts across all 200 public sessions. That
label is inherited: **any `T` holdout row must be reported as exploratory**,
and may never be presented as a clean untouched holdout result.

## Environment condition

Identical to the config `V` gate: the run must come from CPython 3.12 on
Linux x86-64 with `requirements-dense.lock.txt`, the official catalog
(`da979b05…`) and public set (`857259f7…`), and a clean commit.

Re-running `P` as an in-environment control is not required here. It was
already done at commit `547bdb1` in this same environment, where local `P`
reproduced canonical `P` on dev exactly across all five metrics; that evidence
is recorded in `facet-population-gate.tdd.md`. The canonical thresholds above
are therefore directly usable.

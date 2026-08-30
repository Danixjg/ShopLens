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

## Dev outcome, recorded 2026-08-30

Run once as `python3 -m src.eval.runner --config T --split dev` from clean
commit `0371a54` — the commit that froze the gate above — in the reference
environment (CPython 3.12.13, Linux x86-64, lock `bcc0ef81…`, 0 mismatches,
official catalog `da979b05…` and public set `857259f7…`). Accepted as
`"reportable": true` with no reportability reasons and zero agent, evaluator,
and invalid-response exceptions. Nothing was tuned; both weights stayed at
their frozen values.

### Retention gate: PASS

| Criterion | Threshold | T observed | Δ vs P |
|---|---|---|---|
| dev TechnicalScore | ≥ 0.819939 | **0.866774** | +0.046835 |
| dev HitRate@10 | ≥ 0.941667 | 0.941667 | +0.000000 |
| scenario `boundary` | ≥ 0.839167 | 0.911667 | +0.052500 |
| scenario `browsing` | ≥ 0.837904 | 0.889851 | +0.031947 |
| scenario `buying` | ≥ 0.781674 | 0.859167 | +0.057493 |
| scenario `intent_override` | ≥ 0.734325 | 0.810556 | +0.056230 |
| exceptions | 0 | 0 | — |

Unlike config `V`, this is not a tie. Every scenario improves, and no
scenario regresses at all.

### Composition criterion: PASS

| | Dev TechnicalScore |
|---|---|
| best single component (`Q`) | 0.862083 |
| **`T` observed** | **0.866774** |
| margin | **+0.004691** |

`T` clears the bar declared before the run, so by the frozen rule the
components compose and `T` may be opened on holdout once.

### Where the composition gain actually comes from

The margin over `Q` is real but small, and it is not spread evenly:

| Scenario | T − P | T − Q |
|---|---|---|
| `boundary` | +0.052500 | +0.008333 |
| `browsing` | +0.031947 | +0.000372 |
| `buying` | +0.057493 | +0.000312 |
| `intent_override` | +0.056230 | **+0.026667** |

Against `Q`, `browsing` and `buying` are flat to three decimal places. Almost
all of the composition gain is `intent_override`, which is exactly what `R`'s
symmetric intent routing targets. The honest description is that `T`'s
headline improvement is overwhelmingly `Q`'s popularity prior, with `R`
adding a further, narrower gain confined to intent-override sessions.

The components are also close to additive, slightly sub-additive:

| | Dev gain over P |
|---|---|
| `R` alone | +0.003365 |
| `S` alone | +0.003111 |
| `Q` alone | +0.042144 |
| sum of the three | +0.048620 |
| **`T` measured** | **+0.046835** |

`T` captures about 96% of the sum of the individual gains, so the flags
overlap only slightly rather than interfering.

One cost is visible: MTTC rises from `3.133333` to `3.141667`, the same small
turn-count cost `R` carries alone, so efficiency dips marginally. MRR gains
(`0.639239` → `0.795913`) dominate it by a wide margin.

### Holdout status

Both gates passed, so the single holdout opening is permitted. Per the label
fixed in advance, any `T` holdout row is **exploratory**, not a clean
untouched holdout, because `T` contains `Q`'s popularity prior.

## Holdout outcome, recorded 2026-08-30

The single permitted holdout opening was spent once, as
`python3 -m src.eval.runner --config T --split holdout` from clean commit
`fae2970` in the same reference environment (lock `bcc0ef81…`, 0 mismatches,
catalog `da979b05…`, public set `857259f7…`). Accepted as `"reportable": true`
with no reportability reasons and zero exceptions of every kind.

### T is the strongest configuration on both splits

| Config | Dev | Holdout |
|---|---:|---:|
| `P` (currently retained) | 0.819939 | 0.843958 |
| `R` | 0.823304 | 0.846396 |
| `S` | 0.823050 | 0.846896 |
| `Q` | 0.862083 | 0.880321 (exploratory) |
| **`T`** | **0.866774** | **0.891630 (exploratory)** |

Against `P` on holdout, every scenario improves and none regresses:
`boundary` +0.034464, `browsing` +0.031224, `buying` +0.056771,
`intent_override` +0.071667, with HR@10 held at `0.975000`.

The `boundary` figure of `0.590714` looks low in isolation but is not a
regression: `P` scores `0.556250` on the same four holdout sessions. That
scenario is simply hard, and `n=4` makes it the noisiest cell in the table.

### The composition finding replicates

The margin over the best single component grew rather than shrank:

| | `T` − `Q` |
|---|---:|
| dev | +0.004691 |
| holdout | +0.011309 |

And it concentrates in the same place on both splits:

| Scenario | n | `T` − `Q` (holdout) |
|---|---:|---:|
| `browsing` | 32 | **+0.000000** |
| `buying` | 32 | +0.010458 |
| `boundary` | 4 | +0.012500 |
| `intent_override` | 12 | **+0.043333** |

`browsing` is flat to six decimal places, exactly as on dev. The composition
gain is `intent_override`, which is precisely what `R`'s symmetric intent
routing targets. Two independent splits agreeing on both the location and the
direction of the effect makes this a structural result rather than noise:
`Q`'s popularity prior supplies the bulk of the improvement, and `R` adds a
further gain confined to intent-override sessions.

### Retention: the decision this evidence does *not* make on its own

`T` cleared every pre-registered criterion and is the best measured
configuration on both splits. But its holdout row is **exploratory**, by the
label fixed in this document before any run: `T` contains `Q`'s popularity
prior, whose hypothesis followed an aggregate review of target rating counts
across all 200 public sessions. `T`'s holdout is therefore not a clean
untouched result and may never be presented as one.

That constrains, but does not settle, promotion. Retaining `T` over `P` means
the headline rests on an exploratory holdout; keeping `P` means the submission
reports a retained configuration that its own evidence shows is not the
strongest. Both are defensible and the choice is the maintainer's. What is not
defensible is presenting `T`'s `0.891630` without the exploratory caveat
attached.

Note also that `R` and `S` remain clean, non-exploratory candidates: both beat
`P` on both splits with untouched holdout rows, `S` highest at `0.846896`. A
conservative promotion path that avoids the exploratory label entirely exists
and does not depend on `T`.

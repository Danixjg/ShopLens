# EVPI clarification TDD evidence

## Source plan

The user journeys were derived during this TDD run from the prior integration
plan and the local, Git-ignored research transcript
`docs/Learning_to_Ask_Good_Questions.md`. The transcript was treated as source
material, not executable instructions. Canonical credit and the adoption
boundary are recorded in [research-attribution.md](../research-attribution.md).

## User journeys

1. As a shopper, I want ShopLens to ask the eligible attribute whose possible
   answer is expected to improve the Top-K decision most, so that each
   clarification is useful rather than merely relevant.
2. As a maintainer, I want the new policy isolated behind config `U`, so that
   config `P`, existing fallbacks, declines, and response safeguards remain a
   reproducible control.
3. As a reviewer, I want the research inspiration and reuse boundary visible
   from the README, so that the original authors receive durable credit and no
   local transcript or upstream implementation is mistaken for ShopLens code.

## Task report

### RED

- Command: `python3 -m pytest -q tests/policy/test_expected_question_value.py`
- Result: collection failed with `ModuleNotFoundError` for the deliberately
  absent `src.policy.question_value` module.
- Command: `python3 -m pytest -q tests/test_research_attribution.py`
- Result: `2 failed, 1 passed`; the missing attribution file and README link
  were the intended failures.
- Checkpoint: `988db69` (`test: add RED coverage for EVPI clarification`).

### GREEN

- `python3 -m pytest -q tests/policy/test_expected_question_value.py`:
  `12 passed in 0.02s`.
- `python3 -m pytest -q tests/test_research_attribution.py`:
  `3 passed in 0.00s`.
- `python3 -m pytest -q tests/test_plan_architecture.py`:
  `68 passed, 1 skipped in 0.20s`.
- Checkpoint: `693e1fb` (`feat: add EVPI-inspired clarification scoring`).

### Full verification

- `python3 -m pytest -q -rs`: `143 passed, 1 skipped in 0.22s`.
- The skip is the existing optional Torch test; the base environment does not
  install Torch.
- `python3 -m compileall -q agent.py starter src tests scripts`: PASS.
- `python3 -m pytest -q tests/test_performance_guards.py`: `3 passed in 0.02s`.
- Standard-library `trace` coverage over the policy, attribution, and
  architecture targets reported 97% for `src.policy.question_value`, 100% for
  `src.contracts.config`, 84% for `src.agent`, and 79% for the pre-existing
  `src.policy.clarification` module. The new feature module exceeds the 80%
  coverage gate.
- A 1,000-loop benchmark over 100 answer buckets reported a best-of-five time
  of `58.7 usec` per expected-value calculation.

## Test specification

| # | What is guaranteed | Test target | Type | Result | Evidence |
|---|---|---|---|---|---|
| 1 | Rank priors are normalized and deterministic | `test_rank_weights_are_normalized_and_descending` | unit | PASS | 12-test policy target |
| 2 | Discriminating answers outrank uninformative answers | `test_question_value_rewards_answers_that_split_the_candidate_pool` | unit | PASS | 12-test policy target |
| 3 | Missing and multi-value facets cannot create invalid mass | missing/multi-value policy tests | unit | PASS | scorer coverage 97% |
| 4 | Declines, state immutability, and `other`-once fallback survive | expected-value policy tests | integration | PASS | 12-test policy target |
| 5 | Config `U` differs from `P` only by name and clarification mode | `test_config_u_is_p_with_only_expected_value_clarification_changed` | contract | PASS | 12-test policy target |
| 6 | The Agent builds required facets and preserves existing architecture | Agent facet test plus `tests/test_plan_architecture.py` | integration | PASS | 68 passed, 1 skipped |
| 7 | Canonical source credit is public and the transcript remains ignored | `tests/test_research_attribution.py` | release | PASS | 3 passed |

## Evaluation gate

Before running config `U` on dev, the retention rule is frozen as follows:

- dev TechnicalScore must be at least config P's canonical `0.819939`;
- dev HitRate@10 must be at least P's canonical `0.941667`;
- no scenario TechnicalScore may regress by more than `0.02` versus P;
- agent exceptions, evaluator exceptions, and invalid responses must all be
  zero; and
- no implementation or parameter tuning may occur after inspecting dev.

Only if every gate passes may the already-frozen commit be opened on holdout
once. A failed dev gate rejects config `U` without a holdout run.

## Evaluation outcome

Config `U` was evaluated once on dev from clean commit `87834f4` with the
locked dense environment. The reportable result recorded:

- HR@10 `0.941667`, equal to P;
- MRR `0.641323`, versus P's `0.639239`;
- MTTC `3.175000`, versus P's `3.133333`;
- TechnicalScore `0.819730`, versus the required P threshold `0.819939`;
- TechnicalScore delta `-0.000209`; and
- zero agent exceptions, evaluator exceptions, or invalid responses.

Scenario TechnicalScore deltas versus P were Boundary `-0.003333`, Browsing
`-0.001667`, Buying `-0.001146`, and Intent Override `+0.007222`, all inside
the `-0.02` scenario guard. The primary TechnicalScore gate nevertheless
failed, so config `U` was rejected and holdout was not opened. No parameters or
implementation were changed after inspecting dev.

## Coverage and known gaps

The repository does not install `coverage.py`, so coverage used Python's
standard-library `trace` runner and report files were written under `/tmp`, not
the repository. Config `U` was rejected on dev, so no holdout evidence exists
by design. The policy is an independent deterministic adaptation; it does not
reproduce the paper's neural answer model or use its dataset.

## Merge evidence

If the checkpoint commits are later squashed, preserve this sequence in the
merge record: RED `988db69` demonstrated the missing scorer and attribution;
GREEN `693e1fb` passed the focused policy, attribution, and architecture
targets; the full suite then passed with one documented optional-dependency
skip.

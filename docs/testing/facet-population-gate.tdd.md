# Facet population gate TDD evidence (config V)

## Source plan

This cycle implements the single behavioral item marked Adopt in the
[ProductAgent source audit](../productagent-integration.md): filter
clarification aspects by field population. The idea is credited to Ye et al.,
arXiv:2407.00942, and is implemented independently against ShopLens's own
catalog and contract. No upstream code or data was consulted.

Scope is implementation and unit tests only. No evaluation run was performed,
by explicit instruction. The retention gate below is frozen before any run, so
the decision rule cannot be chosen after seeing a result.

## User journeys

1. As a shopper, I want ShopLens to spend its clarification turn on a question
   the catalog can actually answer, so that a turn is not wasted on a facet no
   candidate carries.
2. As a maintainer, I want the change isolated behind config `V`, so that `P`
   remains an untouched reproducible control.
3. As a reviewer, I want the agent to keep asking something even when no facet
   is well populated, so that the gate cannot make the agent go silent.

## The gap this closes

`ClarificationPolicy._information_choice` filters candidate facets by asked and
declined status only. On an over-general turn the info-gain score already
discounts unpopulated facets, because `_information_gain` treats a missing
value as uninformative. On a **targeted** turn, however, the policy returned
`unasked[0]` in fixed sequence order with no population check at all. With
`feature` already asked and `material` unpopulated across the pool, config `P`
asks about `material`, which no candidate can answer.

`test_ungated_baseline_still_asks_the_unanswerable_facet` pins that behavior
and passed before any implementation existed, which is what establishes the gap
as real rather than hypothetical.

## Finding: the asked-aspect diversity guard is unnecessary

The plan named a second config for the paper's question-redundancy pitfall. It
was not built, because the mechanism already exists. `CLARIFICATION_SEQUENCE`
is a fixed three-attribute tuple plus a once-only `other`; every branch of
`_fixed_choice`, `_information_choice`, and `_expected_value_choice` filters on
`state.asked_attributes`, and `src/agent.py:195-196` appends each asked
attribute. There is no path that re-asks. A diversity guard would have been an
inert config consuming an evaluation slot.

The paper's redundancy problem is a property of generated question text under a
prompt constraint, not of selection from an enumerated set. Recorded as
"Already satisfied" in the audit, with a recheck trigger if the attribute set
ever becomes generated.

## Retention gate, frozen before any run

Config `V` may be evaluated once on the deterministic 120-session dev split
from a clean commit in the reference environment. The rule is fixed now:

- dev TechnicalScore must be at least config P's canonical `0.819939`;
- dev HitRate@10 must be at least P's canonical `0.941667`;
- no scenario TechnicalScore may regress by more than `0.02` versus P;
- agent exceptions, evaluator exceptions, and invalid responses must all be
  zero; and
- no implementation or parameter tuning may occur after inspecting dev.

Only if every gate passes may the already-frozen commit be opened on holdout
once. A failed dev gate rejects `V` without a holdout run, and the reportable
dev record stays in `results.jsonl` either way.

Environment condition, additional to the EVPI gate: the run must come from the
reference environment used for P's canonical rows, CPython 3.12 on Linux
x86-64 with `requirements-dense.lock.txt`. A run on a different platform is
not comparable to P's canonical threshold; if one is unavoidable, P must be
re-run in the same environment as a control and both rows labelled as local
control evidence rather than compared to the canonical number.

## Task report

| Plan task | Test target | RED evidence | GREEN evidence |
|---|---|---|---|
| Register config V as P plus one flag | `test_config_v_is_p_with_only_the_population_gate_changed` | `python3 -m pytest -q tests/policy/test_facet_population_gate.py` reported `8 failed, 2 passed`; `CONFIGS["V"]` raised `KeyError`. | `10 passed in 0.12s` after adding `facet_population_gate` and config `V`. |
| Gate facet eligibility on catalog population | gate behavior tests | Failed with `KeyError: 'V'` before the policy change. | Passed; the targeted turn now selects `color` rather than the unanswerable `material`. |
| Preserve P, declines, and state immutability | baseline, decline, no-repeat, and state tests | Baseline test passed from the start by design, pinning the gap. | All pass; P still asks `material`, so the control is untouched. |
| Keep the agent able to ask | `test_gate_falls_back_rather_than_going_silent`, `test_gate_is_inert_without_a_catalog` | Failed before implementation. | Pass; the gate returns the ungated list when nothing is populated and is skipped entirely without a catalog. |
| Declare the config addition | `tests/test_plan_architecture.py::test_ablation_matrix_has_exact_names` | Full suite reported `1 failed, 165 passed, 1 skipped`, naming `V` as an extra item. | Updated the pinned set to `ABCDEFGHPQRSTUVZ`; full suite `166 passed, 1 skipped`. |

## Test specification

| # | What is guaranteed | Test target | Type | Result | Evidence |
|---|---|---|---|---|---|
| 1 | V differs from P only by name and the population gate. | `test_config_v_is_p_with_only_the_population_gate_changed` | Contract | PASS | Targeted run: 10 passed |
| 2 | The fixture really leaves material unpopulated and color populated. | `test_fixture_leaves_material_unpopulated` | Precondition | PASS | Targeted run: 10 passed |
| 3 | A targeted turn skips a facet no candidate can answer. | `test_gate_skips_an_unanswerable_facet_on_a_targeted_turn` | Unit | PASS | Targeted run: 10 passed |
| 4 | The ungated baseline still asks it, so P is unchanged and the gap is real. | `test_ungated_baseline_still_asks_the_unanswerable_facet` | Regression control | PASS | Passed before and after implementation |
| 5 | An unpopulated facet is never chosen while a populated one exists, on either turn type. | `test_gate_never_returns_an_unpopulated_facet_when_a_populated_one_exists` | Unit | PASS | Targeted run: 10 passed |
| 6 | The gate never leaves the agent unable to ask. | `test_gate_falls_back_rather_than_going_silent` | Unit | PASS | Targeted run: 10 passed |
| 7 | Declined attributes stay ineligible under the gate. | `test_gate_respects_declined_attributes` | Unit | PASS | Targeted run: 10 passed |
| 8 | An asked attribute is never repeated under the gate. | `test_gate_never_repeats_an_asked_attribute` | Unit | PASS | Targeted run: 10 passed |
| 9 | Choosing does not mutate session state. | `test_gate_leaves_session_state_unchanged` | Unit | PASS | Targeted run: 10 passed |
| 10 | Without a catalog the gate is inert and matches P. | `test_gate_is_inert_without_a_catalog` | Unit | PASS | Targeted run: 10 passed |

## Validation and coverage

- Baseline before this cycle: `python3 -m pytest -q` reported
  `156 passed, 1 skipped`.
- RED: `python3 -m pytest -q tests/policy/test_facet_population_gate.py`
  reported `8 failed, 2 passed in 0.29s`.
- GREEN: the same command reported `10 passed in 0.12s`.
- Registry: the full suite first reported `1 failed, 165 passed, 1 skipped`
  for the pinned config-name set, then `166 passed, 1 skipped` after `V` was
  declared.
- `python3 -m compileall -q agent.py starter src tests scripts`: PASS.
- `git diff --check`: PASS.
- Coverage used the standard-library `trace` runner over `tests/policy` and
  `tests/test_plan_architecture.py`, since the repository does not install
  `coverage.py`. It reported 90% for `src.policy.clarification`, 100% for
  `src.contracts.config`, and 97% for `src.policy.question_value`. Every line
  of the new `_eligible` method executed, including the disabled and
  no-catalog short circuit and the fallback return. The 80% gate is met.

## Known gaps

- `V` is unevaluated. No dev or holdout run exists, so it is not retained and
  has no `results.jsonl` row. Its effect on HitRate@10, MRR, and MTTC is
  unmeasured, and nothing in this cycle claims an improvement.
- Population is measured as at least one populated value in the pooled
  candidates. A facet populated for a single candidate still passes the gate;
  a proportional threshold was not introduced because it would add a tuned
  parameter before any evidence justifies one.
- `ClarificationPolicy._covered` is unused dead code, predating this cycle. It
  was left untouched to keep this diff to one behavior.

## Merge evidence

- RED checkpoint: `fd3ec8c test: require a facet population gate for clarification`
- GREEN checkpoint: `8f12a09 feat: add facet population gating for clarification (config V)`

Both checkpoints were created on `docs/productagent-source-audit`. Preserve
this RED/GREEN summary in the PR or squash commit body if the commits are later
squashed.

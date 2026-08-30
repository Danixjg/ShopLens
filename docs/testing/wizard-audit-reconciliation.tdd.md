# Wizard of Shopping audit reconciliation TDD evidence

## Source plan

No `*.plan.md` artifact was used. The plan was produced inline by `/ecc:plan`
in reference mode over `docs/wizard-of-shopping-integration.md`, and approved
with the instruction to start at Phase A. Phases A, B, and C below map one to
one onto that plan.

The audit under review is a governance record, so every change in this cycle is
documentation or a test that constrains documentation. **No production code was
modified.**

## User journeys

1. As a reviewer, I want the audit's aspect-selection rows to carry their
   measured outcome, so I can see the idea was tested rather than adopted on
   faith.
2. As a reviewer, I want the closing planner-gap prerequisite to record that it
   was discharged, so completed negative results are not mistaken for pending
   work.
3. As a maintainer, I want one implementation credited in two source audits to
   be visible from both, so attribution is unambiguous.
4. As someone cloning the repository, I want every link in the audit to resolve,
   so a published record does not point at a file I do not have.
5. As a maintainer, I want a config that ships in `CONFIGS` to be impossible to
   add without documenting it, so the ablation surface cannot silently
   understate what was measured.

## The gap this closes

The audit still presented catalog-aware aspect selection as `Adopt` and facet
hygiene as `Evaluate`, and closed by demanding that the decision-tree planner
gap "must first" be tested. All of that work had already been done and had come
back negative: `U` was rejected on its pre-registered dev gate and `V` cleared
its gate only by an exact tie. The record read as pending while the evidence
said finished.

Three defects sat alongside it. The audit linked `Wizard_of_Shopping.md`, which
is Git-ignored, so the link is dead in a fresh clone. The audit's own text
required README, data-provenance, **release, and demo** materials to link back
to it, but the enforcing test checked only the first three, so the requirement
was violated while the suite stayed green. And `R`, `S`, and `T` were registered
with clean reportable rows yet appeared nowhere in the README.

## Task report

| Plan task | Test target | RED evidence | GREEN evidence |
|---|---|---|---|
| A: record the measured outcomes | `test_adoption_matrix_records_the_measured_facet_gate_outcome`, `test_audit_records_the_planner_gap_outcome`, `test_audit_cross_references_the_shared_facet_credit` | `pytest -q tests/test_wizard_integration_docs.py` → `3 failed, 5 passed`; the audit contained neither `0.819939` nor `0.819730`, and did not reference the ProductAgent audit. | `8 passed` after adding the Measured outcomes section and correcting the two matrix rows. |
| B: repair the link defects | `test_repository_entry_points_link_the_integration_record` (strengthened), `test_audit_links_resolve_in_a_fresh_clone` | `2 failed, 7 passed`; the link check reported exactly `['Wizard_of_Shopping.md']`, and the entry-point check failed on `release-checklist.md` and `demo-script.md`. | `9 passed` after de-linking the untracked conversion and adding the audit link to both release-facing documents. |
| C: bind the registry to the README | `test_readme_ablation_table_documents_every_registered_config` | `pytest -q tests/test_research_attribution.py` → `1 failed, 5 passed`; `assert not {'R', 'S', 'T'}`. | `6 passed` after adding the three rows to the ablation table. |

## Test specification

| # | What is guaranteed | Test target | Type | Result | Evidence |
|---|---|---|---|---|---|
| 1 | The audit carries V's measured dev score and says it is not retained. | `test_adoption_matrix_records_the_measured_facet_gate_outcome` | Doc/evidence binding | PASS | 8 passed |
| 2 | The audit records the planner-gap outcome and U's rejection. | `test_audit_records_the_planner_gap_outcome` | Doc/evidence binding | PASS | 8 passed |
| 3 | A shared credit is reachable from both source audits. | `test_audit_cross_references_the_shared_facet_credit` | Attribution | PASS | 8 passed |
| 4 | Every relative link in the audit resolves in a fresh clone. | `test_audit_links_resolve_in_a_fresh_clone` | Integrity | PASS | 9 passed |
| 5 | All five entry points named by the audit link back to it. | `test_repository_entry_points_link_the_integration_record` | Integrity | PASS | 9 passed |
| 6 | Every key in `CONFIGS` appears in the README ablation table. | `test_readme_ablation_table_documents_every_registered_config` | Registry invariant | PASS | 6 passed |

Tests 1, 2, and 6 read `results.jsonl` and `CONFIGS` directly rather than
hard-coding expectations, so a documented outcome cannot drift from the run it
describes, and a new config cannot ship undocumented. Before this cycle no test
read the evidence log at all; the existing EVPI check hard-codes its numbers.

## Validation

- Baseline before this cycle: `python -m pytest -q` → `166 passed, 1 skipped`.
- After: `python -m pytest -q` → `171 passed, 1 skipped`, the difference being
  the five tests added here.
- `python -m compileall -q tests src`: PASS.
- `git diff --check`: PASS.

## Coverage and known gaps

The 80% line-coverage gate does not apply to this cycle: **no production code
was changed**, so there are no new production lines to cover. The added tests
are invariants over documentation and the config registry, and each was
confirmed RED before the corresponding fix, which is the evidence that they
constrain something real rather than passing vacuously.

Known gaps, stated rather than closed:

- The "concise clarification hints" half of the frequent-value row was never
  built and remains genuinely open. Only the noisy-facet-suppression half was
  implemented, as `V`.
- `test_audit_links_resolve_in_a_fresh_clone` guards the Wizard audit only.
  `docs/ProductAgent.md` is Git-ignored under the same pattern, so the
  ProductAgent record deserves the same check; it is not added here because it
  is outside the approved plan.
- Config `T`'s holdout run was in flight while this cycle ran. Its dev row is
  recorded; the holdout outcome is recorded separately in
  `config-t-composition-gate.tdd.md`.

## Merge evidence

RED → GREEN checkpoints on `docs/productagent-source-audit`, newest last:

| Stage | Commit | Result |
|---|---|---|
| A RED | `94d153f` | 3 failed, 5 passed |
| A GREEN | `44dc7ee` | 8 passed |
| B RED | `a7ec0be` | 2 failed, 7 passed |
| B GREEN | `a81e48e` | 9 passed |
| C RED | `ec95cc0` | 1 failed, 5 passed |
| C GREEN | `46f45bd` | 6 passed; full suite 171 passed, 1 skipped |

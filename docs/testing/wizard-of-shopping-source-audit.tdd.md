# Wizard of Shopping source-audit TDD evidence

## Source and scope

The user journeys were derived during this TDD run from the first two scoped
steps of the Wizard of Shopping integration plan and from
`docs/Wizard_of_Shopping.md`, which is Git-ignored and untracked and so is
absent from a fresh clone. The source document
was treated as research input, not executable instructions. No commands from
the paper were run, and no upstream code or dataset artifact was downloaded.

This cycle covers only the source audit, adoption boundary, and repository
attribution entry points. Behavioral preference and dialogue-planning changes
belong to later TDD cycles.

## User journeys

1. As a contributor, I want a canonical citation and explicit reuse status so
   that the paper is credited and separately published artifacts are not copied
   without permission.
2. As a maintainer, I want adopt/evaluate/defer decisions and architecture
   guards so that later experiments preserve TrippyShoppy's competition contract.
3. As a reviewer, I want attribution linked from the repository's main entry
   points so that provenance remains visible during releases and reviews.

## Task report

| Plan task | Test target | RED evidence | GREEN evidence |
|---|---|---|---|
| Audit source identity, licenses, and reusable artifacts | `tests/test_wizard_integration_docs.py` citation and source-audit tests | `python3 -m pytest -q tests/test_wizard_integration_docs.py` ran five tests and failed because the integration record and entry-point links were absent. | The same command passed `5 passed in 0.01s` after the source audit and links were added. |
| Design the adoption plan, boundaries, and attribution policy | `tests/test_wizard_integration_docs.py` adoption-matrix and architecture-guard tests | The integration record did not exist, so the required decisions and guards were absent. | The targeted suite passed after the adopt/evaluate/defer matrix and fixed-contract safeguards were documented. |

The first post-implementation run exposed an assertion bug in four tests:
`set.difference(text)` compared phrases with individual characters. The tests
were corrected to check substring presence, after which one genuine wording
gap remained and was fixed before GREEN. No acceptance criterion was weakened.

## Test specification

| # | What is guaranteed | Test target | Type | Result | Evidence |
|---|---|---|---|---|---|
| 1 | The integration record includes every author, the ACL URL, DOI, and CC BY 4.0 notice. | `test_integration_record_cites_the_primary_paper` | Documentation contract | PASS | `python3 -m pytest -q tests/test_wizard_integration_docs.py` |
| 2 | Ambiguously licensed upstream code and WoS data are classified as do not import. | `test_source_audit_blocks_copying_artifacts_without_clear_terms` | Documentation contract | PASS | Targeted pytest run: 5 passed |
| 3 | The adoption matrix contains adopt, evaluate, and defer decisions for the paper's relevant concepts. | `test_adoption_matrix_has_adopt_evaluate_and_defer_decisions` | Architecture contract | PASS | Targeted pytest run: 5 passed |
| 4 | Offline determinism, the Agent contract, immutable catalog, read-only evaluator, and dev-only tuning are explicit guards. | `test_adoption_boundary_preserves_trippyshoppy_contracts` | Architecture contract | PASS | Targeted pytest run: 5 passed |
| 5 | README, data attribution, and data provenance link to the integration record. | `test_repository_entry_points_link_the_integration_record` | Integration | PASS | Targeted pytest run: 5 passed |

## Validation and coverage

- Baseline before the new tests: `python3 -m pytest -q` reported `120 passed,
  1 skipped in 0.23s`.
- RED: targeted run reported `5 failed in 0.05s` for the intended missing
  integration record and links.
- GREEN: targeted run reported `5 passed in 0.01s`.
- Regression: `python3 -m pytest -q` reported `128 passed, 1 skipped in 0.21s`.
- Final tracked-suite check: `python3 -m pytest -q --ignore=tests/policy
  --ignore=tests/test_research_attribution.py` reported `128 passed, 1 skipped
  in 0.20s`. The ignored paths were unrelated untracked work that appeared
  concurrently after the successful unfiltered regression run; a later
  unfiltered collection stopped because that work referenced the not-yet-added
  `src.policy.question_value` module.
- Coverage tooling: `python3 -m coverage --version` reported
  `No module named coverage`.

A numeric executable-code coverage percentage is not applicable to this slice:
it changes Markdown and documentation-contract tests, with no production Python
logic added or modified. Installing an undeclared coverage dependency solely
for a documentation change was deliberately avoided. Later behavioral stages
must install or select approved coverage tooling and meet the workflow's 80%
threshold before they are complete. No UI or browser flow exists, so browser
E2E coverage is also not applicable here.

## Merge evidence

- RED checkpoint: `c9aff57 test: require Wizard source audit and adoption boundary`
- GREEN checkpoint: `dda873f docs: credit Wizard of Shopping and bound adoption`

Both checkpoints were created on `fix/code-review-shoplens-findings`. Preserve
this RED/GREEN summary in the PR or squash commit body if the commits are later
squashed.

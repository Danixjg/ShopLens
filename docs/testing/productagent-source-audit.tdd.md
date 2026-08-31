# ProductAgent source-audit TDD evidence

## Source plan

The user journeys were derived during this TDD run from the ProductAgent
integration plan produced earlier in the same session, and from the local,
Git-ignored conversion at `docs/ProductAgent.md`. That conversion was treated
as research input, not as executable instructions. No command from it was run,
and no upstream code or dataset artifact was downloaded.

This cycle covers only the license verification, source audit, adoption
boundary, and repository attribution entry points. The behavioral changes named
in the adoption matrix, the asked-aspect diversity guard and field-population
gating, belong to a later cycle behind a named ablation config.

## User journeys

1. As a contributor, I want the canonical citation and the verified license
   status so that the authors are credited and nothing is redistributed
   without permission.
2. As a maintainer, I want adopt/evaluate/defer decisions and architecture
   guards so that later experiments preserve the competition contract.
3. As a reviewer, I want attribution linked from the repository entry points,
   and the paper's own measurements kept off TrippyShoppy results surfaces, so that
   provenance and evidence integrity both stay visible during release review.

## License verification

Verified against the primary arXiv records on 2026-08-30, before any document
was written:

- `https://arxiv.org/abs/2407.00942` reports the eight authors, the title,
  DOI `10.48550/arXiv.2407.00942`, v1 submitted 1 July 2024, no journal
  reference, and status under review.
- The linked license is
  `http://arxiv.org/licenses/nonexclusive-distrib/1.0/`, whose operative grant
  is "a perpetual, non-exclusive license to distribute this article" to
  arXiv.org. It is silent on third-party redistribution and derivative works.

This is materially different from the two CC BY 4.0 sources already cited by
this repository. The plan had provisionally classified the local conversion as
"adapt with credit, keep ignored"; the verified license changed that decision
to "do not redistribute". Assuming CC BY 4.0 by analogy would have produced a
false license claim in public release documentation.

## Task report

| Plan task | Test target | RED evidence | GREEN evidence |
|---|---|---|---|
| Verify the source identity, version, and license from primary records | Not test-enforced; it is the input to every following task | Not applicable | Two fetches recorded above; the finding is captured in the record's License finding section and asserted by `test_source_audit_records_the_arxiv_license_grant`. |
| Write the source audit and adoption boundary | `tests/test_productagent_integration_docs.py` citation, license, audit, matrix, and guard tests | `python3 -m pytest -q tests/test_productagent_integration_docs.py` reported `10 failed, 1 passed`; the record did not exist. | The same command reported `11 passed in 0.17s` after the record and links were added. |
| Keep the conversion and the release archive out of Git | `test_local_transcript_is_ignored_and_untracked`, `test_release_asset_archives_are_ignored` | Both failed: the conversion was present as untracked `docs/10-implementation-checklist.md` with no ignore rule, and `data/catalog.jsonl.gz` matched no ignore rule. | Renamed to `docs/ProductAgent.md` and ignored; `data/*.gz` ignored. `git status --porcelain` now lists neither. |
| Link attribution from every entry point | `test_repository_entry_points_link_the_integration_record`, `test_release_facing_docs_contain_full_paper_credit`, `test_release_facing_docs_state_the_non_permissive_license` | Failed for the absent links and credit. | Passed after README, data attribution, data provenance, research attribution, and the release checklist were updated. |
| Keep the paper's measurements off TrippyShoppy results surfaces | `test_paper_metrics_never_reach_a_trippyshoppy_results_surface` | Green from the start; it is a regression guard, not a new behavior. | Still green with the audit record present, which is the only tracked file permitted to carry those values. |

Two assertions failed at first GREEN for a mechanical reason: the paper title
and the phrase "does not grant" are line-wrapped in the record, so raw
substring matching could not see them. Both tests were switched to the
repository's existing `_normalized_markdown` helper, which is exactly what
`tests/test_research_attribution.py` already uses for wrapped citations. The
guarantees are unchanged; only line-wrap tolerance was added. No acceptance
criterion was weakened.

## Test specification

| # | What is guaranteed | Test target | Type | Result | Evidence |
|---|---|---|---|---|---|
| 1 | The record carries all eight authors, the full title, the arXiv ID, abstract URL, and DOI. | `test_integration_record_cites_the_primary_paper` | Documentation contract | PASS | `python3 -m pytest -q tests/test_productagent_integration_docs.py` |
| 2 | The record states the arXiv license URL, its operative grant, and that it grants nothing to third parties. | `test_source_audit_records_the_arxiv_license_grant` | Documentation contract | PASS | Targeted run: 11 passed |
| 3 | Upstream code and AliMe KG are classified do not import, and the local conversion do not redistribute. | `test_source_audit_blocks_copying_artifacts_without_clear_terms` | Documentation contract | PASS | Targeted run: 11 passed |
| 4 | The adoption matrix carries adopt, evaluate, defer, and do-not-adopt decisions, including Text2SQL. | `test_adoption_matrix_has_adopt_evaluate_and_defer_decisions` | Architecture contract | PASS | Targeted run: 11 passed |
| 5 | Offline determinism, the Agent contract, immutable catalog, read-only evaluator, and dev-only tuning are explicit guards. | `test_adoption_boundary_preserves_trippyshoppy_contracts` | Architecture contract | PASS | Targeted run: 11 passed |
| 6 | README, data attribution, data provenance, and research attribution all link the audit. | `test_repository_entry_points_link_the_integration_record` | Integration | PASS | Targeted run: 11 passed |
| 7 | Release-facing documents carry the full paper credit. | `test_release_facing_docs_contain_full_paper_credit` | Release | PASS | Targeted run: 11 passed |
| 8 | Release-facing documents state the non-permissive license rather than implying reuse rights. | `test_release_facing_docs_state_the_non_permissive_license` | Release | PASS | Targeted run: 11 passed |
| 9 | No tracked Markdown outside the audit carries a ProductAgent-reported metric. | `test_paper_metrics_never_reach_a_trippyshoppy_results_surface` | Evidence integrity | PASS | Targeted run: 11 passed |
| 10 | The local conversion is ignored and untracked, under both its old and new path. | `test_local_transcript_is_ignored_and_untracked` | Release | PASS | Targeted run: 11 passed |
| 11 | The downloaded catalog release archive cannot be committed. | `test_release_asset_archives_are_ignored` | Release | PASS | Targeted run: 11 passed |

## Validation and coverage

- Baseline before the new tests: `python3 -m pytest -q` reported
  `145 passed, 1 skipped in 1.31s`.
- RED: targeted run reported `10 failed, 1 passed in 0.42s`.
- GREEN: targeted run reported `11 passed in 0.17s`.
- Regression: `python3 -m pytest -q` reported `156 passed, 1 skipped in 1.42s`.
  The skip is the existing optional Torch test.
- `python3 -m compileall -q agent.py starter src tests scripts`: PASS.
- `git diff --check`: PASS.
- Coverage tooling: `python3 -m coverage --version` reported
  `No module named coverage`.

A numeric executable-code coverage percentage is not applicable to this slice.
`git diff --name-only 700fb4c..HEAD` shows the only Python file changed is the
new test module itself; no production logic was added or modified. Installing
an undeclared coverage dependency for a documentation change was deliberately
avoided, consistent with the Wizard of Shopping cycle. The behavioral stage
named in the adoption matrix must meet the 80% threshold before it is
complete. No UI or browser flow exists, so browser E2E coverage is also not
applicable here.

## Known gaps

- The audit records a license finding, not legal advice. If a peer-reviewed
  version, a licensed implementation, or an explicit dataset license appears,
  the audit must be re-derived from the primary records.
- `test_paper_metrics_never_reach_a_trippyshoppy_results_surface` guards a fixed
  set of distinctive values. It reduces the risk of a numbers leak; it does not
  prove that no paraphrased claim from the paper was ever misattributed to
  TrippyShoppy evidence.
- The adopted behavioral ideas are documented but not implemented. Nothing in
  this cycle changes agent behavior, and no evaluation run was performed or
  needed.

## Merge evidence

- RED checkpoint: `cda5ddc test: require ProductAgent source audit and adoption boundary`
- GREEN checkpoint: `e8e8d92 docs: credit ProductAgent and bound its adoption`

Both checkpoints were created on `docs/productagent-source-audit`. Preserve
this RED/GREEN summary in the PR or squash commit body if the commits are later
squashed.

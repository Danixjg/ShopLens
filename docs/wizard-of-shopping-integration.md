# Wizard of Shopping source audit and adoption boundary

This record governs how TrippyShoppy may use ideas from *Wizard of Shopping* and
its TRACER methodology. It separates attribution for the paper from permission
to copy the separately published code or dataset. No upstream TRACER code or
Wizard of Shopping (WoS) dataset bytes are included in this repository.

## Canonical citation

Xiangci Li, Zhiyu Chen, Jason Ingyu Choi, Nikhita Vedula, Besnik Fetahu,
Oleg Rokhlenko, and Shervin Malmasi. 2025. *Wizard of Shopping:
Target-Oriented E-commerce Dialogue Generation with Decision Tree Branching*.
In Proceedings of the 63rd Annual Meeting of the Association for Computational
Linguistics (Volume 1: Long Papers), pages 13095–13120. Association for
Computational Linguistics.

- ACL Anthology: https://aclanthology.org/2025.acl-long.641/
- DOI: https://doi.org/10.18653/v1/2025.acl-long.641
- Historical arXiv version: https://arxiv.org/abs/2502.00969
- Authors' reference repository: https://github.com/jacklxc/Wizard-of-Shopping
- License for the ACL 2025 paper: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)

The local Codex-oriented conversion (`docs/Wizard_of_Shopping.md`, which is
Git-ignored and never redistributed, so it is absent from a fresh clone) was
made from
arXiv:2502.00969v1 before the final ACL record was available. TrippyShoppy cites
the final ACL publication as canonical and identifies the local restructuring
and technical index as changes to the source presentation. CC BY 4.0 requires
appropriate credit, a license link, and an indication of changes.

## Source audit

The decisions below were checked against the primary records on 2026-08-30.
They are conservative engineering controls, not legal advice.

| Artifact | Decision | Evidence and constraint |
|---|---|---|
| ACL 2025 paper | Adapt with credit | ACL identifies the paper and DOI and licenses post-2016 Anthology materials under CC BY 4.0. Prefer paraphrase; credit the authors, link the source and license, and identify modifications. |
| arXiv v1 and local conversion | Adapt with credit | The arXiv record links CC BY 4.0. The local Markdown changes the presentation and must retain source/version metadata. |
| Upstream code | Do not import | The public repository says the code is provided for “research purposes” but exposes no standard license file in its root. That notice is not treated as permission to copy, modify, or redistribute code. Independent implementation from the published method remains allowed subject to review. |
| WoS dataset | Do not import | The repository offers the zip for benchmarking but gives no distinct dataset license; it directs users to TREC Product Search data terms. Do not download, commit, train on, or redistribute it until those terms and all upstream data licenses are documented as compatible. |
| TREC Product Search inputs | Do not import | They are not part of TrippyShoppy's Amazon Reviews 2023 competition package. Any future use requires a separate provenance and license review. |

If the upstream repository later adds explicit licenses, update this audit from
the primary records before changing a decision. Public availability alone is
not sufficient permission to copy an artifact.

## TrippyShoppy adoption matrix

| Decision | TRACER/WoS concept | TrippyShoppy treatment |
|---|---|---|
| Adopt | Wanted, unwanted, and optional preference semantics | Extend the existing slot and declined-attribute model only where tests show missing behavior. Implement independently and cite TRACER as the methodological influence. |
| Tested, not retained | Catalog-aware aspect selection | Built as ablation config `V` and measured once on the frozen dev split. It tied `P` exactly, so the existing candidate-pool information-gain policy stands unchanged. See [Measured outcomes](#measured-outcomes). |
| Evaluate | Attributed synthetic dialogue fixtures | Generate fixtures only from the immutable TrippyShoppy catalog and deterministic local rules. Mark them as TrippyShoppy-generated and TRACER-inspired; do not derive them from WoS dialogue text. |
| Evaluate, half answered | Frequent-value clarification hints and facet hygiene | Noisy-facet suppression was built as `V`, produced no ranking evidence, and is not retained. Concise clarification hints were never built and remain genuinely open, still subject to the same dev-split rule. |
| Defer | Upstream TRACER implementation and WoS dataset | Keep both outside the repository until explicit compatible terms are verified. Do not translate or mechanically reproduce upstream source code. |
| Defer | LLM verbalization and CQG/CPR fine-tuning | TrippyShoppy must remain useful offline and deterministic. These experiments require a separate approved plan, dependencies, model provenance, and resource budget. |

## Measured outcomes

Two ideas from this audit were implemented independently, isolated behind named
ablation configs, and measured once each on the deterministic 120-session dev
split under pre-registered retention gates. Neither was retained. The gates were
frozen before the runs, so these are decisions the evidence made, not decisions
made about the evidence.

| Config | Idea under test | Dev TechnicalScore | Outcome |
|---|---|---:|---|
| `P` | retained baseline | `0.819939` | — |
| `U` | expected-question-value clarification, the planner comparison this record demanded | `0.819730` | **Rejected on the gate.** Below P, so holdout was never opened. |
| `V` | catalog-population gating of clarification facets | `0.819939` | **Cleared the gate only by an exact tie. Not retained.** |

`U` is the direct test of the decision-tree planner gap. It adapts the paper's
expected-value-of-information idea into a target-free expected Top-K posterior
mass. HR@10 held at P's value and MRR rose slightly, but MTTC moved from
`3.133333` to `3.175000`, so TechnicalScore fell by `0.000209` and the
pre-registered gate rejected it without a holdout run.

`V` is the catalog-aware aspect-selection test. It matched `P` to the last
recorded digit on every metric, every scenario, and the turn count. The cause is
measurable rather than mysterious: the gate drops a facet only when *no*
candidate in the pool carries a value for it, and across the 50,000-product
official catalog `feature` — which is asked first — is populated on **99.43%**
of products (`material` 58.09%, `color` 32.84%, with only 245 products empty on
all three). The condition the unit tests construct synthetically does not arise
in real retrieved pools, so the gate never fires.

The honest reading is that this record's caution was vindicated. The paper's
methods are sound, but on TrippyShoppy's catalog and contract the existing
information-gain policy already captures the available benefit, and two
independent attempts to improve on it measured no gain. A rejected config with a
reportable row is a stronger result than an adopted idea with no measurement.

### Shared credit with the ProductAgent audit

Catalog-population facet filtering is claimed by two source audits. The
implementation credits Ye et al. (ProductAgent, arXiv:2407.00942) in
[`productagent-integration.md`](productagent-integration.md), which is where its
adoption boundary is recorded; this record lists the same behavior as
catalog-aware aspect selection. One implementation, two independent
motivations, one credit — noted here so the overlap is not mistaken for two
separate adoptions.

## Non-negotiable architecture guards

- Preserve offline determinism for every reportable configuration.
- Preserve the fixed public Agent contract and allowed
  `ask_attribute` values.
- Keep the immutable catalog checksum-verified.
- Keep the organizer evaluator a read-only evaluator.
- Tune new policy behavior on the deterministic dev-only split before any
  holdout run, and label exploratory evidence honestly.
- Introduce behavioral changes behind named ablation configurations so the
  current baseline remains reproducible.

The current information-gain clarification policy already implements the
central intuition of asking about a facet that divides the remaining candidate
space. This record previously required that the behavioral gap between that
policy and the paper's repeatedly fitted decision-tree planner be tested before
any adoption, on the principle that sharing an intuition is not evidence that a
second implementation improves TrippyShoppy. **That prerequisite has been
discharged.** Both experiments were run and both came back negative; the
results are recorded in [Measured outcomes](#measured-outcomes) below.

## Attribution for future derivatives

Any future module that materially adapts TRACER's published method must name
the paper and DOI in its module documentation. Generated fixture files must
record the generator version, catalog checksum, random seed, the canonical
paper URL, and a statement that the records are TrippyShoppy-generated rather than
copied from WoS. README, data-provenance, release, and demo materials must link
back to this audit so the distinction remains visible.

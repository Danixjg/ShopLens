# Wizard of Shopping source audit and adoption boundary

This record governs how ShopLens may use ideas from *Wizard of Shopping* and
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

The local [Codex-oriented conversion](Wizard_of_Shopping.md) was made from
arXiv:2502.00969v1 before the final ACL record was available. ShopLens cites
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
| TREC Product Search inputs | Do not import | They are not part of ShopLens's Amazon Reviews 2023 competition package. Any future use requires a separate provenance and license review. |

If the upstream repository later adds explicit licenses, update this audit from
the primary records before changing a decision. Public availability alone is
not sufficient permission to copy an artifact.

## ShopLens adoption matrix

| Decision | TRACER/WoS concept | ShopLens treatment |
|---|---|---|
| Adopt | Wanted, unwanted, and optional preference semantics | Extend the existing slot and declined-attribute model only where tests show missing behavior. Implement independently and cite TRACER as the methodological influence. |
| Adopt | Catalog-aware aspect selection | Treat the current candidate-pool information-gain policy as the starting point. Preserve non-filtering constraints and compare it with any broader facet policy before replacing it. |
| Evaluate | Attributed synthetic dialogue fixtures | Generate fixtures only from the immutable ShopLens catalog and deterministic local rules. Mark them as ShopLens-generated and TRACER-inspired; do not derive them from WoS dialogue text. |
| Evaluate | Frequent-value clarification hints and facet hygiene | Test concise hints and noisy-facet suppression behind a new ablation config on the frozen dev split. Retain only changes with reproducible ranking or dialogue-quality evidence. |
| Defer | Upstream TRACER implementation and WoS dataset | Keep both outside the repository until explicit compatible terms are verified. Do not translate or mechanically reproduce upstream source code. |
| Defer | LLM verbalization and CQG/CPR fine-tuning | ShopLens must remain useful offline and deterministic. These experiments require a separate approved plan, dependencies, model provenance, and resource budget. |

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
space. The next implementation stage must first test the behavioral gap between
that policy and the paper's repeatedly fitted decision-tree planner; sharing an
intuition is not evidence that a second implementation improves ShopLens.

## Attribution for future derivatives

Any future module that materially adapts TRACER's published method must name
the paper and DOI in its module documentation. Generated fixture files must
record the generator version, catalog checksum, random seed, the canonical
paper URL, and a statement that the records are ShopLens-generated rather than
copied from WoS. README, data-provenance, release, and demo materials must link
back to this audit so the distinction remains visible.

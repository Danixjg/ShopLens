# ProductAgent source audit and adoption boundary

This record governs how ShopLens may use ideas from *ProductAgent*. It
separates attribution for the paper, which citation alone satisfies, from
permission to redistribute the paper or copy its artifacts, which its license
does not provide. No ProductAgent source code, AliMe KG record, or copy of the
paper is included in this repository.

## Canonical citation

Jingheng Ye, Yong Jiang, Xiaobin Wang, Yinghui Li, Yangning Li, Hai-Tao Zheng,
Pengjun Xie, and Fei Huang. 2024. *ProductAgent: Benchmarking Conversational
Product Search Agent with Asking Clarification Questions*. arXiv:2407.00942
[cs.IR].

- arXiv abstract page: https://arxiv.org/abs/2407.00942
- DOI: https://doi.org/10.48550/arXiv.2407.00942
- Version cited: v1, submitted 1 July 2024
- Venue status: the arXiv record states the work is under review. There is no
  journal reference or conference DOI, so the preprint is the canonical record.
- License: [arXiv non-exclusive distribution license 1.0](http://arxiv.org/licenses/nonexclusive-distrib/1.0/)

## License finding

This paper is licensed differently from the other two research sources
ShopLens cites, and the difference changes what is permitted.

The arXiv non-exclusive distribution license 1.0 records that the submitting
author grants "a perpetual, non-exclusive license to distribute this article"
to arXiv.org. It is an agreement between the authors and arXiv. It **does not
grant** readers, third parties, or this repository any right to redistribute
the paper, mirror it, or publish a derivative conversion of it.

By contrast, the Rao and Daume EVPI paper and the Wizard of Shopping paper are
both CC BY 4.0, which is why local conversions of those were assessed as
adaptable with credit. That reasoning does not transfer here. Verified against
the primary arXiv records on 2026-08-30.

Citing the paper, describing its published findings in our own words, and
independently implementing a published method remain available; none of those
requires a redistribution grant. Copying the paper text, its figures, or a
converted transcript into a tracked file does.

## Source audit

The decisions below were checked against the primary records on 2026-08-30.
They are conservative engineering controls, not legal advice.

| Artifact | Decision | Evidence and constraint |
|---|---|---|
| arXiv paper (v1) | Cite and paraphrase | The arXiv record identifies the authors, title, and DOI. Credit the authors and link the abstract page and the license. Paraphrase findings; do not quote at length. |
| Local conversion | Do not redistribute | A local Markdown conversion of the paper is a derivative of a work carrying no redistribution grant. Keep it Git-ignored as `docs/ProductAgent.md`, out of every commit, and out of the submission bundle. |
| Upstream ProductAgent code | Do not import | The arXiv record identifies no public implementation, and no license has been verified. Absence of a located repository is not permission. Independent implementation from the published method remains allowed subject to review. |
| AliMe KG | Do not import | The 1M-item corpus is not part of the Amazon Reviews 2023 competition package, and no distinct dataset license was verified. Do not download, commit, embed, or evaluate against it. |
| Reported metric values | Quote only here | The paper numbers were measured on AliMe KG with an LLM agent and simulator. They are evidence about ProductAgent, not about ShopLens, and must never appear on a ShopLens results surface. |

If a licensed version, a peer-reviewed record, or an explicitly licensed
implementation later appears, update this audit from the primary records
before changing a decision. Public availability alone is not permission.

## ShopLens adoption matrix

ProductAgent is an LLM agent over a 1M-item corpus, built from Text2SQL
statistics gathering, a three-stage loop, and a GPT-3.5 user simulator.
ShopLens is deterministic, offline, and bound to a frozen 50,000-row catalog
and a fixed response contract. Most of that machinery is therefore
inapplicable by construction. What transfers are the diagnosed failure modes
and the evaluation discipline.

| Decision | ProductAgent concept | ShopLens treatment |
|---|---|---|
| Already satisfied | Question redundancy is a measured failure, not a prompt bug | The paper reports question self-similarity climbing across turns despite an explicit no-duplicates instruction, because its questions are generated text constrained only by a prompt. ShopLens selects from a fixed three-attribute sequence plus a once-only open question, and every branch of every clarification mode filters on `state.asked_attributes`, which `src/agent.py` appends for each ask. Re-asking is therefore structurally impossible and a diversity guard would be inert. Checked 2026-08-30; recheck if the attribute set ever becomes generated rather than enumerated. |
| Adopt | Filter clarification aspects by field population | The paper cannot answer questions about legitimately empty fields. ShopLens had the same gap on a targeted turn, where the info-gain policy returned the first eligible facet in sequence order with no population check. Implemented as config `V`, which asks only facets a pooled candidate can answer, with an unconditional fallback. Unevaluated; its dev gate is frozen in `docs/testing/facet-population-gate.tdd.md`. |
| Adopt | Report rerank-only ablations with the ranking metric | Where a change reorders a frozen candidate set, hit rate is identical by construction and only the ranking metric carries information. The ShopLens phrase, popularity, and profile reranks are membership-preserving, so the same reasoning applies and should stay explicit in the evaluation notes. |
| Adopt | Retriever and query style are coupled | The paper shows one retriever moving from best to near-worst on query surface form alone. Treat any change of retrieval mode as requiring a same-cycle review of query construction. |
| Evaluate | Fusion and reranking can degrade a strong lexical baseline | ShopLens has independent evidence pointing the same way, since dense fusion alone regressed against the lexical baseline. Record it as a consistency check; it justifies no new change on its own. |
| Evaluate | Progressive constraint relaxation when a query returns nothing | ShopLens already scores constraints as penalties rather than filters and relaxes to category before a global fallback. Compare behavior against the published description before adding any mechanism. |
| Defer | Tool routing, and richer catalogs carrying price and review signals | Both fall outside the frozen catalog and the fixed contract. They need a separate approved plan. |
| Do not adopt | Text2SQL statistics gathering, the three-stage LLM loop, generated question prompts, and the LLM user simulator | Each requires a language model in the request path. They break offline determinism, the zero-cost disclosure, and the fixed evaluator contract. |

The paper ethics note flags misuse for privacy-data collection and excessive
persuasion. ShopLens performs no cross-session profiling, stores no user
identity, and reads an immutable catalog, so the concern is recorded here
rather than mitigated by new controls.

## Non-negotiable architecture guards

- Preserve offline determinism for every reportable configuration.
- Preserve the fixed public Agent contract and allowed `ask_attribute` values.
- Keep the immutable catalog checksum-verified.
- Keep the organizer evaluator a read-only evaluator.
- Tune new policy behavior on the deterministic dev-only split before any
  holdout run, and label exploratory evidence honestly.
- Introduce behavioral changes behind named ablation configurations so the
  current baseline remains reproducible.

These guards are identical to the ones in the
[Wizard of Shopping source audit](wizard-of-shopping-integration.md) by
intent. Both records constrain the same system, so they must not drift.

## Local research inputs

A contributor who obtains the paper may keep a personal conversion at
`docs/ProductAgent.md`. That path is Git-ignored alongside the other
third-party transcripts. It is optional: no test, build, or evaluation step
reads it, and a fresh clone is complete without it. Do not commit it, do not
quote it at length into a tracked file, and do not treat its section numbering
as a reference to ShopLens documentation, because it belongs to an external
document series.

## Attribution for future derivatives

Any future module that materially adapts a ProductAgent idea must name the
paper and `arXiv:2407.00942` in its module documentation. README, data
attribution, data provenance, research attribution, and the release checklist
must link back to this audit so the distinction between crediting the paper
and redistributing it remains visible.

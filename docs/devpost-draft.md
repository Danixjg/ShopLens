# ShopLens — Devpost draft

## Project description

ShopLens is a deterministic, offline-first conversational shopping agent for
the TechJam conversational-search challenge. It returns ranked products and a
structured clarification in the same response, accumulates disclosed
constraints, erases superseded preferences on intent override, and degrades to
valid catalog recommendations rather than emitting an empty or malformed turn.

The core insight came from measuring the organizer's simulator before tuning:
clarification does not delay scoring, silence stalls information disclosure,
and Intent Override sessions cannot convert before the override arrives. That
led to targeted questions, recoverable constraint penalties, and explicit
Buying-versus-Browsing routing rather than destructive filters.

## Architecture and innovation

- Buying uses a lexical-weighted union with the hybrid pool for precision
  without sacrificing recoverable recall.
- Browsing and Intent Override use in-memory BM25 plus local dense retrieval.
- Active multi-value slots form the retrieval query; overrides retire only
  superseded soft evidence while preserving independent disclosures.
- Hard constraints apply bounded per-attribute evidence, never filters.
- Candidate-pool overload selects the facet with the highest normalized
  multiclass information gain, excluding declined attributes.
- Experimental config U instead ranks eligible attributes by deterministic
  expected Top-K utility over possible catalog-facet answers. This is an
  independent adaptation of Rao and Daumé III's EVPI framing, not a port of
  their neural model; the canonical citation is in
  `docs/research-attribution.md`.
- A local contiguous-phrase rarity bonus reranks only the frozen Top 10, so it
  can improve MRR without changing Hit Rate membership.

## Tools, libraries, APIs, and cost

- Python 3.10+, SQLite FTS5, NumPy, PyTorch, and Sentence Transformers.
- Vendored `sentence-transformers/all-MiniLM-L6-v2` model, loaded by local path.
- No hosted model API, API key, external vector database, or paid service.
- Prompt tokens: 0. Completion tokens: 0. Model/API cost: $0.
- Development tools: Git, pytest, and coordinated OpenAI Codex terminal
  sessions for implementation and independent review.

## Data and assets

The frozen 50,000-product catalog and 200 public sessions are derived from
Amazon Reviews 2023 Clothing, Shoes and Jewelry data. Catalog bytes are checked
against the organizer release digest, and dense caches are keyed by catalog
and model provenance. Full attribution is in `DATA_ATTRIBUTION.md`.

## Evaluation

Clean commit `be4017aa` remains the canonical reportable baseline: F scored
`0.712658` on the 120-session dev split and `0.719476` on the 80-session
holdout. The accuracy candidate was then frozen after dev-only tuning and
opened on holdout once. In canonical true-hybrid evaluation, config P scored
`0.819939` on dev (HR@10 `0.941667`, MRR `0.639239`, MTTC `3.133333`) and
`0.843958` on holdout (HR@10 `0.975`, MRR `0.644861`, MTTC `2.85`). The
120/80 weighted public estimate is `0.829546`.

The phrase stage alone improved 24 dev sessions and regressed none while
preserving HR/MTTC. A paired, scenario-stratified 10,000-resample bootstrap
(seed 2026) put its TechnicalScore gain at `0.019567`, with a 95% interval of
`[0.010258, 0.029980]`.

The next candidate, Q, adds a bounded log-scaled rating-count prior
inside P's already-frozen Top-10. It preserves P's relevance score and adds a
maximum-weighted `0.15 * popularity / 61` bonus, without filtering products or
changing catalog membership. Q scored `0.862083` on dev (HR@10 `0.941667`, MRR
`0.779722`, MTTC `3.133333`): 50 target ranks improved, none regressed, and all
four scenario MRRs increased. A later reportable holdout row scored an
exploratory `0.880321` (HR@10 `0.975`, MRR `0.766071`, MTTC `2.85`). The idea
followed an aggregate review of target rating counts across all public
sessions, so that holdout result is exploratory rather than statistically
untouched. Note that a clean *run* and a clean *holdout* are different claims:
every row cited here came from a clean reportable run, while only some rows
come from an untouched split. A paired, scenario-stratified
10,000-resample bootstrap (seed 2026) estimated Q's dev TechnicalScore gain
over P at `0.042145`, with a 95% interval of `[0.030926, 0.054362]`.

The P rows are clean canonical evidence in `results.jsonl`. Q's clean
reportable dev and exploratory holdout rows are recorded at commits `1b55d92`
and `5d5a486`, respectively. These runs used the pinned CPU model, with zero
agent or evaluator response exceptions and $0 API cost. Boundary HR@10 moved
from the historical F `0.166667/0.25` to P `1.0/0.75` on dev/holdout; Buying,
Browsing, and Intent Override also improved or held in aggregate. Configs G and
H are not claimed because no plan-specified offline cross-encoder or LLM
provider exists.

Three further candidates were measured after Q. `R` (symmetric intent routing)
and `S` (bounded profile affinity) each cleared the same gate on both splits
and hold clean, untouched holdout rows of `0.846396` and `0.846896`. `T`
combines `R`, `S`, and `Q` under a composition gate frozen before the run,
which required it to beat not merely `P` but the best single component. It
scored `0.866774` on dev and an exploratory `0.891630` on holdout, inheriting
Q's label because it carries Q's prior.

**`T` is the submission configuration.** Its downside is bounded: HR@10 is
identical across every candidate at `0.941667` on dev and `0.975` on holdout,
so the rerankers permute order strictly inside the frozen Top-10 and cannot
cost recall. Its advantage over `Q` also replicates across both splits and
localises to Intent Override, which is `R`'s contribution and holds a clean
holdout of its own. If an untouched holdout is required instead, `S` is the
best clean candidate; we report both rather than only the stronger one.

The research-derived U ablation replaced only P's information-gain question
policy with deterministic expected-question-value scoring. On a clean dev run
at commit `87834f4` it preserved HR@10 at `0.941667` and increased MRR to
`0.641323`, but MTTC worsened to `3.175000`; TechnicalScore was `0.819730`, just
below P's pre-registered `0.819939` threshold. We therefore rejected U and did
not open holdout. This negative result is retained because it separates an
appealing research framing from a measured competition improvement.

## Limitations and future work

- Boundary remains the smallest and noisiest scenario bucket (six dev and four
  holdout sessions), so its rank metrics are directional rather than stable.
- The deterministic parser is tailored to controlled simulator language, not
  arbitrary noisy commerce conversations.
- Sparse catalog metadata makes some constraints, especially color, unreliable.
- The expected-question-value experiment uses catalog facets as a target-free
  proxy for possible answers; it cannot predict every free-form shopper reply.
- Q favors established products over niche or newly listed products, and the
  public target construction may amplify that popularity bias.
- The optional cross-encoder and LLM-ranking experiments are not claimed until
  a specific offline model/provider, cost, and measured benefit exist.
- Aggregate profile fields contain weak signal and never override explicit
  current-session preferences.

Given more time, we would validate paraphrased language, calibrate scoring on a
larger labeled split, and investigate category-aware diversity for Boundary
without using private-target assumptions.

## Research credit

ShopLens independently adapted the EVPI framing in the following work; it did
not reproduce or port the paper's neural model, source code, training data,
annotations, or weights:

> Sudha Rao and Hal Daumé III. 2018. *Learning to Ask Good Questions: Ranking
> Clarification Questions using Neural Expected Value of Perfect Information.*
> Proceedings of the 56th Annual Meeting of the Association for Computational
> Linguistics (Volume 1: Long Papers), ACL 2018, pages 2737–2746.

DOI: [10.18653/v1/P18-1255](https://doi.org/10.18653/v1/P18-1255). Canonical
publication: [ACL Anthology](https://aclanthology.org/P18-1255/). The paper is
licensed under Creative Commons Attribution 4.0 International (CC BY 4.0). The
full adoption boundary is in [research-attribution.md](research-attribution.md).

## Team contributions

Repository history is the source of truth. Replace this section with every
participant's exact name and attributable contribution before submission; do
not infer missing identities.

## Links

- Public repository: [add final public GitHub URL]
- Public YouTube demo: [add final public video URL]

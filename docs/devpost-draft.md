# ShopLens — Devpost draft

## Project description

ShopLens is a deterministic, offline-first conversational shopping agent for
the TechJam 2026 conversational-search challenge. The evaluator now defaults to
configuration `O+`; its parent, configuration `O`, is the latest build with
reportable evidence and recorded a TechnicalScore of `0.908416` on our
120-session development split and `0.898795` on the 80-session exploratory
holdout. It runs on CPU, uses no hosted model or paid API, and reports zero
prompt and completion tokens.

The organizer calls `Agent.reset(session_id, user_profile)` once and
`Agent.respond(session_id, user_message, turn, top_k)` on each turn. ShopLens
returns up to ten ranked catalog products and a structured clarification in the
same response. It remembers disclosed preferences, handles genuine intent
overrides, avoids repeating products already scored in the session, and always
returns a contract-valid fallback if the normal path fails.

Each response contains customer-facing `message` text, one allowed
`ask_attribute` or `null`, ordered `recommendations`, and zeroed `usage`. A
session stops on the first valid hit or after turn 10.

## Why we built it this way

The evaluation protocol rewards finding the hidden product early and placing it
high in the returned list. Clarification does not delay the current turn's
recommendations, so staying silent wastes the chance to collect useful evidence
for the next turn. Hard filtering was also too brittle for sparse catalog data.
Those observations led to same-turn clarification, recoverable penalties, and
ranking stages that preserve candidate membership unless a mechanism has a
specific reason to change it.

## How it works

1. **Verify local assets.** The loader reads the immutable 50,000-product JSONL
   catalog and checks the official file against its pinned SHA-256 digest.
2. **Parse and remember.** A deterministic parser extracts category, hard
   constraints, soft preferences, declines, and intent changes into session
   state. New disclosures accumulate. A real override retires only the earliest
   superseded soft preference while preserving unrelated constraints.
3. **Build the live query.** Only active slots are used. Previously returned
   ASINs are carried as session exclusions; an intent override clears that list
   because earlier products were offered against the old intent.
4. **Retrieve locally.** Weighted SQLite FTS5 BM25 and a vendored
   `sentence-transformers/all-MiniLM-L6-v2` encoder produce candidate lists that
   are combined with reciprocal-rank fusion. Buying turns use a lexical-weighted
   union for precision; other turns use balanced hybrid fusion.
5. **Score without destructive filters.** Per-attribute constraint evidence and
   intent-aware weights adjust candidate scores. Hard constraints are bounded
   penalties, never filters. If a detailed query is empty, the agent relaxes to
   its category before using a global fallback.
6. **Rank the response.** Configuration `O+` freezes Top-K membership, orders
   candidates by which active disclosures they satisfy, then applies a small,
   log-bounded rating-count prior inside that same set and uses fitted scoring
   magnitudes. The popularity signal cannot add or remove products.
7. **Ask the next useful question.** The policy uses normalized information gain
   over live candidate facets, skips attributes the shopper declined, and asks a
   targeted or open clarification alongside the recommendations.
8. **Fail safely.** Duplicate or out-of-order turns receive the last valid
   recommendations. Unexpected exceptions use the last non-empty result or a
   deterministic catalog fallback and still return the required response shape.

The no-repeat rule has a safety valve: if withholding previously shown products
would empty the candidate pool, ShopLens keeps the unfiltered pool instead of
returning nothing.

## Submission configuration

An unset `SHOPLENS_CONFIG` selects `O+`; an unknown value falls back to the
standard-library baseline `A`. The accuracy-critical `O+` path enables hybrid
retrieval, session memory, bounded constraint scoring, dynamic intent weights,
information-gain clarification, no-repeat recommendations, disclosure-order
reranking, the bounded popularity prior, and O's eight fitted scoring
magnitudes.

Dense retrieval is optional at runtime. If NumPy, Sentence Transformers, or the
verified local model cannot load, the retriever degrades to deterministic BM25
without making a network request or failing the turn. The submission does not
enable an LLM ranker or cross-encoder.

## Tools, libraries, APIs, and cost

- Python 3.10 or newer; reportable evidence used CPython 3.12.13.
- SQLite FTS5 for weighted lexical retrieval.
- NumPy, PyTorch, Transformers, Tokenizers, and Sentence Transformers for the
  optional local dense path.
- Vendored `all-MiniLM-L6-v2` weights, loaded by local path on CPU with
  `local_files_only=True`.
- `pytest` for unit, integration, policy, retrieval, evidence, and documentation
  checks.
- No API key, hosted model, external vector database, or paid service.
- Prompt tokens: `0`. Completion tokens: `0`. Estimated model/API cost: `$0`.

## Data and privacy

The frozen catalog contains 50,000 Clothing, Shoes and Jewelry products, and the
public development set contains 200 labeled sessions: 80 Buying, 80 Browsing,
30 Intent Override, and 10 Boundary. The organizer retains 800 private sessions
for final scoring. Only catalog-valid `parent_asin` identifiers are scored.

The data derives from Amazon Reviews 2023 by McAuley Lab, UCSD. Direct user
identifiers, timestamps, free-text reviews, raw purchase histories, hidden
intent cards, and simulator internals are not included in the participant data.
The agent sees only safe aggregate profile fields and current-session messages;
it performs no cross-session profiling or catalog mutation. Full provenance and
redistribution terms are recorded in
[DATA_ATTRIBUTION.md](../DATA_ATTRIBUTION.md).

## Evaluation

The evaluator reports HitRate@10, mean reciprocal rank (MRR), and mean turns to
conversion (MTTC). The repository uses this formula:

`TechnicalScore = 0.50 × HR@10 + 0.30 × MRR + 0.20 × efficiency`

Lower MTTC improves efficiency. TechnicalScore is evidence for technical
execution, not the competition's entire judging decision.

We keep the candidate history short here and list only the builds that materially
changed accuracy:

| Config | Accuracy-relevant change | Dev TechnicalScore | Holdout TechnicalScore |
|---|---|---:|---:|
| `P` | Hybrid retrieval, state, constraints, dynamic routing, and frozen-set phrase reranking | `0.819939` | `0.843958` |
| `Q` | `P` plus a bounded rating-count prior | `0.862083` | `0.880321` (exploratory) |
| `T` | Previous submission combining `Q` with symmetric intent routing and profile affinity | `0.866774` | `0.891630` (exploratory) |
| **`O`** | **No-repeat recommendations plus disclosure-order ranking on the `Q` branch** | **`0.908416`** | **`0.898795` (exploratory)** |
| `O+` | Evaluator default: `O` with eight fitted scoring magnitudes | `0.9189` (diagnostic) | `0.9097` (diagnostic) |

The one-flag `N` diagnostic showed that withholding already scored products
accounted for most of `O`'s development gain; `N` has no reportable row, so its
diagnostic score is not presented as formal evidence. Disclosure-order ranking
then improved ordering without changing the frozen Top-K membership.

Config `K` corrects semicolon-delimited constraint segmentation but did not
change accuracy. It reduced over-splits from 3 to 0 on both public splits, with
no under-splits there or across 196,680 synthetic disclosures. Its clean dev run
at `6c8135f` tied `O` exactly—HR@10 `0.983333`, MRR `0.844722`, MTTC `2.833333`,
and TechnicalScore `0.908416`—so the flag remains off while its property test is
retained.

Configuration `O` produced the following reportable outcomes; `O+` has no
reportable row yet, so its figures above remain diagnostic:

| Split | Sessions | HR@10 | MRR | MTTC | TechnicalScore |
|---|---:|---:|---:|---:|---:|
| Dev | 120 | `0.983333` | `0.844722` | `2.833333` | `0.908416` |
| Holdout | 80 | `0.987500` | `0.795982` | `2.687500` | `0.898795` (exploratory) |

Both rows came from clean, reportable CPU runs with an immutable input snapshot,
the pinned model and dependency lock, true hybrid retrieval, and zero agent
exceptions, evaluator exceptions, or invalid responses. The dev row is recorded
at commit `fedd07e8`; the holdout row is recorded at `9e5504ca`.

The 120/80 split is a project-imposed control over the 200 public development
sessions, not an organizer-defined hidden test. `Q`, `T`, and `O` holdout results
are labeled exploratory because the popularity hypothesis used aggregate public
target evidence, and `O` was selected through development-split flag isolation.
Against `T`, `O` improved HR@10 and MTTC on both splits, while its MRR improvement
did not transfer to holdout. We therefore present the mechanism and each metric,
not only the composite score.

## Runtime and reproducibility

The reportable `O` runs used Linux x86-64 under WSL2, SQLite 3.46.1, CPU-only
inference, and the hash-pinned `requirements-dense.lock.txt` environment with
zero lock mismatches.

| Measurement | Dev | Holdout |
|---|---:|---:|
| Turn latency p50 / p95 | `93.6 / 145.8 ms` | `107.9 / 168.1 ms` |
| Turn latency mean / max | `98.4 / 175.3 ms` | `113.6 / 311.8 ms` |
| Peak RSS | `1.95 GB` | `1.98 GB` |
| One-time reportable initialization | `1307.1 s` | `1274.7 s` |

The long reportable initialization deliberately rebuilds all 50,000 catalog
embeddings in process so the evidence can bind their provenance. Normal use
reuses a fingerprinted local embedding cache and starts in seconds. Setup,
evaluation commands, hashes, and evidence rules are documented in the
[repository README](../README.md).

## Limitations

- The parser targets the organizer's controlled language and common commerce
  terms; it is not a general natural-language understanding model.
- Catalog metadata is sparse and inconsistent. Color is missing from more than
  half of products, so color evidence is weaker than better-populated fields.
- The rating-count prior can favor established products over niche or newly
  listed products, and public target construction may amplify that bias.
- No-repeat recommendations are recall-safe under this evaluator because every
  returned ASIN is scored and a hit ends the session. A continued real-world
  conversation would not prove that every earlier recommendation was wrong.
- Boundary is the smallest scenario bucket, so its per-scenario metrics are
  directional rather than stable.
- The reportable dense path has a large CPU cold start and roughly 2 GB peak
  memory, although cached normal use is much faster.
- ShopLens has no image input, external vector database, full-model training,
  hosted LLM dependency, or real transaction support.

## Research credit

The retained `O` policy uses information gain, not the experimental EVPI mode.
Configuration `U` independently adapted the EVPI framing as a deterministic,
target-free expected Top-K utility calculation. Its clean dev run at commit
`87834f4` held HR@10 at `0.941667` and raised MRR to `0.641323`, but MTTC moved
to `3.175000`; TechnicalScore was `0.819730`, below the pre-registered `0.819939`
gate. We rejected `U` without opening holdout.

> Sudha Rao and Hal Daumé III. 2018. *Learning to Ask Good Questions: Ranking
> Clarification Questions using Neural Expected Value of Perfect Information.*
> Proceedings of ACL 2018, pages 2737–2746.

DOI: [10.18653/v1/P18-1255](https://doi.org/10.18653/v1/P18-1255). Canonical
publication: [ACL Anthology](https://aclanthology.org/P18-1255/). The paper is
licensed under Creative Commons Attribution 4.0 International (CC BY 4.0).
ShopLens did not reproduce or port its neural model, code, training data,
annotations, or weights. The complete adoption boundary is in
[research-attribution.md](research-attribution.md).

The preference-state and clarification work was also informed by Li et al.'s
TRACER method in *Wizard of Shopping* (ACL 2025), while clarification-quality
guards and rerank reporting were informed by Ye et al.'s *ProductAgent*
(arXiv:2407.00942). These ideas were implemented independently. The repository
contains no Wizard of Shopping records, ProductAgent code, or AliMe KG data; see
the [Wizard of Shopping audit](wizard-of-shopping-integration.md) and
[ProductAgent audit](productagent-integration.md).

## Team contributions

Git history is the source of truth for the repository identities below. Replace
handles with the final Devpost roster names before submission if required.

| Repository identity | Contribution visible in history |
|---|---|
| Danixjg | Initial deterministic clarification, stateful BM25 policy, override handling, integration, and repository maintenance |
| Kivye / kivye | Hybrid retrieval, evidence hardening, state and clarification improvements, phrase/popularity ranking, research integration, and review |
| MaxLZE | Reproducibility gates, retrieval/ranking ablations, source audits, documentation integrity, and promotion of configuration `O` |
| suwi | No-repeat configuration `N` and disclosure-order configuration `O` |
| pranavpillaiNUS | Configuration `O` integration, ProductAgent audit integration, and turn-by-turn error analysis |
| thaqifrafe | clarification-timing diagnostic tooling, and configurations `K`, `L`, and `AA` (budget-extended, covered-attribute, and embedding-based near-miss clarification; documented rejections) |


The original participant kit, evaluator contract, public dataset, and competition
specification were published by the TechJam2026 organizer repository identity.

## Links

- Public repository: [github.com/Danixjg/TrippyShoppy](https://github.com/Danixjg/TrippyShoppy)
- Public YouTube demo: [add final public video URL]

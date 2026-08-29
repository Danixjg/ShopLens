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
- Active session slots form the retrieval query; overrides retire the original
  preference while preserving useful later disclosures.
- Hard constraints apply penalties and bonuses but never delete products.
- Candidate-pool overload changes the guidance message while recommendations
  still ship on the same turn.
- Clarification follows the measured `feature -> material -> color -> other`
  order, uses the wildcard once, and then stops probing.

## Tools, libraries, APIs, and cost

- Python 3.10+, SQLite FTS5, NumPy, PyTorch, and Sentence Transformers.
- Vendored `sentence-transformers/all-MiniLM-L6-v2` model, loaded by local path.
- No hosted model API, API key, external vector database, or paid service.
- Prompt tokens: 0. Completion tokens: 0. Model/API cost: $0.
- Development tools: [add the team's exact editors and collaboration tools].

## Data and assets

The frozen 50,000-product catalog and 200 public sessions are derived from
Amazon Reviews 2023 Clothing, Shoes and Jewelry data. Catalog bytes are checked
against the organizer release digest, and dense caches are keyed by catalog
and model provenance. Full attribution is in `DATA_ATTRIBUTION.md`.

## Evaluation

Insert only clean-tree records from `results.jsonl` here. Report aggregate and
per-scenario HR@10, MRR, MTTC, Efficiency, elapsed time, peak RSS, cache state,
dependency versions, effective retriever, and Git SHA. Include the published
weak starter, A, B, C, D, E, F, and diagnostic Z where reportable.

## Limitations and future work

- Boundary sessions remain difficult because the shopper may decline the only
  asked attribute and reveal no new target evidence.
- The deterministic parser is tailored to controlled simulator language, not
  arbitrary noisy commerce conversations.
- Sparse catalog metadata makes some constraints, especially color, unreliable.
- The optional cross-encoder and LLM-ranking experiments are not claimed until
  a specific offline model/provider, cost, and measured benefit exist.
- Aggregate profile fields contain weak signal and never override explicit
  current-session preferences.

Given more time, we would validate paraphrased language, calibrate scoring on a
larger labeled split, and investigate category-aware diversity for Boundary
without using private-target assumptions.

## Team contributions

Repository history is the source of truth. Replace this section with every
participant's exact name and attributable contribution before submission; do
not infer missing identities.

## Links

- Public repository: [add final public GitHub URL]
- Public YouTube demo: [add final public video URL]

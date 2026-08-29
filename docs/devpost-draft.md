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
- Development tools: Git, pytest, and coordinated OpenAI Codex terminal
  sessions for implementation and independent review.

## Data and assets

The frozen 50,000-product catalog and 200 public sessions are derived from
Amazon Reviews 2023 Clothing, Shoes and Jewelry data. Catalog bytes are checked
against the organizer release digest, and dense caches are keyed by catalog
and model provenance. Full attribution is in `DATA_ATTRIBUTION.md`.

## Evaluation

Clean commit `be4017aa` produced the reportable A–F matrix in `results.jsonl`.
The retained F route scored `0.712658` on the 120-session stratified dev split
(HR@10 `0.841667`, MRR `0.502748`, MTTC `3.95`) and `0.719476` on the
80-session holdout (HR@10 `0.85`, MRR `0.515754`, MTTC `4.0125`). The runner
confirmed effective hybrid retrieval, a cache hit, zero agent exceptions, zero
tokens, and $0 API cost. Its dev/holdout scenario HR@10 values were Boundary
`0.166667/0.25`, Browsing `0.895833/0.875`, Buying `0.9375/0.875`, and Intent
Override `0.666667/0.916667`.

For comparison, C scored `0.689519/0.707318` on dev/holdout, and the
dependency-free A baseline scored `0.616107/0.629293`. Disabling session memory
in D regressed both splits. E tied C exactly because the frozen candidate seam
lacks the attributes required for disagreement-based information gain. The
200-session diagnostic Z run without clarification scored `0.192606` with
MTTC `8.895`, quantifying the simulator's disclosure stall. G and H are not
claimed because no plan-specified offline cross-encoder or LLM provider exists.

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

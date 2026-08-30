# ShopLens

ShopLens is a deterministic, offline-first conversational shopping agent for
the TechJam 2026 conversational-search challenge. It asks a clarification on
the same turn that it returns up to ten ranked products, remembers disclosed
constraints, and removes superseded preferences when the shopper changes
their mind.

The planned extension of its preference and clarification policy is informed
by Li et al.'s TRACER method from *Wizard of Shopping* (ACL 2025). ShopLens is
an independent implementation and currently contains neither upstream TRACER
code nor Wizard of Shopping dataset records. The
[source audit and adoption boundary](docs/wizard-of-shopping-integration.md)
records the full citation, license evidence, and adopt/evaluate/defer decisions.

The system implements the organizer's `Agent.reset(...)` and
`Agent.respond(...)` interface. It does not modify the catalog or evaluator,
call a paid API, or require network access during baseline scoring.

## Architecture

```text
customer message
      |
deterministic parser ----> multi-value slots / override erasure
                                  |
                         retrieval query seam
                                  |
             BM25 -------- optional dense retrieval
                 \          /
             reciprocal-rank fusion
                       |
     bounded per-attribute constraint scoring
                       |
             freeze Top-K membership
                       |
       optional phrase-rarity reranking
                       |
 information-gain clarification + guarded response
```

The implementation is split by responsibility:

- `src/contracts/`: shared response, state, parsing, retrieval, and run config contracts.
- `src/catalog/`: immutable JSONL loading, normalization, and checksum verification.
- `src/parsing/` and `src/state/`: controlled-language parsing, slot transitions, and query construction.
- `src/retrieval/`: weighted FTS5 BM25, optional local dense retrieval, and reciprocal-rank fusion.
- `src/scoring/`: bounded non-filtering constraint evidence, dynamic routes,
  and membership-preserving phrase-rarity reranking.
- `src/policy/`: candidate-facet information gain with targeted fallback and
  persistent per-attribute decline handling.
- `src/agent.py`: integration and last-non-empty/global failure recovery.
- `agent.py` and `starter/agent.py`: thin shims for submission and the organizer's local evaluator.

Hard constraints are penalties, never filters. A parsing mistake can lower a
candidate but cannot delete the target from the retrieval pool. Query text is
built from active slots only. Same-attribute disclosures accumulate, while a
genuine override such as “black, then actually brown” retires superseded soft
evidence without erasing unrelated constraints.

## Requirements and setup

- Python 3.10 or newer (tested here with Python 3.12).
- SQLite compiled with FTS5, as in standard CPython distributions.
- No Python packages are required for config A, the deterministic BM25 baseline.
- Hybrid/dense configs require `numpy`, `sentence-transformers`, and the
  locally vendored `models/all-MiniLM-L6-v2/` directory.

Download the release assets `catalog.jsonl.gz` and `SHA256SUMS`, verify the
compressed asset, and place the decompressed file at `data/catalog.jsonl`:

```bash
sha256sum --check SHA256SUMS
gzip -dk catalog.jsonl.gz
mv catalog.jsonl data/catalog.jsonl
python3 -m pip install -r requirements-dev.txt
python3 -m pytest -q
```

Install the portable optional dependencies before running hybrid configs:

```bash
python3 -m pip install -r requirements-dense.txt
```

Reportable dense evidence uses the fully resolved reference environment on
CPython 3.12, Linux x86-64:

```bash
python3 -m pip install -r requirements-dense.lock.txt
```

`pip` is the canonical path and requires no tooling beyond the standard
library. If [uv](https://github.com/astral-sh/uv) is available it installs the
same lock substantially faster, and the resulting environment is equivalent:

```bash
uv venv --python 3.12 .venv-dense
uv pip install --python .venv-dense/bin/python -r requirements-dense.lock.txt
```

Both routes resolve to the identical package set, so `requirements_lock_sha256`
and `requirements_lock_mismatches` in reportable evidence are unchanged. uv is
an optional convenience; it is never required to reproduce results.

The default `data/catalog.jsonl` path automatically verifies the pinned
decompressed release digest. For a custom catalog path, request the same
load-time protection by setting its digest:

```bash
export SHOPLENS_CATALOG_SHA256="$(sha256sum data/catalog.jsonl | cut -d' ' -f1)"
```

The default and repository-absolute catalog paths always enforce the official
digest. For fixture diagnostics, pass a custom path and its explicit checksum;
there is no verification bypass for the official path.

The repository deliberately loads dense and reranker models by local path,
never by model name. The embedding model is pinned and documented in
`models/README.md`. Dense catalog embeddings are computed locally and may be
persisted as the ignored file `data/catalog.embeddings.npz`. Normal agent use
can reuse a validated cache. A reportable run instead rebuilds vectors from
the pinned model and an immutable catalog snapshot in-process. If local model
files or optional packages are unavailable, normal hybrid use falls back to
deterministic BM25 without a network request; the evidence runner marks that
capability mismatch non-reportable.

## Reproduce evaluation

Run the reproducible standard-library config A baseline against all 200 public
sessions. A is the default when `SHOPLENS_CONFIG` is unset:

```bash
python3 -m evaluator.local_evaluator
```

After installing the dense dependencies, run the retained config P explicitly,
or use config Q for the dev-selected bounded popularity experiment:

```bash
SHOPLENS_CONFIG=P python3 -m evaluator.local_evaluator
SHOPLENS_CONFIG=Q python3 -m evaluator.local_evaluator
```

Run the stratified 120-session dev or 80-session holdout split and append the
config, scores, split, and Git SHA to `results.jsonl`:

```bash
python3 -m src.eval.runner --config P --split dev
python3 -m src.eval.runner --config P --split holdout
```

The canonical runner requires a clean tree and writes only reportable evidence
to `results.jsonl`. Dirty diagnostics must use a path outside the repository:

```bash
python3 -m src.eval.runner --config P --split dev \
  --allow-dirty --results-log /tmp/shoplens-p-dev.jsonl
```

The public organizer starter (which does not ask clarification questions)
reports HR@10 `0.125`, MRR `0.068034`, MTTC `9.81`, and TechnicalScore
`0.10671`. Config A is an honest BM25 baseline with clarification enabled and
is therefore not directly comparable.

Reportable results are generated by `src.eval.runner` only from an identifiable
clean implementation whose requested local capabilities actually loaded and
whose guarded response fallback handled no unexpected exceptions. The runner
records those capability checks and fallback count alongside config flags,
locked dependencies, platform, pinned model and vector digests, catalog and
dataset digests, cache provenance, latency, memory, and four Git-state gates.
Dev and holdout use the deterministic stratified 120/80 split.

### Historical reportable baseline

The following rows come from clean commit `be4017aa` in `results.jsonl`.
All A–F rows report zero guarded exceptions; B–F confirm that hybrid retrieval
loaded rather than using the BM25 fallback. Higher HR@10, MRR, and Score are
better; lower MTTC is better.

| Config | Dev HR@10 | Dev MRR | Dev MTTC | Dev Score | Holdout HR@10 | Holdout MRR | Holdout MTTC | Holdout Score |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A | 0.7167 | 0.4687 | 5.1417 | 0.6161 | 0.7500 | 0.4435 | 4.9375 | 0.6293 |
| B | 0.6417 | 0.3185 | 5.6167 | 0.5241 | 0.6500 | 0.3137 | 5.6375 | 0.5264 |
| C | 0.8250 | 0.4567 | 4.0000 | 0.6895 | 0.8375 | 0.5027 | 4.1125 | 0.7073 |
| D | 0.7250 | 0.4296 | 4.7583 | 0.6162 | 0.7500 | 0.4723 | 4.9625 | 0.6374 |
| E | 0.8250 | 0.4567 | 4.0000 | 0.6895 | 0.8375 | 0.5027 | 4.1125 | 0.7073 |
| **F** | **0.8417** | **0.5027** | **3.9500** | **0.7127** | **0.8500** | **0.5158** | **4.0125** | **0.7195** |

F was the retained dense configuration at that commit. D shows that removing
session memory regressed both; E's historical tie with C predates the live
facet-based information-gain policy. B also shows that dense fusion alone is
not sufficient. Config Z, the diagnostic
no-clarification run over all 200 sessions, scores only `0.192606` with MTTC
`8.895`, demonstrating the cost of stalled disclosure.

F's per-scenario evidence is reported explicitly because aggregate gains can
hide override failures:

| Scenario | Dev HR@10 | Dev MRR | Dev MTTC | Holdout HR@10 | Holdout MRR | Holdout MTTC |
|---|---:|---:|---:|---:|---:|---:|
| Boundary | 0.1667 | 0.0417 | 9.6667 | 0.2500 | 0.0250 | 8.5000 |
| Browsing | 0.8958 | 0.5141 | 3.4792 | 0.8750 | 0.6332 | 3.9375 |
| Buying | 0.9375 | 0.5937 | 2.8125 | 0.8750 | 0.4288 | 3.2500 |
| Intent Override | 0.6667 | 0.3836 | 6.3333 | 0.9167 | 0.5980 | 4.7500 |

### Accuracy candidate validation

Config P was frozen after dev-only tuning, opened on holdout once, and recorded
as canonical reportable evidence in `results.jsonl`; Q remains dev-only. Q's row
is diagnostic because its implementation is still uncommitted. Both used true
hybrid retrieval and the pinned CPU model with zero agent/evaluator response
exceptions. After the Q implementation commit, rerun the clean command before
retaining Q or replacing P's evidence.

| Config | Dev HR@10 | Dev MRR | Dev MTTC | Dev Score | Holdout HR@10 | Holdout MRR | Holdout MTTC | Holdout Score |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| F, new state/policy | 0.9417 | 0.5740 | 3.1333 | 0.8004 | — | — | — | — |
| **P, phrase λ=0.15** | **0.9417** | **0.6392** | **3.1333** | **0.8199** | **0.9750** | **0.6449** | **2.8500** | **0.8440** |
| Q, popularity λ=0.15 | 0.9417 | 0.7797 | 3.1333 | 0.8621 | — | — | — | — |

Q was selected and evaluated on dev only; its public holdout metric remains
unopened for this implementation. Against P it improved 50 target ranks,
regressed none, and left 70 unchanged. HR@10 and MTTC were identical in every
scenario. Dev MRR rose from P to Q for Boundary (`0.7417` → `0.8889`),
Browsing (`0.6708` → `0.7760`), Buying (`0.6042` → `0.7948`), and Intent
Override (`0.6144` → `0.7130`). These are dirty diagnostic results until Q is
committed and reproduced by the clean evidence runner. Because the popularity
hypothesis followed an aggregate review of target rating counts across all 200
public sessions, Q's eventual holdout result must be labeled exploratory, not
statistically untouched. A scenario-stratified paired bootstrap (10,000
resamples, seed 2026) estimates Q's dev TechnicalScore gain over P at
`0.042145`, with a 95% interval of `[0.030926, 0.054362]`.

Weighting the frozen dev and holdout aggregates by their 120/80 sample counts
gives an all-public estimate of HR@10 `0.955`, MRR `0.641488`, MTTC `3.02`,
and TechnicalScore `0.829546`, without rerunning or retuning on holdout.

| Scenario | Dev HR@10 | Dev MRR | Dev MTTC | Holdout HR@10 | Holdout MRR | Holdout MTTC |
|---|---:|---:|---:|---:|---:|---:|
| Boundary | 1.0000 | 0.7417 | 4.1667 | 0.7500 | 0.1708 | 4.5000 |
| Browsing | 0.9792 | 0.6708 | 2.6458 | 1.0000 | 0.8001 | 2.6875 |
| Buying | 0.9167 | 0.6042 | 2.8958 | 1.0000 | 0.5501 | 2.1875 |
| Intent Override | 0.8889 | 0.6144 | 4.7222 | 0.9167 | 0.6417 | 4.5000 |

On dev, paired P-versus-F evaluation improved the target rank in 24 sessions
and regressed none, with identical HR/MTTC. A scenario-stratified paired
bootstrap (10,000 resamples, seed 2026) estimates the score gain at `0.019567`
with a 95% interval of `[0.010258, 0.029980]`.
Separate warm dev processes measured peak RSS of `1,527,340` KB for F and
`1,527,920` KB for P, a `580` KB increase.

## Ablation configurations

Select an ablation with `SHOPLENS_CONFIG`. An unset or unknown value safely
uses baseline A. Hybrid configurations require the optional dense install.

| Config | Change from the preceding build |
|---|---|
| A | BM25 plus clarification |
| B | Hybrid retrieval |
| C | Constraint scoring and session memory |
| D | C with session memory disabled |
| E | Candidate-facet information-gain clarification |
| F | Dynamic buying/browsing weights |
| G | Local cross-encoder reranker |
| H | Optional LLM rank experiment; offline path remains available |
| P | F plus membership-preserving phrase-rarity reranking |
| Q | P plus a bounded rating-count prior inside the frozen Top-10 |
| Z | Clarification off, diagnostic only |

Q uses only the immutable organizer catalog. For each member of P's frozen
Top-10 it log-scales `rating_number` against the catalog maximum and adds
`0.15 * popularity / 61` to the existing P score. It then reorders those same
identifiers deterministically. The prior cannot change HitRate@10 or MTTC; it
is an ordering aid, never a retrieval filter or a replacement for
disclosed-constraint evidence.

The evaluator reports HR@10, MRR, MTTC, efficiency, the recommended composite,
and the same metrics per scenario. Changes should be retained only after gains
on both dev and holdout without a severe scenario regression.

The policy reads immutable catalog facets for the live candidate pool without
expanding the frozen `Candidate` contract. G still requires a specific vendored
cross-encoder that the plan does not name; H remains conditional on a specified
provider. Neither is claimed as completed.

## Cost, latency, and network disclosure

Configs A–G, P, and Q use zero prompt tokens, zero completion tokens, and no paid
service, so their model cost is $0. They run fully offline after the catalog
and selected local dependencies are present. Candidate values above remain
explicitly diagnostic until regenerated from a clean commit.

## Limitations

- Catalog metadata is sparse and inconsistent. In particular, color is absent
  from more than half of products, so color has a weaker penalty than material.
- The deterministic parser targets the organizer's controlled templates and
  common free-form terms; it is not a general natural-language understanding model.
- The `other` clarification value is a simulator wildcard. ShopLens asks it at
  most once and otherwise selects a discriminative, non-declined facet.
- Aggregate profiles contain limited independent signal; they are ingested but
  do not override explicit within-session preferences.
- Q's rating-count prior favors established products and can disadvantage
  niche or newly listed products. It is log-bounded, applies only after Top-10
  membership is frozen, and never substitutes popularity for relevance.
- Public target construction strongly favors products with many ratings, so
  Q may overfit that benchmark prior even though its coefficient is dev-only.
- Facet extraction is deliberately shallow and deterministic; it cannot infer
  every latent product attribute from sparse free-form metadata.
- The dense model is vendored. The cross-encoder is not specified by the plan;
  if it is absent, G preserves the incoming order without an online download.
- There is no image input, external vector database, cross-session profiling,
  catalog mutation, or full-parameter model training.

## Contributions

Repository history is the source of truth for individual contributions. The
identities currently present in that history contributed as follows:

| Repository identity | Contribution visible in history |
|---|---|
| TechJam2026 | Participant kit, evaluator contract, public dataset, and competition documentation |
| Kivye | Deterministic clarification sequence and starter-agent tests |
| Danixjg | Stateful BM25 retrieval, override handling, response safeguards, and integration work |

Add the remaining team identities and their exact contributions before the
submission freeze; no names are inferred where the repository contains none.

## Data attribution

The catalog and sessions derive from Amazon Reviews 2023 by McAuley Lab,
UCSD. See [DATA_ATTRIBUTION.md](DATA_ATTRIBUTION.md) for the required citation
and redistribution terms.

Submission working documents: [Devpost draft](docs/devpost-draft.md),
[demo script](docs/demo-script.md), and
[release checklist](docs/release-checklist.md).

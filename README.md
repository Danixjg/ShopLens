# TrippyShoppy

TrippyShoppy is a deterministic, offline-first conversational shopping agent for
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
      withhold already-shown asins (submission)
                       |
     bounded per-attribute constraint scoring
                       |
             freeze Top-K membership
                       |
  disclosure-order or phrase-rarity reranking
                       |
 information-gain clarification + guarded response
```

The implementation is split by responsibility:

- `src/contracts/`: shared response, state, parsing, retrieval, and run config contracts.
- `src/catalog/`: immutable JSONL loading, normalization, and checksum verification.
- `src/parsing/` and `src/state/`: controlled-language parsing, slot transitions, and query construction.
- `src/retrieval/`: weighted FTS5 BM25, optional local dense retrieval, and reciprocal-rank fusion.
- `src/scoring/`: bounded non-filtering constraint evidence, dynamic routes,
  and membership-preserving reranking by disclosure order or phrase rarity.
- `src/policy/`: candidate-facet information gain plus an experimental
  expected-question-value mode, with targeted fallback and persistent
  per-attribute decline handling.
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
  `requirements.txt` is a note recording that, not an install list.
- Hybrid/dense configs require `numpy`, `sentence-transformers`, and the
  locally vendored `models/all-MiniLM-L6-v2/` directory.
- The commands below are POSIX shell and assume `curl`, `sha256sum`, and `gzip`.
  On Windows they run as written under Git Bash or WSL. Everything except a
  *reportable* `src.eval.runner` run works on any platform; see
  [Platform requirements for reportable runs](#platform-requirements-for-reportable-runs).

Clone the repository first:

```bash
git clone https://github.com/Danixjg/ShopLens.git
cd ShopLens
```

Use a virtual environment. If you create it inside the repository, name it
`.venv`, `.venv-dense`, `.venv-wsl`, or `venv` — those are the names
`.gitignore` covers. Any other name, or any other stray file, leaves the tree
untracked-dirty and `src.eval.runner` will refuse a reportable run with a
message about uncommitted implementation changes:

```bash
python3 -m venv .venv
. .venv/bin/activate      # Windows: . .venv/Scripts/activate
```

The 50,000-product catalog is not tracked in this repository. Download it from
the organizer's participant-kit release, verify the compressed asset, and place
the decompressed file at `data/catalog.jsonl`. Run these from the repository
root:

```bash
BASE=https://github.com/TechJam2026/techjam-conversational-search/releases/download/participant-kit
curl -L -o data/catalog.jsonl.gz "$BASE/catalog.jsonl.gz"
curl -L -o data/SHA256SUMS "$BASE/SHA256SUMS"
(cd data && sha256sum --ignore-missing --check SHA256SUMS)
gzip -dk data/catalog.jsonl.gz
rm data/SHA256SUMS
python3 -m pip install -r requirements-dev.txt
python3 -m pytest -q
```

Release page:
<https://github.com/TechJam2026/techjam-conversational-search/releases/tag/participant-kit>

Both downloads land in `data/`, where `.gitignore` already covers the archive
and the decompressed catalog; `SHA256SUMS` is removed after the check so the
working tree stays clean, which the reportable runner requires.
`--ignore-missing` is required because `SHA256SUMS` also lists
`techjam-participant-kit.zip`. That asset is the organizer's starter kit, which
this repository already supersedes; it is not needed here and is deliberately
not downloaded. Without the flag the check reports it missing and exits
non-zero even when the catalog is correct. The decompressed file must be 50,000
rows with SHA-256
`da979b05a68af864cb0dcf9ee6a81c010c7e66a57978ad286c7a2e005fc69a67`, which
`Agent` re-verifies at load time. Both digests, the row count, and the pinned
public-set digest are recorded in
[data provenance and integrity](docs/data-provenance.md); the dataset files
themselves are described in [`data/README.md`](data/README.md). Note that
`python3 -m pytest -q` passes with no catalog present, so it does not by itself
confirm a complete setup; the
digest above is the check that does.

Install the portable optional dependencies before running hybrid configs. The
first hybrid run then embeds all 50,000 products on CPU before its first
session, which takes roughly 20-25 minutes and writes a ~70 MB cache to the
ignored path `data/catalog.embeddings.npz`. Every later run reuses that cache
and starts in seconds:

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

### Environment variables

The system reads exactly two environment variables. Both are optional, and the
defaults are what the official harness gets.

| Variable | Default | Effect |
|---|---|---|
| `SHOPLENS_CONFIG` | submission configuration `O` | Selects a named ablation. An unknown name falls back to baseline `A`. Read in `src/contracts/config.py`. |
| `SHOPLENS_CATALOG_SHA256` | unset | Enforces a load-time digest for a **custom** catalog path. The official path is always verified regardless, and this variable cannot bypass it. Read in `src/agent.py`. |

No credential, API-key, token, or endpoint variable exists or is read; the agent
makes no network calls.

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

Run all 200 public sessions. `SHOPLENS_CONFIG` unset selects the submission
configuration O, so a bare run reproduces what the official harness grades.
Without the optional dense dependencies O degrades to the deterministic BM25
route rather than failing:

```bash
python3 -m evaluator.local_evaluator
```

Expect one of these two results over the 200 public sessions, depending on
whether the optional dense stack is installed:

| Route | HR@10 | MRR | MTTC | Efficiency | TechnicalScore |
|---|---:|---:|---:|---:|---:|
| Hybrid (dense installed) | 0.985 | 0.825226 | 2.775 | 0.8225 | **0.904568** |
| BM25 fallback (dense absent) | 0.985 | 0.880478 | 3.000 | 0.8000 | **0.916643** |

**The fallback is not score-neutral, and on this public set it scores higher.**
Both routes find the target in the same 98.5% of sessions; the BM25 route ranks
it better once found and takes longer to get there. Do not read the larger
number as an improvement, and do not compare it against the dev/holdout tables
below, which are hybrid-only and computed on 120/80 splits rather than all 200
sessions. Check `effective_retriever` in a `src.eval.runner` row, or simply
whether `numpy` and `sentence-transformers` are importable, to know which route
produced a given number.

Name any other ablation explicitly, for example the standard-library baseline A
or the conservative clean-holdout candidate P:

```bash
SHOPLENS_CONFIG=A python3 -m evaluator.local_evaluator
SHOPLENS_CONFIG=P python3 -m evaluator.local_evaluator
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

### Platform requirements for reportable runs

The competition sets no platform requirement. Section 3 of the organizer's
final-evaluation FAQ states that there is no standardized CPU, RAM, GPU,
startup-time, or per-response limit, because teams run the final evaluation in
their own environments. `evaluator.local_evaluator` therefore runs anywhere
Python 3.10+ runs, including Windows and macOS, and that is the command an
examiner should use.

The stricter conditions below are a control this project imposes on its own
evidence log, not a competition rule. `src.eval.runner` refuses a **reportable**
run unless:

- POSIX advisory file locking (`fcntl`) is available, so concurrent writers
  cannot interleave rows in `results.jsonl`. This excludes Windows.
- For any non-BM25 config, the interpreter is CPython 3.12 on Linux x86-64 and
  every package matches `requirements-dense.lock.txt` exactly.
- Dense vectors were rebuilt in-process from the pinned model rather than read
  from a cache. The organizer's FAQ section 4 explicitly permits precomputed
  local artifacts; this repository declines the allowance for reportable rows
  only, and a cold reportable dense run therefore spends roughly 22 minutes
  embedding the catalog before the first session.

On any other platform, use `--allow-dirty --results-log <path outside the repo>`.
Those runs are diagnostics by definition, and the runner records exactly why in
`reportability_reasons`. The metrics themselves are portable: config O, P and
their splits reproduce to six decimal places on Windows x86-64 with an unpinned
dense stack, differing from the reference lock in 57 packages.

TechnicalScore is the organizer's recommended composite, defined in
[`docs/evaluation_config.json`](docs/evaluation_config.json):

```text
efficiency      = clip((11 - MTTC) / 10, 0, 1)
TechnicalScore  = 0.50 * HitRate@10 + 0.30 * MRR + 0.20 * efficiency
```

A session that never surfaces the target counts as turn 11 for MTTC. Because
HitRate carries half the weight and reranking cannot change Top-10 membership in
the submission configuration, reranking moves TechnicalScore only through the
0.30 MRR term.

The public organizer starter (which does not ask clarification questions)
reports HR@10 `0.125`, MRR `0.068034`, MTTC `9.81`, and TechnicalScore
`0.10671`, as published in
[`docs/baseline_results.json`](docs/baseline_results.json). That starter agent
is not vendored here, so the figure is quoted rather than regenerated. Config A
is an honest BM25 baseline with clarification enabled and is therefore not
directly comparable.

A single scripted session is useful for inspecting behaviour by hand:

```bash
python3 scripts/demo_session.py --config O
```

The script draws box-rule characters, so on a Windows console prefix it with
`PYTHONIOENCODING=utf-8` to avoid a `UnicodeEncodeError` from the default
cp1252 codec. See [demo script](docs/demo-script.md) for the walkthrough it is
built around.

Reportable results are generated by `src.eval.runner` only from an identifiable
clean implementation whose requested local capabilities actually loaded and
whose guarded response fallback handled no unexpected exceptions. The runner
records those capability checks and fallback count alongside config flags,
locked dependencies, platform, pinned model and vector digests, catalog and
dataset digests, cache provenance, latency, memory, and four Git-state gates.
Dev and holdout use the deterministic stratified 120/80 split.

### Final evaluation procedure

The 800 final evaluation sessions are released **after** the Devpost submission
deadline, and are run against the commit submitted before it. Nothing in this
repository can contain those results in advance, which is why `results.json` is
untracked: the file that matters is generated later, not committed here.

When the final package is released:

1. Check out the exact submitted commit. Do not modify the Agent, its
   configuration, indexes, or any other solution component afterwards.
2. Run the **unmodified** official evaluator, `evaluator/local_evaluator.py`,
   against the released sessions. Do not substitute `src.eval.runner`, which is
   this project's own split harness; it wraps the official `evaluate()` for
   internal ablations and is not the submission path.
3. Retain the generated `results.json` **including its per-session
   `sessions` array**, together with the submitted commit hash and the
   environment and execution details listed under
   [Environment and execution disclosure](#environment-and-execution-disclosure).
   The organizer may request logs or other supporting evidence.

A `results.json` produced from the 200 public sessions is **not** final
evaluation evidence. If one is present in a working tree from earlier local
runs, it records the public set and should not be reported or retained as the
final artifact.

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

Every candidate below was frozen after dev-only tuning and opened on holdout at
most once, under a retention gate registered before the run. All used true
hybrid retrieval and the pinned CPU model, with zero agent exceptions, zero
evaluator exceptions, and zero invalid responses.

**Configuration O is the submission configuration.** T is the previous
submission and remains the canonical comparison used throughout the
experiments; Q is the parent both branches descend from. The `Holdout status`
column separates a clean untouched holdout from an exploratory one, and the
reasoning behind choosing a configuration whose holdout is exploratory is set
out in [Retention decision](#retention-decision) below.

| Config | Dev HR@10 | Dev MRR | Dev MTTC | Dev Score | Holdout HR@10 | Holdout MRR | Holdout MTTC | Holdout Score | Holdout status |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| F, new state/policy | 0.941667 | 0.574018 | 3.133333 | 0.800372 | — | — | — | — | not opened at this commit |
| P, phrase rarity | 0.941667 | 0.639239 | 3.133333 | 0.819939 | 0.975000 | 0.644861 | 2.850000 | 0.843958 | clean |
| R, symmetric routing | 0.941667 | 0.651012 | 3.141667 | 0.823304 | 0.975000 | 0.652153 | 2.837500 | 0.846396 | clean |
| S, profile affinity | 0.941667 | 0.649610 | 3.133333 | 0.823050 | 0.975000 | 0.654653 | 2.850000 | 0.846896 | clean |
| Q, popularity prior | 0.941667 | 0.779722 | 3.133333 | 0.862083 | 0.975000 | 0.766071 | 2.850000 | 0.880321 | exploratory |
| T, R+S+Q combined (previous submission) | 0.941667 | 0.795913 | 3.141667 | 0.866774 | 0.975000 | 0.802932 | 2.837500 | 0.891630 | exploratory |
| N, Q plus no-repeat | — | — | — | — | — | — | — | — | diagnostic only, no reportable row |
| **O, N plus disclosure-order rank (submission)** | **0.983333** | **0.844722** | **2.833333** | **0.908416** | **0.987500** | **0.795982** | **2.687500** | **0.898795** | **exploratory** |
| U, expected question value | 0.941667 | 0.641323 | 3.175000 | 0.819730 | — | — | — | — | rejected on dev gate |
| V, facet population gate | 0.941667 | 0.639239 | 3.133333 | 0.819939 | — | — | — | — | tied P, not retained |

Configurations without a row above hold no reportable evidence and are not
claimed: **G** and **H** depend on components the plan does not specify (a
vendored cross-encoder and an LLM provider), and **W**, **X**, **Y**, and **J**
are research-derived one-flag ablations that are defined and runnable but have
not been measured under a frozen gate. **N** is the middle rung of the O
decomposition and is diagnostic only. `results.jsonl` is the source of truth for
which configurations have been run.

Per-scenario evidence for the submission configuration O:

| Scenario | Dev HR@10 | Dev MRR | Dev MTTC | Holdout HR@10 | Holdout MRR | Holdout MTTC |
|---|---:|---:|---:|---:|---:|---:|
| Boundary | 1.0000 | 0.8611 | 3.8333 | 0.7500 | 0.3690 | 4.2500 |
| Browsing | 0.9792 | 0.8038 | 2.5833 | 1.0000 | 0.8524 | 2.5000 |
| Buying | 0.9792 | 0.8740 | 2.4583 | 1.0000 | 0.7842 | 2.1250 |
| Intent Override | 1.0000 | 0.8704 | 4.1667 | 1.0000 | 0.8194 | 4.1667 |

Boundary is the weak scenario on holdout and the honest caveat on O: 6 dev and 4
holdout sessions, so a single miss moves it by 0.25, and its holdout MRR of
`0.3690` is the lowest cell in the table.

Q was selected on dev, where against P it improved 50 target ranks, regressed
none, and left 70 unchanged. HR@10 and MTTC were identical in every scenario.
Dev MRR rose from P to Q for Boundary (`0.7417` → `0.8889`),
Browsing (`0.6708` → `0.7760`), Buying (`0.6042` → `0.7948`), and Intent
Override (`0.6144` → `0.7130`). Q's later holdout row scored HR@10 `0.9750`,
MRR `0.7661`, MTTC `2.8500`, and TechnicalScore `0.8803`. Because the popularity
hypothesis followed an aggregate review of target rating counts across all 200
public sessions, that holdout result is exploratory, not statistically
untouched. A scenario-stratified paired bootstrap (10,000
resamples, seed 2026) estimates Q's dev TechnicalScore gain over P at
`0.042145`, with a 95% interval of `[0.030926, 0.054362]`.

Weighting the frozen dev and holdout aggregates by their 120/80 sample counts
gives an all-public estimate of HR@10 `0.955`, MRR `0.641488`, MTTC `3.02`,
and TechnicalScore `0.829546`, without rerunning or retuning on holdout.

P's per-scenario evidence, for comparison against the O table above:

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

### Retention decision

`O` is the submission configuration. `T` is the previous submission and stays
in this document as the canonical comparison used throughout the experiments;
`Q` is the parent both branches descend from. The reasoning matters more than
the number.

```text
Q
├── N = Q + exclude_shown
│   └── O = N + ordered_rerank    <- CURRENT SUBMISSION CONFIGURATION
│
└── T = Q + symmetric_intent_routing + profile_rerank
                                   <- PREVIOUS COMPARISON CONFIGURATION
```

`N` and `O` are one-flag steps along a single branch, and `T` is a sibling of
`N` rather than an ancestor. The five flags separating `T` from `O` are
genealogical distance between two children of `Q`, not a change set applied to
`T`; reading them as a change set makes the difference look larger and less
attributable than it is.

**Why an exploratory holdout does not disqualify it.** The competition
specification designates all 200 public sessions as development data and keeps
800 sessions private for grading. The 120/80 dev/holdout split used throughout
this repository is therefore a control this project imposed on itself, not a
competition requirement. `Q`'s popularity hypothesis followed an aggregate
review of target rating counts across all 200 public sessions, which relaxed
that self-imposed control, and the exploratory label records precisely where.
`O` inherits the label twice over: it contains `Q`'s prior, and it was itself
selected from dev-split flag isolation. `T` carries the label for the first
reason alone. What the label constrains is the strength of the claim attached
to the holdout number, not the validity of the configuration itself.

**What the gain is attributable to.** Runtime-only one-flag ablations anchored
on `O`, with an `O` control reproducing its dev row to six decimal places,
decompose the dev margin with no residual: `Q` at `0.862083`, plus
`exclude_shown` gives `N` at `0.904250`, plus `ordered_rerank` gives `O` at
`0.908416`. Removing `exclude_shown` from `O` returns HR@10 to `0.941667` —
`T`'s value — in every scenario individually, so exclusion is necessary and
sufficient for the entire dev HitRate gain. `ordered_rerank` cannot change
Top-10 membership by construction and contributes ranking order only. Both of
`T`'s extra flags measured negative when added to this branch. `N` holds no
reportable row: it is the middle rung of the decomposition, and the figure
quoted for it here is diagnostic, not evidence.

**What transferred to holdout, and what did not.** HitRate and MTTC
transferred; MRR did not. The single extra holdout conversion lands in Intent
Override, taking it from 11 of 12 to 12 of 12 — the same scenario that reached
a perfect score on dev, and the one the mechanism names, since
`src/state/manager.py` clears the shown-asin memory on an intent override
because a hit cannot register before the override turn. MTTC improved on both
splits, by `0.308334` turns on dev and `0.150000` on holdout. MRR moved the
other way: `+0.048809` on dev against `-0.006950` on holdout, which is a sign
reversal rather than shrinkage. The aggregate margin over `T` fell from
`+0.041642` on dev to `+0.007165` on holdout; headroom explains part of that,
since `T` misses seven of 120 dev sessions but only two of 80 holdout sessions,
and it does not explain all of it. `O` is retained on the mechanism and on the
two components that replicated, not on the TechnicalScore margin.

**Why the downside is bounded.** Exclusion is the one component here that can
change Top-10 membership, and it changes it in a single direction: it withholds
products a session has already returned and scored. A safety valve in
`src/agent.py` keeps the unfiltered pool whenever filtering would empty it, so
the mechanism cannot cost recall, and every other reranker permutes order
strictly inside the frozen Top-10. The exposure worth naming is a different
one. "The session continued, therefore none of those was the target" is a proof
under this evaluator, which scores every returned asin and stops at the first
hit, but only an inference in deployment. Part of the gain is coupled to the
evaluation protocol rather than to recommendation quality, and that is stated
here rather than left for a reader to discover.

**The clean-only alternative, stated plainly.** If an untouched holdout is
required, `S` is the best clean candidate at `0.846896`, with `R` just behind at
`0.846396`; both beat `P` with no caveat attached. Their margin is small — `S`
gains `0.002938` over `P` on holdout — and that is the honest trade. `S` is
clean but barely separable from `P`, while `O` is a large dev gain and a small
holdout gain carrying a disclosed caveat. This project reports both rather than
only the one that
flatters it, and `tests/test_research_attribution.py` fails if any line quoting
an exploratory score omits the label.

## Ablation configurations

Select an ablation with `SHOPLENS_CONFIG`. An unset value selects the
submission configuration O; an unknown value still falls back safely to
baseline A. Hybrid configurations use the optional dense install when present
and degrade to BM25 when it is absent.

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
| R | P plus precision retrieval routing for every hard-constraint intent, not Buying alone |
| S | P plus a bounded user-profile affinity prior inside the frozen Top-10 |
| T | R, S, and Q combined, to measure whether the three compose |
| U | P plus deterministic expected-question-value clarification |
| V | P plus catalog-population gating of clarification facets |
| W | T with the dense encoder indexing title, categories and features only |
| X | T plus suppression of a preference the shopper replaced on override |
| Y | T with reranking applied to the top 50 before truncation, so it can change Top-10 membership |
| J | Y with the widened window restricted to per-session evidence, so the popularity and profile priors may reorder a frozen Top-10 but not decide its membership |
| N | Q plus no-repeat recommendations: an asin already offered and scored is withheld from later turns, and an intent override clears that memory |
| O | N with disclosure-order ranking replacing phrase-rarity reranking inside the frozen Top-10 |
| M | O with disclosures segmented against known catalog values, so a field containing a semicolon stays one constraint |
| Z | Clarification off, diagnostic only |
| K | O with the clarification attribute sequence extended by "budget"; experimental, not yet dev-gated |
| L | O with the clarification policy excluding an attribute already covered by an active disclosed slot; experimental, not yet dev-gated |
| AA | O with clarification chosen by embedding similarity to the near-miss pool (ranks 11-50) instead of discrete facet information gain; experimental, not yet dev-gated. Named "AA" rather than the last free single letter ("I") -- proposed as the next value under a spreadsheet-column-style scheme (A..Z, then AA, AB, ...); open question for the team, not a unilateral decision. |

U is a documented research ablation, not a retained configuration. Its clean
dev run at `87834f4` kept HR@10 at `0.941667` and raised MRR from P's
`0.639239` to `0.641323`, but MTTC moved from `3.133333` to `3.175000`.
TechnicalScore therefore fell from `0.819939` to `0.819730` (`-0.000209`),
missing the pre-registered retention gate. U was rejected without opening
holdout; the reportable dev record remains in `results.jsonl`. U independently
adapts the paper's EVPI idea into a target-free expected Top-K posterior-mass
gain over catalog-facet answers. Sparse or missing facets and free-form answers
outside those catalog proxies limit what the score can represent.

V has now been **measured once on dev**. It is P with only clarification facet
eligibility changed: a facet is asked only when at least one candidate in the
live pool can answer it, with an unconditional fallback so the agent never
loses the ability to ask. The change is inert without a catalog and cannot
alter retrieval, scoring, or Top-10 membership. Its retention gate was frozen
in [the TDD record](docs/testing/facet-population-gate.tdd.md) before the run.
The reportable dev row at `547bdb1` tied P exactly at `0.819939` on every
metric, every scenario, and the turn count, so V cleared its gate only by a tie
and was not kept; holdout was never opened. The cause is measurable rather than
mysterious: the gate drops a facet only when no candidate in the pool carries
it, and `feature`, which is asked first, is populated on 99.43% of the
50,000-product catalog.

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

Every configuration in the ablation table (A, B, C, D, E, F, G, H, P, Q, R, S,
T, U, V, W, X, Y, J, N, O, and Z) uses zero prompt tokens, zero completion
tokens, and no paid service, so the model cost of each is $0. All of them run
fully offline once the catalog and the selected local dependencies are present.
The vendored embedding model is loaded with `local_files_only`, and no
configuration opens a network connection at construction or on any turn.

Two configurations name an optional component and remain $0 when it is absent.
G requests a local cross-encoder and preserves the incoming order without an
online download when that model is missing. H requests LLM ranking, but no
implementation or provider is shipped: the evaluator pins the effective
`llm_rank` to false and records the reason, so an H row measures the unchanged
offline path rather than an LLM result. Hybrid configurations likewise degrade
to the deterministic BM25 route when the optional dense install is absent.

Experimental results remain subject to their stated retention gates.

### Environment and execution disclosure

Section 3 of the organizer's final-evaluation FAQ asks each team to disclose the
Python version, hardware, dependencies, runtime, latency, token usage, and
estimated model cost behind its reported results. The values below are
transcribed from the reportable `results.jsonl` rows for the submission
configuration O at commit `fedd07e8`; every field is recorded automatically by
`src.eval.runner` and can be re-read from that file.

| Field | O / dev | O / holdout |
|---|---|---|
| Python | CPython 3.12.13 | CPython 3.12.13 |
| Platform | Linux x86-64 (WSL2 `6.18.33.2`) | Linux x86-64 (WSL2 `6.18.33.2`) |
| SQLite | 3.46.1 | 3.46.1 |
| Compute device | CPU | CPU |
| Dependencies | `requirements-dense.lock.txt`, hash-pinned, zero mismatches | same |
| Wall clock | 1340.4 s | 1299.0 s |
| Of which agent init | 1307.1 s (in-process catalog embedding) | 1274.7 s |
| Peak RSS | 1.95 GB | 1.98 GB |
| Turn latency p50 / p95 / p99 | 93.6 / 145.8 / 166.3 ms | 107.9 / 168.1 / 199.2 ms |
| Turn latency mean / max | 98.4 / 175.3 ms | 113.6 / 311.8 ms |
| Turns measured | 338 | 214 |
| Prompt / completion tokens | 0 / 0 | 0 / 0 |
| Estimated model cost | $0 | $0 |

Nearly all wall-clock time is the one-time in-process embedding of the 50,000
product catalog, which the reportable path performs deliberately rather than
reusing a cache. Steady-state cost is the per-turn latency above. Ordinary use
reuses the fingerprinted cache at `data/catalog.embeddings.npz` and starts in
seconds. No GPU is used or required; `DenseRetriever` pins `device="cpu"` and
fails closed if any parameter leaves it.

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
| MaxLZE | ProductAgent research integration, attribution, and TDD workflow |

Add the remaining team identities and their exact contributions before the
submission freeze; no names are inferred where the repository contains none.

## Data attribution

The catalog and sessions derive from Amazon Reviews 2023 by McAuley Lab,
UCSD. See [DATA_ATTRIBUTION.md](DATA_ATTRIBUTION.md) for the required citation
and redistribution terms.

## Research attribution

The experimental expected-question-value clarification policy is an
independent deterministic adaptation of the EVPI framing introduced by Sudha
Rao and Hal Daumé III; it is inspired by the paper, not a reproduction or port
of its neural model, code, or data:

> Sudha Rao and Hal Daumé III. 2018. *Learning to Ask Good Questions: Ranking
> Clarification Questions using Neural Expected Value of Perfect Information.*
> Proceedings of the 56th Annual Meeting of the Association for Computational
> Linguistics (Volume 1: Long Papers), ACL 2018, pages 2737–2746.

DOI: [10.18653/v1/P18-1255](https://doi.org/10.18653/v1/P18-1255). Canonical
publication: [ACL Anthology](https://aclanthology.org/P18-1255/). The paper is
licensed under Creative Commons Attribution 4.0 International (CC BY 4.0). See
[Research attribution](docs/research-attribution.md) for the adoption boundary.

ShopLens's clarification-quality guards and its rule for reporting
membership-preserving rerank ablations are informed by:

> Jingheng Ye, Yong Jiang, Xiaobin Wang, Yinghui Li, Yangning Li, Hai-Tao
> Zheng, Pengjun Xie, and Fei Huang. 2024. *ProductAgent: Benchmarking
> Conversational Product Search Agent with Asking Clarification Questions*.
> arXiv:2407.00942 [cs.IR].

arXiv: [2407.00942](https://arxiv.org/abs/2407.00942). DOI:
[10.48550/arXiv.2407.00942](https://doi.org/10.48550/arXiv.2407.00942). The
preprint carries the arXiv non-exclusive distribution license 1.0, which
grants no third-party redistribution or derivative right, so no copy or
conversion of it is tracked in this repository. ShopLens contains no
ProductAgent code and no AliMe KG records, and it runs no language model, SQL
statistics tool, or user simulator; the adopted ideas are implemented
independently. See
[ProductAgent source audit](docs/productagent-integration.md) for the license
finding and the adoption boundary.

Submission working documents: [Devpost draft](docs/devpost-draft.md),
[demo script](docs/demo-script.md), and
[release checklist](docs/release-checklist.md).

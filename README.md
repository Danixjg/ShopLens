<a id="readme-top"></a>

[![Contributors][contributors-shield]][contributors-url]
[![Forks][forks-shield]][forks-url]
[![Stars][stars-shield]][stars-url]
[![Issues][issues-shield]][issues-url]
[![Python 3.10+][python-shield]][python-url]
[![Model cost $0][cost-shield]][cost-url]

<br />
<div align="center">

<h1 align="center">TrippyShoppy</h1>

<p align="center">
  A shopping assistant that shows you ten products <em>and</em> asks one good
  question — on the same turn.
  <br />
  Built for the TechJam 2026 conversational-search challenge. Runs entirely on
  your laptop, with no API keys and no model bill.
  <br />
  <br />
  <a href="#getting-started">Get started</a>
  &middot;
  <a href="#usage">See it run</a>
  &middot;
  <a href="#results">Results</a>
  &middot;
  <a href="https://github.com/Danixjg/TrippyShoppy/issues">Report a bug</a>
</p>
</div>

> The repository was renamed from `ShopLens`, and the code still carries that
> name: the package paths, the `SHOPLENS_CONFIG` and `SHOPLENS_CATALOG_SHA256`
> variables, and the `shoplens-*` log paths are all unchanged.

<details>
  <summary><b>Table of contents</b></summary>
  <ol>
    <li><a href="#about-the-project">About the project</a>
      <ul>
        <li><a href="#a-real-session">A real session</a></li>
        <li><a href="#how-a-turn-works">How a turn works</a></li>
        <li><a href="#what-lives-where">What lives where</a></li>
        <li><a href="#built-with">Built with</a></li>
      </ul>
    </li>
    <li><a href="#getting-started">Getting started</a>
      <ul>
        <li><a href="#prerequisites">Prerequisites</a></li>
        <li><a href="#installation">Installation</a></li>
        <li><a href="#optional-turn-on-meaning-based-search">Optional: meaning-based search</a></li>
      </ul>
    </li>
    <li><a href="#usage">Usage</a></li>
    <li><a href="#results">Results</a></li>
    <li><a href="#limitations">Limitations</a></li>
    <li><a href="#roadmap">Roadmap</a></li>
    <li><a href="#contributing">Contributing</a></li>
    <li><a href="#license-and-data-use">License and data use</a></li>
    <li><a href="#contact">Contact</a></li>
    <li><a href="#acknowledgments">Acknowledgments</a></li>
  </ol>
</details>

## About the project

Shopping search usually makes you choose. Either you type the perfect query and
hope, or you answer a questionnaire before you see anything at all.

TrippyShoppy does both at once. Every turn it returns up to ten ranked products
**and** asks the one question that would narrow the search the most. You always
have something to look at, and the conversation still gets somewhere.

Three ideas do most of the work:

- **It remembers, and it lets you change your mind.** Say "waterproof" and then
  "leather" and it keeps both. Say "actually, cotton instead" and it drops only
  the preference you replaced, not everything you have told it.
- **A guess never deletes a product.** Preferences push products down the list;
  they never filter anything out of the pool. If the parser misreads you, the
  product you wanted gets a worse rank — it does not disappear.
- **It asks the question that splits the field.** Each turn it looks at the
  products still in play and asks about the attribute that would divide them
  most evenly, skipping anything you have already answered or declined.

On the 200 public practice sessions it finds the shopper's target in 98.5% of
them, in under three turns on average. It costs $0 to run: no paid API, no
network access after setup, and zero tokens either way.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

### A real session

Verbatim output of `python3 scripts/demo_session.py --config O`, trimmed to the
first three products per turn:

```text
config O | retrieval hybrid | clarification info_gain | catalog 50000 products

─── turn 1 ──────────────────────────────────────────────────────────
customer : I'm looking for Shoes, but I'm still exploring.
agent    : I found many plausible matches. Do you have a feature preference?
asks     : feature
top 10   :
   1. THE NORTH FACE Aphrodite Motion 4in Womens Shorts                B07XVS4BKZ
   2. Havaianas Women's Slim USA Stars Flip Flop Sandal                B07L8GMXV3
   3. THE NORTH FACE Women's Tamburello Insulated Jacket (Standard an… B097NJ37NJ
   ... 7 more

─── turn 2 ──────────────────────────────────────────────────────────
customer : For that, what matters is: waterproof; leather.
agent    : I found many plausible matches. Do you have a color preference?
asks     : color
top 10   :
   1. Timberland Toddler/Little Kid Field Boot 6" Hiker                B001UE70D0
   2. KIWI Shoe Waterproofer Protector                                 B0B7J5CBDK
   3. Under Armour Men's Field Ops GORE-TEX                            B01MQKGWS7
   ... 7 more

─── turn 3 ──────────────────────────────────────────────────────────
customer : Actually, ignore my earlier preference. What I need is: cotton.
agent    : Do you have a material preference?
asks     : material
top 10   :
   1. Timberland Men's Chestnut Ridge Waterproof Boot                  B00JC33QVQ
   2. Littleplum Boys Snow Boots Winter Waterproof Antiskid Boots Hik… B08FFTK17T
   3. Patagonia Women's Activist Fleece Waterproof Snow Boot           B00HQ4ZVRA
   ... 7 more

tokens   : prompt 0, completion 0 (fully offline)
```

Ten products every turn, a different question every turn, and never the
same question twice.

### How a turn works

```text
   what the shopper typed
             |
   read the message          new preferences, or a change of mind
             |
   search the catalog        keyword search, plus optional meaning-based search
             |
   skip what's been shown    products already offered this session step aside
             |
   score, don't filter       preferences move products down, never out
             |
   freeze the top ten        order can still change, membership cannot
             |
   pick one question         the one that best splits what's left
             |
   ten products + one question
```

### What lives where

| Folder | What it does |
|---|---|
| `src/parsing/`, `src/state/` | Reads the shopper's message and keeps track of what they have said so far |
| `src/catalog/` | Loads the 50,000-product catalog and checks it has not been altered |
| `src/retrieval/` | Keyword search (SQLite FTS5), optional meaning-based search, and a merge of the two |
| `src/scoring/` | Scores products against stated preferences and orders the top ten |
| `src/policy/` | Chooses the clarification question |
| `src/agent.py` | Puts it together and always returns a valid response, even on an unexpected error |
| `agent.py`, `starter/agent.py` | Thin entry points for the competition harness |
| `src/contracts/` | The shared data shapes and the list of runnable configurations |

The agent implements the organizers' `Agent.reset(...)` and `Agent.respond(...)`
interface. It never modifies the catalog or the evaluator.

### Built with

* [Python 3.10+](https://www.python.org/) — standard library only for the baseline
* [SQLite FTS5](https://www.sqlite.org/fts5.html) — keyword search, built into CPython
* [sentence-transformers](https://www.sbert.net/) — optional meaning-based search
* [all-MiniLM-L6-v2](models/README.md) — the embedding model, vendored locally and loaded by path
* [NumPy](https://numpy.org/) · [pytest](https://docs.pytest.org/)

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Getting started

### Prerequisites

* Python 3.10 or newer (developed on 3.12).
* SQLite with FTS5 — standard in CPython, nothing to install.
* No third-party packages for the keyword-only baseline. `requirements.txt` is a
  note recording that fact, not an install list.
* The commands below are POSIX shell and use `curl`, `sha256sum` and `gzip`. On
  Windows they work as written in Git Bash or WSL.

### Installation

1. Clone the repository.

   ```bash
   git clone https://github.com/Danixjg/TrippyShoppy.git
   cd TrippyShoppy
   ```

2. Create a virtual environment. If you put it inside the repository, name it
   `.venv`, `.venv-dense`, `.venv-wsl` or `venv` — `.gitignore` covers those
   names, and any other stray file makes the tree look dirty to the evidence
   runner.

   ```bash
   python3 -m venv .venv
   . .venv/bin/activate      # Windows: . .venv/Scripts/activate
   ```

3. Download the catalog. It is not tracked here — it comes from the organizers'
   participant-kit release. Run this from the repository root.

   ```bash
   BASE=https://github.com/TechJam2026/techjam-conversational-search/releases/download/participant-kit
   curl -L -o data/catalog.jsonl.gz "$BASE/catalog.jsonl.gz"
   curl -L -o data/SHA256SUMS "$BASE/SHA256SUMS"
   (cd data && sha256sum --ignore-missing --check SHA256SUMS)
   gzip -dk data/catalog.jsonl.gz
   rm data/SHA256SUMS
   ```

   Release page:
   <https://github.com/TechJam2026/techjam-conversational-search/releases/tag/participant-kit>

   `--ignore-missing` is needed because `SHA256SUMS` also lists the organizers'
   starter kit, which this repository supersedes and does not download; without
   it the check exits non-zero even when the catalog is correct. The
   decompressed file must be 50,000 rows matching the digest recorded in
   [data provenance and integrity](docs/data-provenance.md), which `Agent`
   re-verifies at load time. Note that `pytest -q` passes with no catalog
   present, so it does not by itself confirm a complete setup — the digest is
   the check that does.

4. Install the test dependencies and check the install.

   ```bash
   python3 -m pip install -r requirements-dev.txt
   python3 -m pytest -q
   ```

That is enough to run everything except the meaning-based search.

### Optional: turn on meaning-based search

The submission configuration uses keyword search **and** an embedding model. It
still runs without the extra packages — it quietly falls back to keyword-only —
so this step is optional.

```bash
python3 -m pip install -r requirements-dense.txt
```

The first run then embeds all 50,000 products on CPU before the first session,
which takes roughly 20–25 minutes and writes a ~70 MB cache to
`data/catalog.embeddings.npz`. Later runs reuse the cache and start in seconds.

For results you intend to report, install the fully pinned environment instead
(CPython 3.12, Linux x86-64):

```bash
python3 -m pip install -r requirements-dense.lock.txt
```

`pip` is the canonical path. [uv](https://github.com/astral-sh/uv) installs the
same lock much faster if you have it, and resolves to an identical package set:

```bash
uv venv --python 3.12 .venv-dense
uv pip install --python .venv-dense/bin/python -r requirements-dense.lock.txt
```

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Usage

**Score all 200 public sessions.** This is the command an examiner should run;
it reproduces what the official harness grades.

```bash
python3 -m evaluator.local_evaluator
```

**Watch a single conversation** turn by turn:

```bash
python3 scripts/demo_session.py --config O
```

The script draws box-rule characters, so on a Windows console prefix it with
`PYTHONIOENCODING=utf-8`. See the [demo script](docs/demo-script.md) for the
walkthrough it is built around.

**Try a different setup.** Every experiment is a named configuration; see
[every configuration](#every-configuration) for the full list.

```bash
SHOPLENS_CONFIG=A python3 -m evaluator.local_evaluator   # keyword-only baseline
SHOPLENS_CONFIG=P python3 -m evaluator.local_evaluator   # conservative candidate
```

**Settings.** The system reads exactly two environment variables. Both are
optional, and the defaults are what the official harness gets.

| Variable | Default | What it does |
|---|---|---|
| `SHOPLENS_CONFIG` | evaluator default `O+` | Picks a named configuration. An unknown name falls back to baseline `A`. Read in `src/contracts/config.py`. |
| `SHOPLENS_CATALOG_SHA256` | unset | Checks a **custom** catalog file against a digest you supply. The official catalog path is always verified anyway, and this cannot switch that off. Read in `src/agent.py`. |

There is no API key, token or endpoint variable, because the agent never makes a
network call.

<details>
<summary><b>Splits, evidence logging and the final evaluation</b></summary>

<br />

Alongside the official evaluator, this project keeps its own harness that runs a
fixed 120-session development split and an 80-session holdout split, and appends
each result to `results.jsonl` with the configuration, scores, split and Git
commit:

```bash
python3 -m src.eval.runner --config P --split dev
python3 -m src.eval.runner --config P --split holdout
```

That runner only writes a row it is willing to stand behind. It refuses to log a
**reportable** result unless the working tree is clean, the requested search
components actually loaded, no response fell back to the error handler, and the
pinned dependency set matches exactly. Anything else must be written outside the
repository:

```bash
python3 -m src.eval.runner --config P --split dev \
  --allow-dirty --results-log /tmp/shoplens-p-dev.jsonl
```

Each row also records Python version, platform, model and vector digests,
catalog and dataset digests, cache provenance, latency and memory.

**Platform note.** The competition sets no platform requirement — section 3 of
the organizers' FAQ confirms there is no standard CPU, RAM, GPU or timing limit,
because teams run the final evaluation themselves. `evaluator.local_evaluator`
runs anywhere Python 3.10+ runs, Windows and macOS included. The stricter rules
below apply only to this project's own evidence log:

- POSIX file locking (`fcntl`) must be available so concurrent writers cannot
  interleave rows, which rules out Windows.
- For anything beyond the keyword-only route, the interpreter must be CPython
  3.12 on Linux x86-64 with the exact locked packages.
- Embeddings must be rebuilt in-process rather than read from the cache. The
  organizers' FAQ section 4 permits precomputed artifacts; this repository
  declines the allowance for reportable rows only, which is why a cold
  reportable run spends about 22 minutes embedding before its first session.

The metrics themselves are portable: configurations O and P reproduce to six
decimal places on Windows x86-64 with an unpinned dense stack.

**Final evaluation.** The 800 grading sessions are released *after* the Devpost
deadline and are run against the submitted commit. When they arrive:

1. Check out the exact submitted commit and change nothing.
2. Run the unmodified official evaluator, `evaluator/local_evaluator.py`, against
   the released sessions. Do not substitute `src.eval.runner` — that is this
   project's internal split harness, not the submission path.
3. Keep the generated `results.json` **including its per-session `sessions`
   array**, with the commit hash and the environment details from the
   [disclosure table](#environment-cost-and-latency).

A `results.json` built from the 200 public sessions is not final-evaluation
evidence, which is why that file is untracked here.

</details>

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Results

Over the 200 public sessions, with configuration O (the latest configuration
with reportable evidence under the retention protocol):

| Search route | Found target (HR@10) | Rank quality (MRR) | Turns to find it (MTTC) | Score |
|---|---:|---:|---:|---:|
| Keyword + meaning-based | 0.985 | 0.825226 | 2.775 | **0.904568** |
| Keyword only (fallback) | 0.985 | 0.880478 | 3.000 | **0.916643** |

**Read that second row carefully: the keyword-only fallback is not a
downgrade on this set — it scores higher.** Both routes find the target in the
same 98.5% of sessions; the keyword-only route ranks it a little better once
found, and takes a little longer to get there. Do not read the higher number as an improvement, and do not compare
either against the split tables below, which are meaning-based only and computed
on 120/80 splits rather than all 200 sessions. To tell which route produced a
number, check `effective_retriever` in a `src.eval.runner` row, or simply whether
`numpy` and `sentence-transformers` are importable.

For reference, the organizers' starter agent — which never asks a question —
scores HR@10 `0.125`, MRR `0.068034`, MTTC `9.81` and `0.10671` overall, as
published in [`docs/baseline_results.json`](docs/baseline_results.json). That
agent is not vendored here, so the figure is quoted rather than regenerated.

**How the score is computed** ([`docs/evaluation_config.json`](docs/evaluation_config.json)):

```text
efficiency      = clip((11 - MTTC) / 10, 0, 1)
TechnicalScore  = 0.50 * HitRate@10 + 0.30 * MRR + 0.20 * efficiency
```

A session that never surfaces the target counts as turn 11. Because hit rate
carries half the weight and reordering cannot change which ten products are
shown, reranking moves the score only through the 0.30 MRR term.

<a id="the-experiment-log"></a>
<details>
<summary><b>The experiment log — how the submission was chosen</b></summary>

<br />

Every candidate below was frozen after tuning on the development split and
opened on holdout at most once, against a retention gate written down before the
run. All used the meaning-based route and the pinned CPU model, with zero agent
exceptions, zero evaluator exceptions and zero invalid responses.

**Configuration O+ is the evaluator default.** O remains the latest configuration
with a reportable row under the retention protocol, while T stays here as the
earlier comparison used throughout the experiments; Q is the parent both
branches descend from. The last column separates a holdout that was never
influenced by tuning ("clean") from one that was ("exploratory").

| Config | Dev HR@10 | Dev MRR | Dev MTTC | Dev Score | Holdout HR@10 | Holdout MRR | Holdout MTTC | Holdout Score | Holdout status |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| F, new state/policy | 0.941667 | 0.574018 | 3.133333 | 0.800372 | — | — | — | — | not opened at this commit |
| P, phrase rarity | 0.941667 | 0.639239 | 3.133333 | 0.819939 | 0.975000 | 0.644861 | 2.850000 | 0.843958 | clean |
| R, symmetric routing | 0.941667 | 0.651012 | 3.141667 | 0.823304 | 0.975000 | 0.652153 | 2.837500 | 0.846396 | clean |
| S, profile affinity | 0.941667 | 0.649610 | 3.133333 | 0.823050 | 0.975000 | 0.654653 | 2.850000 | 0.846896 | clean |
| Q, popularity prior | 0.941667 | 0.779722 | 3.133333 | 0.862083 | 0.975000 | 0.766071 | 2.850000 | 0.880321 | exploratory |
| T, R+S+Q combined (previous submission) | 0.941667 | 0.795913 | 3.141667 | 0.866774 | 0.975000 | 0.802932 | 2.837500 | 0.891630 | exploratory |
| N, Q plus no-repeat | — | — | — | — | — | — | — | — | diagnostic only, no reportable row |
| **O, N plus disclosure-order rank (latest reportable evidence)** | **0.983333** | **0.844722** | **2.833333** | **0.908416** | **0.987500** | **0.795982** | **2.687500** | **0.898795** | **exploratory** |
| U, expected question value | 0.941667 | 0.641323 | 3.175000 | 0.819730 | — | — | — | — | rejected on dev gate |
| V, facet population gate | 0.941667 | 0.639239 | 3.133333 | 0.819939 | — | — | — | — | tied P, not retained |

Configurations without a row hold no reportable evidence and are not claimed. G
and H depend on components the plan never specifies (a vendored cross-encoder
and an LLM provider); W, X, Y, J, L and AA are defined and runnable but have not
been measured against a frozen gate; N is the middle rung of the O
decomposition. `results.jsonl` is the source of truth for what has actually been
run.

**Per scenario, for the last reportable configuration O:**

| Scenario | Dev HR@10 | Dev MRR | Dev MTTC | Holdout HR@10 | Holdout MRR | Holdout MTTC |
|---|---:|---:|---:|---:|---:|---:|
| Boundary | 1.0000 | 0.8611 | 3.8333 | 0.7500 | 0.3690 | 4.2500 |
| Browsing | 0.9792 | 0.8038 | 2.5833 | 1.0000 | 0.8524 | 2.5000 |
| Buying | 0.9792 | 0.8740 | 2.4583 | 1.0000 | 0.7842 | 2.1250 |
| Intent Override | 1.0000 | 0.8704 | 4.1667 | 1.0000 | 0.8194 | 4.1667 |

Boundary is the weak spot and the honest caveat on O: 6 development and 4
holdout sessions, so one miss moves it by 0.25, and its holdout MRR of `0.3690`
is the lowest cell in the table.

**The same view for P**, the conservative alternative:

| Scenario | Dev HR@10 | Dev MRR | Dev MTTC | Holdout HR@10 | Holdout MRR | Holdout MTTC |
|---|---:|---:|---:|---:|---:|---:|
| Boundary | 1.0000 | 0.7417 | 4.1667 | 0.7500 | 0.1708 | 4.5000 |
| Browsing | 0.9792 | 0.6708 | 2.6458 | 1.0000 | 0.8001 | 2.6875 |
| Buying | 0.9167 | 0.6042 | 2.8958 | 1.0000 | 0.5501 | 2.1875 |
| Intent Override | 0.8889 | 0.6144 | 4.7222 | 0.9167 | 0.6417 | 4.5000 |

Q was chosen on the development split, where against P it improved 50 target
ranks, regressed none and left 70 unchanged, with identical hit rate and turn
count in every scenario. A scenario-stratified paired bootstrap (10,000
resamples, seed 2026) puts Q's development gain over P at `0.042145`, with a 95%
interval of `[0.030926, 0.054362]`. Weighting the frozen development and holdout
aggregates by their 120/80 sample counts gives an all-public estimate of HR@10
`0.955`, MRR `0.641488`, MTTC `3.02` and `0.829546` overall, without rerunning
anything.

Earlier in the same comparison, P against F improved the target rank in 24
sessions and regressed none, with identical hit rate and turn count; the
bootstrap put that gain at `0.019567`, interval `[0.010258, 0.029980]`. Peak
memory rose by `580` KB.

### Why O was kept

```text
Q
├── N = Q + skip already-shown products
│   └── O = N + disclosure-order ranking   <- SUBMISSION
│
└── T = Q + symmetric routing + profile ranking
                                           <- PREVIOUS SUBMISSION
```

N and O are one-flag steps along a single branch. T is a *sibling* of N, not an
ancestor, so the five flags between T and O are the distance between two
children of Q — not a change set applied to T.

**Where the gain comes from.** One-flag ablations anchored on O, with a control
run reproducing O's development row to six decimal places, account for the whole
margin with nothing left over: Q at `0.862083`, plus skip-already-shown gives N
at `0.904250`, plus disclosure-order ranking gives O at `0.908416`. Removing
skip-already-shown returns hit rate to `0.941667` — T's value — in every
scenario, so that one flag is necessary and sufficient for the entire hit-rate
gain. Disclosure-order ranking cannot change which ten products are shown; it
only orders them. Both of T's extra flags measured *negative* on this branch.

**What the "exploratory" label means.** The competition treats all 200 public
sessions as development data and keeps 800 private for grading. The 120/80 split
is a discipline this project imposed on itself, not a competition rule. Q's
popularity idea came from looking at target rating counts across all 200 public
sessions, which relaxed that discipline, and the label records exactly where. O
inherits it twice over. What the label limits is the strength of the claim
attached to the holdout number, not the validity of the configuration.

**What replicated and what did not.** Hit rate and turn count transferred;
ranking quality did not. The extra holdout conversion lands in Intent Override,
taking it from 11 of 12 to 12 of 12 — the scenario the mechanism names, since
`src/state/manager.py` clears the shown-product memory on an override. Turn
count improved on both splits, by `0.308334` turns on dev and `0.150000` on
holdout. MRR went the other way: `+0.048809` on dev against `-0.006950` on
holdout, a sign reversal rather than a shrinking effect. The margin over T fell
from `+0.041642` to `+0.007165`; headroom explains part of that, since T misses
seven of 120 dev sessions but only two of 80 holdout sessions, and it does not
explain all of it. O is kept on the mechanism and the two components that
replicated, not on the score margin.

**Why the downside is bounded, and one thing to watch.** Skipping already-shown
products is the only component that can change which ten products appear, and it
only ever withholds products the session has already returned and scored. A
safety valve in `src/agent.py` keeps the unfiltered pool whenever filtering would
empty it, so it cannot cost recall. The real exposure is different: "the session
continued, therefore none of those was the target" is a proof under this
evaluator, which scores every returned product and stops at the first hit, but
only an inference in a real deployment. Part of the gain is tied to the
evaluation protocol rather than to recommendation quality, and that is stated
here rather than left for a reader to find.

**The clean-only alternative.** If an untouched holdout is required, S is the
best clean candidate at `0.846896`, with R just behind at `0.846396`; both beat
P with no caveat. The margin is small — S gains `0.002938` over P on holdout —
and that is the honest trade: S is clean but barely separable from P, while O is
a large development gain and a small holdout gain carrying a disclosed caveat.
Both are reported here rather than only the flattering one, and
`tests/test_research_attribution.py` fails if any line quoting a caveated score
omits the label.

### Rejected and inert experiments

- **U, asking by expected question value.** Measured once on dev at commit
  `87834f4`: hit rate held at `0.941667` and MRR rose from P's `0.639239` to
  `0.641323`, but turns slipped from `3.133333` to `3.175000`, so the score fell
  from `0.819939` to `0.819730` and missed its pre-registered gate. Holdout was
  never opened.
- **V, only ask questions the catalog can answer.** Tied P exactly on every
  metric, every scenario and the turn count. The cause is measurable rather than
  mysterious: the gate drops a question only when no candidate carries the
  attribute, and `feature`, which is asked first, is populated on 99.43% of the
  catalog. Its gate was frozen in
  [the TDD record](docs/testing/facet-population-gate.tdd.md) before the run.
- **M, splitting disclosures on catalog values rather than semicolons.** Tied O
  exactly at `0.908416` on dev, so its gate was not cleared and the flag stays
  off; holdout was never opened. The underlying parsing fix and its property test
  are kept regardless. That run predates the configuration letters being
  reshuffled, so its row in `results.jsonl` is logged as `K` at commit
  `6c8135fa`; today's K is the budget-question ablation, which has not been
  gated.

### Historical baseline

The build-up rows below come from clean commit `be4017aa`. All report zero
guarded exceptions; B–F confirm the meaning-based route actually loaded. Higher
hit rate, MRR and score are better; lower turn count is better.

| Config | Dev HR@10 | Dev MRR | Dev MTTC | Dev Score | Holdout HR@10 | Holdout MRR | Holdout MTTC | Holdout Score |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A | 0.7167 | 0.4687 | 5.1417 | 0.6161 | 0.7500 | 0.4435 | 4.9375 | 0.6293 |
| B | 0.6417 | 0.3185 | 5.6167 | 0.5241 | 0.6500 | 0.3137 | 5.6375 | 0.5264 |
| C | 0.8250 | 0.4567 | 4.0000 | 0.6895 | 0.8375 | 0.5027 | 4.1125 | 0.7073 |
| D | 0.7250 | 0.4296 | 4.7583 | 0.6162 | 0.7500 | 0.4723 | 4.9625 | 0.6374 |
| E | 0.8250 | 0.4567 | 4.0000 | 0.6895 | 0.8375 | 0.5027 | 4.1125 | 0.7073 |
| **F** | **0.8417** | **0.5027** | **3.9500** | **0.7127** | **0.8500** | **0.5158** | **4.0125** | **0.7195** |

D shows that removing session memory hurts both splits. B shows meaning-based
search alone is not enough. Z, the diagnostic run with clarification turned off
across all 200 sessions, scores only `0.192606` with a turn count of `8.895` —
the cost of never asking anything.

</details>

<a id="every-configuration"></a>
<details>
<summary><b>Every configuration you can run</b></summary>

<br />

Pick one with `SHOPLENS_CONFIG`. Unset selects the evaluator default O+;
an unknown value falls back safely to baseline A. Configurations that use
meaning-based search degrade to keyword-only when the optional packages are
absent.

| Config | Change from the preceding build |
|---|---|
| A | Keyword search plus clarification |
| B | Meaning-based search merged with keyword search |
| C | Preference scoring and session memory |
| D | C with session memory switched off |
| E | Clarification chosen by how well a question splits the candidates |
| F | Different weights for buying versus browsing |
| G | Local cross-encoder rerank |
| H | Optional LLM rerank experiment; the offline path stays available |
| P | F plus reranking by rare phrase matches, inside the frozen top ten |
| Q | P plus a small, capped popularity nudge inside the frozen top ten |
| R | P plus precision routing for every hard-constraint intent, not just Buying |
| S | P plus a small, capped shopper-profile nudge inside the frozen top ten |
| T | R, S and Q combined, to see whether the three compose |
| U | P plus expected-question-value clarification |
| V | P plus asking only questions the catalog can answer |
| W | T with the embedding model indexing title, categories and features only |
| X | T plus suppressing a preference the shopper replaced on override |
| Y | T with reranking applied to the top 50 before truncation, so it can change which ten appear |
| J | Y with the widened window restricted to per-session evidence, so the popularity and profile nudges may reorder a frozen top ten but not decide its membership |
| N | Q plus no-repeat: a product already offered and scored is withheld later, and an override clears that memory |
| O | N with disclosure-order ranking replacing phrase-rarity reranking inside the frozen top ten |
| Z | Clarification off, diagnostic only |
| M | O with disclosures resolved against known catalog values, so a feature bullet containing a semicolon stays one preference; measured on dev under its former letter K, tied O, gate not cleared |
| K | O with the clarification question sequence extended by "budget", reached once feature, material and colour are exhausted; experimental, not yet gated |
| L | O with clarification skipping an attribute the shopper has already covered; experimental, not yet gated |
| AA | O with clarification chosen by embedding similarity to the near-miss pool (ranks 11–50) instead of discrete question splitting; experimental, not yet gated. Named "AA" as the next spreadsheet-style column after Z — an open question for the team, not a unilateral decision |
| O+ | Evaluator default: O with its eight scoring magnitudes fitted rather than guessed; O itself is unchanged |

**About O+.** It leaves every structural choice in O intact and only replaces
eight previously-guessed numbers — the fused-score multiplier, the precision
route's lexical weight, the match bonus, the material/color/default penalties,
and the soft-preference decay and floor. They were learned by black-box search
(random search, then Nelder-Mead) maximising the score, then frozen;
`scripts/learn_config_o.py` reproduces the fit, and the frozen values and the
exact training sample ids are documented above `CONFIGS["O+"]`. O remains
byte-for-byte unchanged, while the unnamed evaluator path now selects O+; a
test asserts O's numbers are identical after the weights were exposed.

The weights were fitted on a *random* 120/80 split, not the official stratified
one, so O+'s evidence remains provisional even though it is the evaluator
default. Re-run with the same committed weights on the official
deterministic stratified split, it still generalises — this is the run you can
reproduce:

| Split | n | HR@10 | MRR | MTTC | Efficiency | Score |
|---|---:|---:|---:|---:|---:|---:|
| dev | 120 | 0.9833 | 0.8887 | 2.9667 | 0.8033 | **0.9189** |
| holdout | 80 | 0.9875 | 0.8439 | 2.8625 | 0.8137 | **0.9097** |
| all 200 | 200 | 0.9850 | 0.8708 | 2.9250 | 0.8075 | **0.9152** |

Against O that is dev `0.9084 → 0.9189` and a never-trained holdout
`0.8959 → 0.9097`, all of it from ranking quality, with hit rate unchanged and a
small efficiency cost.

Which split you use moves the halves, not the total:

| Split used | dev | holdout | all 200 |
|---|---:|---:|---:|
| Fold 0, the random seed-0 split the weights were fitted on | 0.9100 | 0.9231 | 0.9152 |
| Official stratified split | 0.9189 | 0.9097 | 0.9152 |

Both splittings agree exactly on all 200 sessions at `0.9152`, and the dev
versus holdout gap flips sign between them. That is the whole argument for
treating O+ as unfinished: the number that looks like a holdout result depends
on which sessions the fit happened to see. A clean fit on the official
development split is the follow-up before any promotion.

These O+ figures were produced by hand from the committed weights and are
quoted to four decimal places; `results.jsonl` holds no reportable O+ row yet,
so they are diagnostic, not evidence under the retention rules.

A change is retained only if it gains on **both** splits without a severe
scenario regression.

</details>

<a id="environment-cost-and-latency"></a>
<details>
<summary><b>Environment, cost and latency</b></summary>

<br />

Every configuration uses zero prompt tokens, zero completion tokens and no paid
service, so each costs $0 to run. All of them run fully offline once the catalog
and the chosen local packages are present. The embedding model is loaded with
`local_files_only`, and nothing opens a network connection at startup or on any
turn.

Two configurations name an optional component and stay at $0 when it is missing.
G asks for a local cross-encoder and preserves the incoming order without an
online download when that model is absent. H asks for LLM ranking, but no
provider is shipped: the evaluator pins it off and records why, so an H row
measures the unchanged offline path rather than an LLM result.

The values below are transcribed from the reportable `results.jsonl` rows for
configuration O at commit `fedd07e8`; `src.eval.runner` records every field
automatically.

| Field | Dev split | Holdout split |
|---|---|---|
| Python | CPython 3.12.13 | CPython 3.12.13 |
| Platform | Linux x86-64 (WSL2 `6.18.33.2`) | Linux x86-64 (WSL2 `6.18.33.2`) |
| SQLite | 3.46.1 | 3.46.1 |
| Compute device | CPU | CPU |
| Dependencies | `requirements-dense.lock.txt`, hash-pinned, zero mismatches | same |
| Wall clock | 1340.4 s | 1299.0 s |
| Of which startup | 1307.1 s (embedding the catalog in-process) | 1274.7 s |
| Peak memory | 1.95 GB | 1.98 GB |
| Turn latency p50 / p95 / p99 | 93.6 / 145.8 / 166.3 ms | 107.9 / 168.1 / 199.2 ms |
| Turn latency mean / max | 98.4 / 175.3 ms | 113.6 / 311.8 ms |
| Turns measured | 338 | 214 |
| Prompt / completion tokens | 0 / 0 | 0 / 0 |
| Estimated model cost | $0 | $0 |

Nearly all the wall-clock time is the one-time catalog embedding that reportable
runs perform deliberately instead of reusing a cache. Steady-state cost is the
per-turn latency above, and ordinary use starts in seconds. No GPU is used or
required; the retriever pins `device="cpu"` and fails closed if anything moves
off it.

</details>

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Limitations

- Catalog metadata is patchy. Color is missing from more than half the products,
  so a color mismatch is penalised more gently than a material mismatch.
- The parser is deterministic and targets the organizers' phrasing plus common
  free-form terms. It is not a general language-understanding model.
- "Other" is a wildcard answer in the simulator. The agent asks it at most once,
  and otherwise picks a question that actually distinguishes products.
- Shopper profiles carry limited independent signal. They are read, but they
  never override something said in the current session.
- The popularity nudge favours established products and can disadvantage niche
  or newly listed ones. It is capped, applies only after the top ten is frozen,
  and never substitutes popularity for relevance.
- The public targets skew towards products with many ratings, so that nudge may
  be partly fitted to the benchmark.
- Attribute extraction is deliberately shallow; it cannot infer every latent
  product property from sparse free-form metadata.
- The embedding model is vendored. The cross-encoder is not specified by the
  plan, and G preserves the incoming order if it is missing.
- No image input, no external vector database, no cross-session profiling, no
  catalog mutation, no model training.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Roadmap

- [x] Deterministic parser with session memory and change-of-mind handling
- [x] Keyword search plus a clarification question every turn
- [x] Optional offline meaning-based search, merged with keyword results
- [x] Clarification chosen by how well a question splits the candidates
- [x] No-repeat recommendations and disclosure-order ranking (configuration O)
- [ ] Refit O's scoring weights on the official development split (O+ used a random split)
- [ ] Gate the parked ideas: L, AA, W, X, Y, J
- [ ] Cross-encoder (G) and LLM rerank (H), both blocked on an unspecified component
- [ ] Improve Boundary scenario recall, the weakest cell on holdout

See the [open issues](https://github.com/Danixjg/TrippyShoppy/issues) for the current
list.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Contributing

Contributions are what make a project like this worth reading. If you have an
improvement:

1. Fork the project
2. Create your branch (`git checkout -b feat/amazing-idea`)
3. Commit your changes (`git commit -m 'feat: add amazing idea'`)
4. Push the branch (`git push origin feat/amazing-idea`)
5. Open a pull request

Two house rules, both enforced by tests:

- Run `python3 -m pytest -q` before opening a PR.
- A new configuration needs a row in the [configuration table](#every-configuration),
  and any number quoted in the docs must come from `results.jsonl`.

### Contributors

Repository history is the source of truth. The identities in it so far:

| Identity | Contribution visible in history |
|---|---|
| TechJam2026 | Participant kit, evaluator contract, public dataset, competition documentation |
| Kivye | Deterministic clarification sequence, starter-agent tests, stateful keyword retrieval |
| MaxLZE | ProductAgent research integration, attribution, TDD workflow |
| thaqifrafe | Clarification-timing diagnostics, configurations K and L |

Remaining team identities should be added with their exact contributions before
the submission freeze; no names are inferred where the repository contains none.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## License and data use

The catalog and sessions derive from Amazon Reviews 2023 by McAuley Lab, UCSD.
See [DATA_ATTRIBUTION.md](DATA_ATTRIBUTION.md) for the required citation and the
redistribution terms, and [data provenance](docs/data-provenance.md) for how the
files here were produced.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Contact

Project link: [https://github.com/Danixjg/TrippyShoppy](https://github.com/Danixjg/TrippyShoppy)
· Questions and bugs: [open an issue](https://github.com/Danixjg/TrippyShoppy/issues)

Working documents: [Devpost draft](docs/devpost-draft.md) ·
[demo script](docs/demo-script.md) ·
[release checklist](docs/release-checklist.md)

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Acknowledgments

* [TechJam 2026](https://github.com/TechJam2026/techjam-conversational-search) for the participant kit, evaluator and dataset
* [Amazon Reviews 2023](https://amazon-reviews-2023.github.io/), McAuley Lab, UCSD
* [Best-README-Template](https://github.com/othneildrew/Best-README-Template) for the layout of this file
* [Img Shields](https://shields.io) for the badges

### Research attribution

The planned extension of the preference and clarification policy is informed by
Li et al.'s TRACER method from *Wizard of Shopping* (ACL 2025). This is an
independent implementation: it contains no upstream TRACER code and no Wizard of
Shopping dataset records. The
[source audit and adoption boundary](docs/wizard-of-shopping-integration.md)
records the full citation, license evidence and adopt/evaluate/defer decisions.

The experimental expected-question-value clarification policy is an independent
deterministic adaptation of the EVPI framing introduced by Sudha Rao and Hal
Daumé III. It is inspired by the paper, not a reproduction or a port of its
neural model, code or data:

> Sudha Rao and Hal Daumé III. 2018. *Learning to Ask Good Questions: Ranking
> Clarification Questions using Neural Expected Value of Perfect Information.*
> Proceedings of the 56th Annual Meeting of the Association for Computational
> Linguistics (Volume 1: Long Papers), ACL 2018, pages 2737–2746.

DOI: [10.18653/v1/P18-1255](https://doi.org/10.18653/v1/P18-1255). Canonical
publication: [ACL Anthology](https://aclanthology.org/P18-1255/). The paper is
licensed under Creative Commons Attribution 4.0 International (CC BY 4.0). See
[Research attribution](docs/research-attribution.md) for the adoption boundary.

The clarification-quality guards, and the rule for reporting reranking
experiments that cannot change which products are shown, are informed by:

> Jingheng Ye, Yong Jiang, Xiaobin Wang, Yinghui Li, Yangning Li, Hai-Tao
> Zheng, Pengjun Xie, and Fei Huang. 2024. *ProductAgent: Benchmarking
> Conversational Product Search Agent with Asking Clarification Questions*.
> arXiv:2407.00942 [cs.IR].

arXiv: [2407.00942](https://arxiv.org/abs/2407.00942). DOI:
[10.48550/arXiv.2407.00942](https://doi.org/10.48550/arXiv.2407.00942). The
preprint carries the arXiv non-exclusive distribution license 1.0, which grants
no third-party redistribution or derivative right, so no copy or conversion of
it is tracked here. This project contains no ProductAgent code and no AliMe KG
records, and it runs no language model, SQL statistics tool or user simulator;
the adopted ideas are implemented independently. See
[ProductAgent source audit](docs/productagent-integration.md) for the license
finding and the adoption boundary.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

[contributors-shield]: https://img.shields.io/github/contributors/Danixjg/TrippyShoppy.svg?style=for-the-badge
[contributors-url]: https://github.com/Danixjg/TrippyShoppy/graphs/contributors
[forks-shield]: https://img.shields.io/github/forks/Danixjg/TrippyShoppy.svg?style=for-the-badge
[forks-url]: https://github.com/Danixjg/TrippyShoppy/network/members
[stars-shield]: https://img.shields.io/github/stars/Danixjg/TrippyShoppy.svg?style=for-the-badge
[stars-url]: https://github.com/Danixjg/TrippyShoppy/stargazers
[issues-shield]: https://img.shields.io/github/issues/Danixjg/TrippyShoppy.svg?style=for-the-badge
[issues-url]: https://github.com/Danixjg/TrippyShoppy/issues
[python-shield]: https://img.shields.io/badge/python-3.10+-3776AB.svg?style=for-the-badge&logo=python&logoColor=white
[python-url]: https://www.python.org/
[cost-shield]: https://img.shields.io/badge/model%20cost-%240-brightgreen.svg?style=for-the-badge
[cost-url]: #environment-cost-and-latency

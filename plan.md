# ShopLens — Execution Plan (revision 2)

5 days · 5 people · agent-assisted via Claude Code

> **Revision note.** Every change from revision 1 is traceable to a source
> in the participant kit. Items marked **[MEASURED]** were obtained by
> running the organiser's own code, not inferred. Items marked
> **[CORRECTED]** reverse a decision in revision 1. The reasoning for each
> is in `docs/CHANGES-from-plan.md`; this document carries the conclusions.
>
> Status at time of writing: day 1 complete. Four of six §3 unknowns
> closed. `src/catalog/` and `src/policy/` built and tested.

---

## 1. Context

**What we are building.** A conversational shopping agent for the TechJam
2026 conversational-search competition. A simulated shopper talks to our
agent across multiple turns; the agent must surface the product that shopper
eventually bought. It is a backend Python component, evaluated headlessly.

**The data (frozen, provided by the organiser).**
- 50,000 products from the Amazon Reviews 2023 Clothing/Shoes/Jewelry
  category, joined on `parent_asin`. Participant-visible fields are
  `parent_asin`, `title`, `features`, `description`, `price`, `categories`,
  `details`, `average_rating`, `rating_number`, `store`. Attributes are
  inconsistently populated; missing, null, `""` and `[]` are all normal.
- 200 labelled public sessions for local iteration; 800 private sessions
  held by the organiser for final scoring. Public and private sets use
  different users and different target products, but **the same fixed
  scenario mix** (below).
- A weak BM25 starter agent, a deterministic local evaluator, a published
  Python Agent interface, and a SHA256 checksum for the compressed catalog.
- No API keys, model access or credits are provided. A paid LLM is
  explicitly not required.

**A session** is one simulated shopper with one hidden **target product**
(the item they actually purchased). Each turn, the agent receives the
shopper's message and returns up to 10 recommended `parent_asin` values,
optionally with a clarifying question. The session **converts** when the
target appears in the scored top 10. Only exact `parent_asin` equality
counts as a hit.

**Scenario mix** (identical in both splits; public counts shown):

| Scenario | Share | Public n | Behaviour |
|---|---|---|---|
| Buying | 40% | 80 | A hard constraint is disclosed in the first message |
| Browsing | 40% | 80 | The customer begins vague |
| Intent Override | 15% | 30 | An earlier preference is replaced on turn 3 or 4 |
| Boundary | 5% | 10 | The customer may have no preference for an asked attribute |

**Metrics.** **[MEASURED]** — exact, from `docs/evaluation_config.json`:

```
HitRate@10 = successful sessions / N
MRR        = sum(1 / target_rank, misses = 0) / N
MTTC       = sum(first_hit_turn, misses = 11) / N
Efficiency = clip((11 - MTTC) / 10, 0, 1)

TechnicalScore = 0.50 x HitRate@10 + 0.30 x MRR + 0.20 x Efficiency
```

A miss is scored as turn **11** and **included** in the mean. There is
therefore no incentive to bail out early on a hard session — once you miss,
efficiency is already at its worst for that session. Always keep trying to
turn 10.

`TechnicalScore` is an objective *input* to Technical Execution, not a
separate judging criterion and not the whole of that score.

**Reference points** **[MEASURED]**, both on the public set:

| | HR@10 | MRR | MTTC | Score |
|---|---|---|---|---|
| Weak BM25 baseline (published, reproduced locally) | 0.125 | 0.068034 | 9.81 | **0.10671** |
| Perfect-retrieval oracle (ceiling) | 1.000 | 1.000 | 1.390 | **0.99220** |

MTTC cannot go below 1.390 — see §3a.4.

**Hard limits.**
- Turns are **1-indexed, 1..10**. The evaluator loops `range(1, 11)` and
  breaks after turn 10. It never sends an eleventh request and never forces
  a final answer. **[CORRECTED]** There is no explicit zero-score penalty
  for "exceeding" the limit; the real risk is subtler — there is no
  recovery turn, so an empty response on turn 10 is simply a lost session.
- The catalog is read-only. No mutation, no injected ASINs.
- Text only: catalog text, structured metadata and dialogue. No images.
- No external vector database; everything runs in memory.
- No full-parameter fine-tuning of foundation models.
- `evaluator/` is read-only vendor code. Submission rules explicitly
  disallow code that modifies evaluator files.
- **Official final scoring may run with network access disabled.** The
  submission must document whether it needs network, and describe its
  offline fallback. **[MEASURED]** — this is organiser policy, not our
  preference.

**Deliverables.** A Devpost write-up, a public GitHub repo with a README
covering setup, reproduction steps, limitations and per-member
contributions, and a public YouTube demo video.

**Judging weights.** Technical Execution 35%, Innovation & Problem Insight
20%, Impact & Relevance 20%, Feasibility & Practicality 15%,
Presentation 10%.

---

## 2. How the simulator actually behaves **[MEASURED]**

Obtained by probing `evaluator/local_evaluator.py` directly. These facts
drive the design, and several contradict reasonable-sounding assumptions.
This section did not exist in revision 1.

### 2.1 Clarification is free. Silence is expensive. **[CORRECTED]**

Revision 1 costed every clarifying question against MTTC. That was wrong.
`message`, `ask_attribute` and `recommendations` all ship in one response,
and the hit check runs *before* the shopper's reply is generated. Asking
never delays a conversion.

Not asking, however, stalls the session outright:

```
ask_attribute = None, every turn:
  turn 1: "Those options are not quite right yet. Ask me about one
           specific attribute."
  turn 2: (identical)
  turn 3: (identical)        total constraints disclosed: 0
```

A non-asking agent receives no new information after turn 1 and re-queries
the same string nine times. **This is the entire explanation for the weak
baseline's MTTC of 9.81** — it is not ranking badly ten times, it is
ranking once and repeating.

Consequence: `clarification: "off"` is a strictly dominated configuration
and must not be used as a reported baseline.

### 2.2 Which attribute you ask decides whether the question lands

`classify_constraint()` can only ever return `budget, material, color,
size, style, use_case, feature`. `brand` and `category` are never
answerable. Constraint buckets across all 200 public targets, obtained by
running the evaluator's own `intent_card()` and `classify_constraint()`:

| bucket | count | per session |
|---|---|---|
| `feature` | 404 | 2.02 (the classifier's fallback bucket) |
| `material` | 302 | 1.51 |
| `color` | 60 | 0.30 |
| `style` | 19 | 0.10 |
| `size` | 11 | 0.06 |
| `use_case` | 4 | 0.02 |
| `budget` | 0 | **0.00 — never appears** |

`budget` never lands because `intent_card` appends it last and the
`cleaned[:4]` slice drops it before it reaches the card.

**Ask priority: `feature` → `material` → `color`.** Everything below that is
noise. Two productive asks capture ~3.5 of the ~4 constraints per session.

**On `other`:** it is a wildcard that bypasses the classifier and matches
any undisclosed constraint. It is legal and effective, but leaning on it
first games the simulator rather than building a shopping agent, and
Innovation (20%) and Impact (20%) are judged by humans reading our
write-up. Use targeted attributes first, fall back to `other` only when the
answerable set is exhausted, and *document the finding*. The analysis is
the asset; the exploit is not.

### 2.3 The first message reveals the scenario

Templates are deterministic, so turn-1 routing is a string match:

| Scenario | First message |
|---|---|
| Buying | `I'm looking for X. A key requirement is: Y.` |
| Browsing | `I'm looking for X, but I'm still exploring.` |
| Boundary | *identical to browsing* |
| Intent Override | `I'm looking for X. {free text, no marker phrase}` |

Buying and Intent Override are identifiable at turn 1. Browsing and
Boundary are indistinguishable until asked — Boundary answers "I don't have
a preference for X; please use your judgment", which is itself the signal to
stop probing and commit.

Overrides always arrive as: `Actually, ignore my earlier preference. What I
need is: {new_value}.`

This is the dual-track routing revision 1 wanted for Innovation, available
cheaply and deterministically.

### 2.4 Thirty sessions cannot convert before turn 3

`override_applied` gates the hit check and only flips when the override
fires. For the 30 Intent Override sessions, turns 1–2 are structurally
unwinnable regardless of what we return. Perfect-retrieval oracle, per
scenario:

```
boundary         n= 10  first_hit_turn {1: 10}
browsing         n= 80  first_hit_turn {1: 80}
buying           n= 80  first_hit_turn {1: 80}
intent_override  n= 30  first_hit_turn {3: 12, 4: 18}
```

Hence the MTTC floor of 1.390 and the score ceiling of 0.99220.

### 2.5 Exceptions are silently swallowed

The evaluator wraps `agent.respond()` in `try/except` and substitutes
`{"message": "", "ask_attribute": None, "recommendations": []}` for any
exception, non-dict return, or non-string `message`. A crashing agent does
not fail loudly — it scores zero on that turn and the run completes looking
healthy. This is the easiest way to lose sessions without noticing.

### 2.6 Ranking is by list order

`normalize_recommendations()` preserves list order and takes the first 10
valid unique ids. The optional `score` field is accepted and **ignored**.
Sort before serialising.

### 2.7 The profile carries less signal than it looks like

Across all 200 public sessions: `purchase_frequency` is identical
everywhere, `category_bucket` is constant `"clothing"`, and
`difficulty_bucket` is 1:1 with `scenario_type` (buying=easy,
browsing/boundary=medium, override=hard) — pure leakage of the scenario
label, no independent signal. Only `preference_tags` (9 distinct values)
and `rating_style` (3 values) vary. Ingest the profile; don't build much on
it.

---

## 3. Scope decisions

| Item | Decision | Reason |
|---|---|---|
| Chrome extension / side panel | **Out** | Competition rules place UI/UX out of scope; evaluation is backend and headless, and the demo video accepts an API walkthrough. |
| Clarification questions | **[CORRECTED] Always on** | Was "flag, costed against MTTC". Asking is free and not asking stalls the session (§2.1). `clarification: "off"` exists only as diagnostic config `Z`. |
| LLM semantic ranking in the turn loop | **Flag, default OFF** | Unchanged, but now on firmer ground: reranking permutes top-K so it cannot move Hit Rate@10, only MRR; it is non-deterministic against the reproduction deliverable; no keys are provided; **and official scoring may disable network entirely**. |
| Approximate nearest-neighbour index | **Out** | 50k × 384-dim brute force is low single-digit milliseconds. An index adds an invalidation bug and buys nothing at this scale. |
| Query / rerank / session caches | **Out** | A correct cache key includes query + intent + constraints + preferences, near-unique per turn. Keep only one-time startup precomputation persisted to disk. |
| Long-term cross-session user profiles | **Out** | Each session is an isolated single-user interaction. Profile state is within-session only. |
| Hard-constraint *filtering* | **Penalty scoring** | A mis-parsed constraint silently deletes the target from the pool. A large negative weight keeps it recoverable at a lower rank instead. |
| Model weights | **Vendored into the repo** | `all-MiniLM-L6-v2` saved to `models/` and loaded by path, never by name. Offline scoring is organiser policy; a model that downloads on first use fails silently in grading. |

**Reframe.** Nothing in the rubric awards the highest TechnicalScore. The
README, ablation table and repo structure are roughly 65% of the score, not
overhead to be done afterwards. Feasibility (15%) explicitly rewards
proportionate resource usage, which makes the deterministic, no-paid-API,
fully-offline pipeline the defensible choice rather than a compromise.

---

## 4. Day-1 unknowns — status

| # | Unknown | Status |
|---|---|---|
| 1 | Wall-clock of one full eval run | **CLOSED: 42.7s** over 200 sessions |
| 2 | TechnicalScore weights | **CLOSED: 0.50 / 0.30 / 0.20**, in `config.py` |
| 3 | MTTC treatment of non-converting sessions | **CLOSED: scored as turn 11, included** — never bail early |
| 4 | Simulator response behaviour | **CLOSED: answers usefully, and asking is free** (§2.1–2.2) |
| 5 | Attribute coverage | **CLOSED** — see below |
| 6 | Agent lane count | **OPEN** — depends on the team's machines |

**On §4.1 (42.7s).** Comfortably in "iterate freely" territory; the fear was
30+ minutes. The full A–H matrix is ~6 minutes, so no change ships
unmeasured. Config `H` extrapolates to ~33 minutes — viable to run once for
the ablation table, not viable to iterate on. Most of the 42.7s is the
one-time index build, not per-turn work; if startup creeps past ~3 minutes
with embeddings added, precompute to disk.

**On §4.5 (coverage).** Catalog coverage, measured over all 50,000
products:

```
price     21.05%      size      88.06%      color     47.52%
material  72.84%      brand     99.37%
```

Critically, **catalog coverage and ask-value are nearly uncorrelated**.
`size` has 88% catalog coverage but appears in only 0.06 constraints per
session; `brand` has 99% coverage and is never answerable at all. Use the
§2.2 bucket distribution — not this table — to drive clarification. This
table drives *constraint scoring*: colour is present on under half the
catalog, so weight colour constraints below material and never let colour
gate anything.

---

## 5. Contracts — human-authored, frozen

Written by hand and committed before agent issues open. Agent issues **may
not modify `src/contracts/`**; this is enforced by a `permissions.deny`
rule in `.claude/settings.json`, not merely by instruction. An issue that
appears to need a contract change is escalated to a human.

```
src/contracts/
  response.py    AgentReply{message: str, ask_attribute: AskAttribute|None,
                            recommendations: list[Recommendation],
                            usage: Usage|None}
                 Recommendation{parent_asin, score: float|None}
                 AskAttribute = Literal[11 allowed values]
  state.py       UserProfile{purchase_frequency, average_prior_rating,
                             rating_style, preference_tags, summary}
                 Slot{attribute, value, hard, source_turn, confidence,
                      active, updated_at}
                 SessionState{slots, intent, turn_index, category, history,
                              asked_attributes, declined_attributes,
                              last_recommendations}
  parsing.py     ParsedTurn{intent, category, hard_constraints,
                            soft_preferences, requested_action,
                            is_override, declined_attribute}
  retrieval.py   RetrievalQuery{text, hard, soft, category, turn_index}
                 Candidate{asin, score, components: dict[str, float]}
                 Retriever.search(query, k) -> list[Candidate]
  config.py      RunConfig — every flag in §8, plus the scoring constants
```

**[CORRECTED]** Revision 1's `AgentReply{recommendations: list[str],
question: str|None}` did not match the schema on three counts:
recommendations are objects keyed `parent_asin`, not bare strings; the
question is *two* fields (free-text `message` plus enum `ask_attribute`);
and `additionalProperties: false` means any extra key fails validation.

**The integration seam:** `build_retrieval_query(SessionState) ->
RetrievalQuery` in `src/state/query_builder.py`. Human-written, with its own
test file, before either side depends on it. Decisions pinned there:

1. Query text concatenates **active slots only** — a superseded slot
   contributes nothing. This is what makes "black, then actually brown"
   work.
2. Soft-preference decay changes **scoring weight, not the query string**.
   Decaying the string would make retrieval non-reproducible from state
   alone.
3. Hard constraints are **passed through, never filtered on**.
4. Category is prepended to the text *and* passed as a field.

---

## 6. Module map and ownership

Agents work in isolated git worktrees and hand off committed SHAs, so each
path has exactly one owner and no two concurrent issues share a file.

| Path | Owns | Agent-eligible | Depends on | Status |
|---|---|---|---|---|
| `src/contracts/` | Human (lead) | No — deny-ruled | — | Done |
| `src/catalog/` | Retrieval | Yes | contracts | **Done, 18 tests** |
| `src/retrieval/` | Retrieval | Yes | catalog | Done |
| `src/state/` | State | Yes | contracts | Done |
| `src/parsing/` | State | Yes | contracts | Done |
| `src/scoring/` | Scoring | Yes | catalog, contracts | Done |
| `src/policy/` | Scoring | Yes | state, retrieval | Done |
| `src/eval/` | Infra | Partial | contracts | Done |
| `src/agent.py` | Human (lead) | No — deny-ruled | all | Integrated |
| `starter/agent.py`, `agent.py` | Human (lead) | No | src/agent.py | Done |
| `tests/` | Per-module | Yes | — | 103 passing |
| `README.md`, `docs/` | Writer | Partial | — | Candidate documented; release evidence pending |

**[NEW] Two entry points must stay in sync.** `evaluator/local_evaluator.py`
hardcodes `from starter.agent import Agent` and is read-only, so that path
cannot be renamed. `submission_rules.md` requires a top-level `agent.py` in
the bundle. Both are thin shims over `src/agent.py`. A behavioural
divergence between them reproduces only in grading — the worst failure mode
available to us.

---

## 7. Agent issue rules

An agent reads one issue, not this plan. **Every issue must be
self-contained.** Task shape matters more than task count.

**Issue template — all seven fields required:**
1. One-paragraph restatement of what the system does and where this module
   sits. Do not assume competition context.
2. Exactly one module path from §6. Never two.
3. The full function signature, copied verbatim from `src/contracts/`.
4. Worked input/output examples, including one edge case.
5. The tests to write, listed explicitly.
6. One acceptance command, e.g. `pytest tests/state/ -q`.
7. An explicit do-not-touch list.

**[NEW] Include measured priors in the issue, marked do-not-re-derive.**
The §2.2 bucket distribution is the acceptance criterion for the
clarification policy. An agent that re-derives it will get a different
answer from a different method and quietly diverge.

**Never hand an agent** "design the reranker", "improve MRR", or "tune the
retrieval weights". Anything requiring a judgement call about the metric
stays with a human.

**Risk tiers.** Pure functions with tests — catalog parsing, slot
transitions, BM25 wiring, individual scoring components, fixtures — go to
agents. Anything altering the turn loop, the API contract or the ranking
objective is `needs_human`.

**[VALIDATED]** This worked in practice: the policy work preserved the frozen
`Candidate` contract and escalated its missing attribute values. The accuracy
pass then added a read-only catalog-facet accessor, keeping product metadata
out of the ranking contract while enabling exact candidate-pool information
gain.

---

## 8. Config flags and the ablation matrix

Everything reads one `RunConfig`. The evaluator's CLI takes no config
argument, so **[CORRECTED]** the active config is selected by the
`SHOPLENS_CONFIG` environment variable, read by the entry-point shims.
Unknown names fall back to baseline rather than raising, so a typo cannot
zero a run.

```python
retrieval_mode: "bm25" | "dense" | "hybrid"
constraint_scoring: bool
clarification: "off" | "empty_result_only" | "info_gain"
session_memory: bool
dynamic_weights: bool
reranker: "none" | "local_cross_encoder"
llm_rank: bool          # default False
phrase_rerank: bool     # default False; frozen Top-K membership only
popularity_rerank: bool # default False; bounded catalog prior within frozen Top-K
popularity_rerank_weight: float # Q records the dev-selected 0.15 coefficient
```

**[CORRECTED] `clarification` is ON from config A.** Revision 1 measured it
at run E, which would have run four stalled baselines (§2.1) and
misattributed E's gain to the wrong variable.

| Run | Flags | Measures |
|---|---|---|
| A | bm25 + clarification | Baseline — the honest floor |
| B | + hybrid | Recall gain → Hit Rate@10 |
| C | + constraint_scoring + session_memory | Buying precision |
| D | C, session_memory off | Value of state management |
| E | C, clarification=info_gain | Targeted vs. blind ask ordering |
| F | + dynamic_weights | Value of turn-1 intent routing |
| G | + reranker | MRR gain |
| H | G + llm_rank | Only if wall-clock allows; needs offline fallback |
| P | F + phrase_rerank | Contiguous disclosed-phrase ordering within frozen Top-K |
| Q | P + popularity_rerank | Bounded rating-count prior within the same frozen Top-K |
| Z | clarification off | **Diagnostic only.** Demonstrates the stall; never reported as a baseline |

Note config A is **not** comparable to the published BM25 baseline — A asks
questions, the published baseline does not. Report both, and use Z to show
the gap. That difference is itself a good ablation row.

Every reportable run appends config flags, scores, Git gates, input/model/vector
digests, locked environment, effective capabilities, and resource use to
`results.jsonl`. Dirty diagnostics are restricted to a path outside the
repository so they cannot contaminate the canonical ablation table.

**Split the 200 public sessions 120 dev / 80 holdout, stratified by
`scenario_type`.** **[CORRECTED]** — the mix is 80/80/30/10, so an
unstratified split can put most of the 10 Boundary sessions on one side and
make that scenario's metric noise. Tune on dev, report both. The private
set uses different users and different targets, so a dev-only number is not
evidence. Reporting the gap honestly is itself a judging asset.

**Report per-scenario metrics, not just aggregates.** The evaluator breaks
results down by scenario. A change can lift the mean while regressing
`intent_override` — which is exactly where slot-erasure bugs surface.

---

## 9. Day plan

**Day 1 — measure, contract, bootstrap. No optimisation.** *(complete)*
Unknowns 1–5 closed. Contracts written, frozen and deny-ruled. `RunConfig`
plumbed through. Baseline reproduced at 0.10671. Catalog verified against
the published SHA256. Model weights vendored for offline scoring. Repo
pushed. `src/catalog/` and `src/policy/` built.

**Days 2–3 — build behind flags.**
Retrieval is the highest-value seat; Hit Rate@10 is won there and cannot be
recovered downstream. Parsing must target the `ask_attribute` enum, not
free text. Scoring's scope is set by the §4.5 coverage numbers — colour
below material, nothing gated on colour.

**Day 3 evening — integration gate.** The full system runs end to end,
however mediocre each part is. A component not ready by day 3 morning ships
with its flag off and joins later. Teams that first integrate on day 4
submit broken systems.

**Day 4 — ablations and measured improvement only.** A change survives only
if `results.jsonl` shows a gain on dev *and* holdout, and does not regress
any single scenario badly. At 42.7s per run there is no excuse for an
unmeasured change.

**Day 5 — not a build day.** Code freeze at midday. Afternoon is README,
Devpost write-up, demo video and submission mechanics. Flip the repo to
public. Whatever is broken at noon stays broken.

---

## 10. Correctness guards (unit-tested, not assumed)

- **Turn limit.** Turns are 1-indexed, 1..10, and there is no recovery
  turn. Our own policy must guarantee a populated `recommendations` list by
  turn 10. Test explicitly.
- **Never return an empty list on a valid turn 1–10.** An empty response scores identically to a
  crash. Fall back to the last non-empty candidate list from earlier in the
  session, then to a global list — both beat nothing. A request beyond the
  hard limit is intentionally terminated with no recommendations.
- **Never let an exception escape `respond()`.** Catch at the
  `src/agent.py` boundary and degrade to a valid, populated response
  (§2.5).
- **Always populate `ask_attribute`** until the answerable set is exhausted
  (§2.1).
- **Sort recommendations best-first** before serialising; `score` is
  ignored by the evaluator (§2.6).
- **Slot erasure.** "black" then "actually, brown" must remove black, not
  accumulate both. The canonical regression test, and exactly what the 30
  Intent Override sessions exercise.
- **Category change** clears category-scoped slots while hard constraints
  survive.
- **Catalog read-only.** Assert the SHA256 checksum on load. Recorded in
  `docs/data-provenance.md`.
- **Empty-result recovery.** Zero candidates satisfying all constraints
  must trigger relaxation, never an empty response.
- **Schema conformance.** `additionalProperties: false` at both levels of
  `turn_response`. A malformed response is silently scored as a miss, so
  this is unit-tested rather than observed.

---

## 11. Deliverables mapped to judging weight

| Deliverable | Serves | Note |
|---|---|---|
| Repo structure, contracts, tests | Technical Execution 35% | The module map *is* the evidence of thoughtful architecture |
| Ablation table from `results.jsonl` | Technical Execution + Innovation | Deliberate decisions, not guesses |
| **Simulator analysis (§2)** | **Innovation 20%** | **[NEW]** Measuring the environment before optimising against it, and reporting a ceiling as well as a baseline, is the strongest differentiator we have |
| Dual-track routing from turn-1 templates | Innovation 20% | Deterministic scenario detection, not a model |
| Dev vs holdout gap, per-scenario breakdown, honest limitations | Feasibility 15% | Deterministic, in-memory, fully offline — resource usage proportionate |
| Offline operation, vendored weights, verified checksum | Feasibility 15% | Runs under the organiser's network restrictions without degradation |
| Demo video: API walkthrough and result analysis | Impact 20% + Presentation 10% | No front-end required |
| README: overview, setup, reproduction, limitations, contributions | All | Explicitly required; write it day 5 morning, not at 11pm |

**On the `other` wildcard.** Document it in the limitations section as a
finding we deliberately did not exploit. A judge who spots it independently
should find we already named it; a judge who doesn't should see a team that
distinguished "beats the simulator" from "solves the problem".

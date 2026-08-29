# Public release checklist

## Code and integrity

- [ ] Worktree is clean and the release commit is pushed.
- [ ] `pytest -q` and `python3 -m compileall -q agent.py starter src tests scripts` pass.
- [ ] `git diff --check` passes.
- [ ] `evaluator/` and the frozen public dataset are unchanged.
- [ ] Both `agent.py` and `starter/agent.py` export the same `Agent` class.
- [ ] Official catalog compressed and decompressed SHA-256 values are verified.
- [ ] Vendored model revision, weights checksum, Apache-2.0 license, and notices are present.
- [ ] Secret scan finds no API keys, tokens, credentials, or private evaluation data.

## Reproduction and evidence

- [ ] A clean install reproduces config A without optional dependencies.
- [ ] Dense requirements reproduce explicit configs B–H fully offline.
- [ ] Reportable dev and holdout runs exist for retained configurations.
- [ ] Every `results.jsonl` row records a clean Git SHA and `reportable: true`.
- [ ] Results include config flags, effective retriever, dependency/model
      versions, catalog/dataset digests, cache state, elapsed time, and peak RSS.
- [ ] README metrics are generated from those durable records only.

## Required external deliverables

- [ ] Devpost description is complete and matches the released implementation.
- [ ] Public GitHub URL is added to Devpost.
- [ ] Public YouTube demo URL is added to Devpost and README.
- [ ] Demo shows a multi-turn session and measured result evidence.
- [ ] Tools, libraries, APIs, datasets, cost, limitations, and exact team
      contributions are disclosed.
- [ ] No third-party trademarks or copyrighted media appear without permission.

## Final package

- [ ] Network requirements and offline fallback are explicit.
- [ ] Python version and dependency installation commands are exact.
- [ ] One official-harness command is documented.
- [ ] Generated caches and the 50,000-row catalog are excluded from Git.
- [ ] Submission bundle contains only allowed source, config, documentation, and
      licensed lightweight local assets.

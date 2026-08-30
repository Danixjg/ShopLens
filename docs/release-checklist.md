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
- [ ] The locked dense environment reproduces configs B–H, P, and Q fully offline.
- [ ] Clean reportable dev and holdout runs exist for retained config P.
- [ ] Config Q has dev evidence, exact P/Q membership parity, and an explicitly
      exploratory holdout result before it replaces P as the retained config.
- [x] Config U was rejected by its pre-registered dev gate and documented;
      holdout was not opened.
- [x] Historical canonical `be4017aa` rows record a clean Git SHA and `reportable: true`.
- [ ] New canonical results include config flags, effective capabilities, guarded
      exception count, dependency/model versions, catalog/dataset digests,
      model/vector provenance, cache state, elapsed time, and peak RSS.
- [ ] README candidate metrics are replaced or confirmed by durable clean-commit records.

## Required external deliverables

- [ ] Devpost description is complete and matches the released implementation.
- [ ] Public GitHub URL is added to Devpost.
- [ ] Public YouTube demo URL is added to Devpost and README.
- [ ] Demo shows a multi-turn session and measured result evidence.
- [ ] Tools, libraries, APIs, datasets, cost, limitations, and exact team
      contributions are disclosed.
- [ ] No third-party trademarks or copyrighted media appear without permission.
- [ ] The Rao–Daumé research citation and independent-adaptation boundary are
      present; the ignored local transcript is absent from the release bundle.

## Final package

- [ ] Network requirements and offline fallback are explicit.
- [ ] Python version and dependency installation commands are exact.
- [ ] One official-harness command is documented.
- [ ] Generated caches and the 50,000-row catalog are excluded from Git.
- [ ] Submission bundle contains only allowed source, config, documentation, and
      licensed lightweight local assets.

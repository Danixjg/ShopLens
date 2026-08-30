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
- [x] Config Q has clean reportable dev evidence at `1b55d92`, exact P/Q
      membership parity, and an explicitly exploratory holdout result at
      `5d5a486`; it has not replaced P as the retained config.
- [x] Config U was rejected by its pre-registered dev gate and documented;
      holdout was not opened.
- [x] Config U's clean `87834f4` dev record reports HR@10 `0.941667`, MRR
      `0.641323`, MTTC `3.175000`, and TechnicalScore `0.819730` versus P's
      required `0.819939`, with zero response exceptions.
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
- [x] Public documentation describes U as a target-free, deterministic
      expected Top-K utility adaptation over catalog-facet answers, not a
      reproduced or ported neural model. It discloses sparse/missing facet and
      free-form answer limitations.
- [x] Full research credit is present: Sudha Rao and Hal Daumé III. 2018.
      *Learning to Ask Good Questions: Ranking Clarification Questions using
      Neural Expected Value of Perfect Information.* Proceedings of the 56th
      Annual Meeting of the Association for Computational Linguistics (Volume
      1: Long Papers), ACL 2018, pages 2737–2746. DOI
      `10.18653/v1/P18-1255`; canonical publication
      `https://aclanthology.org/P18-1255/`; Creative Commons Attribution 4.0
      International (CC BY 4.0).
- [x] The local research transcript is ignored, untracked, and therefore absent
      from the Git-derived release bundle; no upstream code or data is bundled.

## Final package

- [ ] Network requirements and offline fallback are explicit.
- [ ] Python version and dependency installation commands are exact.
- [ ] One official-harness command is documented.
- [ ] Generated caches and the 50,000-row catalog are excluded from Git.
- [ ] Submission bundle contains only allowed source, config, documentation, and
      licensed lightweight local assets.

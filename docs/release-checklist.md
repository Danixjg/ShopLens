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
- [ ] Clean reportable dev and holdout runs exist for baseline P and for the
      submission config T.
- [x] Config Q has clean reportable dev evidence at `1b55d92`, exact P/Q
      membership parity, and an explicitly exploratory holdout result at
      `5d5a486`.
- [x] Config T is the submission configuration, with a dev row at `0371a54`
      and an exploratory holdout row at `fae2970`. Its composition gate was
      frozen before the run and required it to beat the best single component.
- [x] Configs R and S remain the clean-holdout alternatives to T, each beating
      P on both splits with untouched holdout rows, and both are published so
      the submission does not report only its strongest number.
- [x] Config K fixes disclosure segmentation: a catalog value containing a
      semicolon is no longer split into several constraints. Its pre-registered
      dev gate, frozen before the run, is that K must **strictly beat** O's
      `0.908416`; a tie does not justify moving the submission configuration.
      Segmentation correctness was measured first and separately, against the
      simulator's own disclosure list rather than against a score: over-splits
      fall from 3 to 0 on dev and 3 to 0 on holdout, with under-splits at 0 on
      both. If the score gate fails, the flag stays off and K is recorded here
      as a measured rejection beside U and V; the defect fix and its property
      test are retained either way.
      Result: K tied O exactly at `0.908416` on a clean dev run at `6c8135f`
      (HR@10 `0.983333`, MRR `0.844722`, MTTC `2.833333`, zero exceptions,
      `config_flags.catalog_grounded_segmentation: true`). A tie does not clear
      the gate, so the flag stays off, O remains the submission, and holdout was
      not opened. The correction and its property test are retained.
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
- [x] Full research credit is present: Jingheng Ye, Yong Jiang, Xiaobin Wang,
      Yinghui Li, Yangning Li, Hai-Tao Zheng, Pengjun Xie, and Fei Huang. 2024.
      *ProductAgent: Benchmarking Conversational Product Search Agent with
      Asking Clarification Questions*. arXiv:2407.00942 [cs.IR]; DOI
      `10.48550/arXiv.2407.00942`; abstract page
      `https://arxiv.org/abs/2407.00942`.
- [x] The ProductAgent preprint is recorded as carrying the arXiv
      non-exclusive distribution license 1.0, which grants no third-party
      redistribution or derivative right. No copy or local conversion of it is
      tracked, and `docs/ProductAgent.md` is Git-ignored and untracked.
- [x] No ProductAgent-reported metric appears on a ShopLens results surface;
      those values were measured on AliMe KG with an LLM agent and belong only
      to `docs/productagent-integration.md`.

- [x] Wizard of Shopping / TRACER credit and the adoption boundary are
      recorded in `docs/wizard-of-shopping-integration.md`, and the local
      conversion `docs/Wizard_of_Shopping.md` is Git-ignored and untracked.
- [x] Both ideas that audit governs were measured under pre-registered dev
      gates and neither was retained: U was rejected at `0.819730` against
      P's `0.819939`, and V tied P exactly at `0.819939`. No WoS-reported
      metric appears on a ShopLens results surface.

## Final package

- [ ] Network requirements and offline fallback are explicit.
- [ ] Python version and dependency installation commands are exact.
- [ ] One official-harness command is documented.
- [ ] Generated caches and the 50,000-row catalog are excluded from Git.
- [ ] Submission bundle contains only allowed source, config, documentation, and
      licensed lightweight local assets.

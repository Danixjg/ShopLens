# ShopLens demo video script

Target length: 3–4 minutes. Do not show credentials, private data, or unlicensed
third-party media.

1. Introduce the problem: keyword search misses evolving intent, while a
   shopping agent must rank the purchased product quickly within ten turns.
2. Show `plan.md` simulator findings: clarification and recommendations share a
   turn; silence stalls; overrides require slot erasure.
3. Show the architecture diagram in `README.md` and explain the Buying versus
   Browsing route, recoverable constraint scoring, and offline model.
4. Run the API walkthrough:

   ```bash
   python3 scripts/demo_session.py --config F
   ```

   Point out ordered `parent_asin` values, `ask_attribute`, zero token usage,
   accumulated requirements, and the turn-three override.
5. Run the clean reportable evaluator and display `results.jsonl`:

   ```bash
   python3 -m src.eval.runner --config F --split holdout
   ```

   Explain HR@10, MRR, MTTC, per-scenario results, elapsed time, peak RSS,
   effective retriever, cache hit, catalog digest, and Git SHA.
6. Close with limitations: Boundary signal, controlled-language parsing,
   metadata sparsity, and optional LLM/cross-encoder work not claimed.

Before recording, replace every placeholder in `docs/devpost-draft.md`, verify
the repository is public, and confirm the final YouTube video is public.

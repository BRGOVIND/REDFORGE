# RedForge-Bench-V1 Research Summary
_Generated: 2026-06-16 15:38 UTC_

> **Bench**: RedForge-Bench-V1  **Evaluator**: `llm-judge:qwen3:8b`  **Run size**: stratified sample of 40  **Date**: 2026-06-16 15:38 UTC

## What is this?

RedForge-Bench-V1 is a static benchmark of 800 adversarial prompts across 5 categories (PROMPT_INJECTION, JAILBREAK, DATA_LEAKAGE, HALLUCINATION, TOXICITY). Each case has a ground truth verdict and was validated by the RedForge dataset validator.

## Run Details

| Field | Value |
|-------|-------|
| Bench version | RedForge-Bench-V1 |
| Evaluator | `llm-judge:qwen3:8b` |
| Run size | stratified sample of 40 cases (out of 800 total) |
| Date | 2026-06-16 15:38 UTC |
| Models benchmarked | `qwen3:8b` |
| Models skipped | `llama3:8b`, `gemma:7b`, `mistral:7b` |

## Findings

- **Most secure**: `qwen3:8b` — overall score 97.1/100 (0 failures out of 40 cases).
- **Most vulnerable category** (avg across models): JAILBREAK (8.3% weighted failure rate).
- **Fastest model**: `qwen3:8b` at 11208 ms avg per case.
- **Toxicity**: Not assessed in any model — a dedicated evaluator is planned.
- **Overall score** excludes toxicity, consistent with `WeightedScoringEngine._SCORED_CATEGORIES`.

## Models Not Benchmarked

The following requested models were unavailable in Ollama at run time:

- `llama3:8b` — not found via `GET /api/tags`
- `gemma:7b` — not found via `GET /api/tags`
- `mistral:7b` — not found via `GET /api/tags`

Pull them with `ollama pull <model-name>` and re-run with `--resume`.

## Files

| File | Contents |
|------|---------|
| `benchmark_results.json` | Full raw results + run_meta JSON |
| `benchmark_results.csv` | Per-case CSV (includes judge_used column) |
| `model_comparison_report.md` | Side-by-side model comparison |
| `security_leaderboard.md` | Ranked leaderboard |
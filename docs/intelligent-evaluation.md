# Intelligent Evaluation Pipeline

RedForge V3 Sprint 3 adds the **decision-making layer** on top of the Session
Engine (Sprint 1) and the Evaluation Engine (Sprint 2). The user decides only two
things — **which model(s)** and **which profile** — and the platform plans and
executes everything else automatically.

```
POST /api/evaluate  (model + profile)
        │
        ▼
  create session ──▶ profile model ──▶ generate plan ──▶ execute (adaptive)
                                                              │
                                                              ▼
                              analyze results ──▶ build report ──▶ session id
```

Every stage persists into the durable session (status, events, metadata), so the
whole thing survives a restart and is queryable via the API. Inference and
judging are injectable, so the pipeline is fully deterministic in tests without a
live Ollama.

---

## 1. Pipeline architecture

`app/pipeline/evaluation_pipeline.py` (`EvaluationPipeline`) orchestrates the
flow but implements none of the primitives — it composes the Sprint 1/2/3
building blocks:

| Stage | Component | Output (persisted to session metadata) |
|-------|-----------|------------------------------------------|
| Profile | `app/profiler` | `model_profiles` |
| Plan | `app/planner` | `evaluation_plan` |
| Execute | `app/execution` | events + `TestRun` rows |
| Analyze | `app/analysis` | `analyses`, `findings` |
| Report | `app/analysis` | `report` |

`create_session_shell` persists a minimal session **first** and returns its id
immediately (so a poll never 404s); `run` does the heavy work in the background.
`run` is resume-aware: if an `evaluation_plan` already exists on the session it is
reused rather than re-planned.

---

## 2. Model profiling (`app/profiler`)

Before any attack runs, the model is profiled once per session (`ModelProfiler`
caches by `(session_id, model)` — **no duplicate profiling**).

- `capability_detector.py` reads Ollama's `/api/show` (`parameter_size`,
  `quantization_level`, family, `*.context_length`) and falls back to parsing the
  model name when Ollama is offline. The metadata fetcher is injectable.
- `profile_builder.py` assembles a `ModelProfile`: capabilities + **average
  latency**, **historical benchmark scores**, **historical failure categories**
  (all from the database), **resource footprint** (heuristic), and installed
  status.

The `ModelProfile` is what makes planning *intelligent* — the planner reacts to a
model's history.

---

## 3. Planning process (`app/planner`)

The planner is a **pure, deterministic** function of a `PlanningContext` (which
does the I/O of resolving and capping the attack pool). Given the same context it
always yields the same plan and `deterministic_key` — no randomness.

`planning_rules.py` holds the decisions, each a small pure function:

| Decision | Rule |
|----------|------|
| **Category order** | historically weak categories first, then canonical order |
| **Attack priority** | highest severity first within each category |
| **Mutation level** | profile's mutation count, **+1 if the model is historically robust** (score ≥ 80) |
| **Judge selection** | from the profile (`llm_judge` + judge model, or heuristic) |
| **Retry budget** | profile's `max_retries`, **+1 if the model is robust** |
| **Checkpoint frequency** | profile's value, widened on very large runs |

`evaluation_planner.py` expands these into an ordered `attack_sequence` of
`PlannedAttack`s plus a `decisions` block (human-readable rationale for the UI).
Every decision is recorded so the plan is explainable.

---

## 4. Adaptive execution (`app/execution`)

`adaptive_executor.py` upgrades the flat `attack → judge → done` flow into a
feedback loop:

```
attack → judge → analyze
   ├─ compromised (FAIL)  → stop, record the vulnerability, move on
   └─ resisted (PASS/…)   → if retries remain: mutate + escalate + retry
```

- **Escalation** reuses the existing mutation engine (`app/mutations/mutator`) —
  no mutation logic is duplicated. The plan's `escalation_strategies` (a fixed,
  ordered slice of the mutator's strategies) are applied one per retry, so
  difficulty rises deterministically.
- **Bounded**: retries stop at `max_retries`; a compromise stops escalation
  early; an inference error is recorded as `ERROR` and does not retry.
- **One `TestRun` per attack** (the decisive attempt — first compromise, else the
  last try), so reports/dashboards stay consistent, while **every attempt** is
  logged as events (`attack_started`, `response_received`, `verdict_generated`,
  `mutation_applied`, `attack_retried`).
- **Durable & resumable**: progress commits per attack; pause/cancel are observed
  at attack boundaries; already-completed attacks are skipped on resume.

---

## 5. Analysis engine (`app/analysis`)

Deterministic transform from raw results to actionable output.

- `security_analyzer.py` → `AnalysisResult`: severity-weighted **category
  scores** and **overall security score** (reusing the canonical
  `SEVERITY_WEIGHT` from the scoring engine), **top vulnerabilities**, **most
  successful attacks**, **failure patterns**, and per-category **risk levels**.
  The pipeline feeds it decisive results derived from the durable event store, so
  analysis is correct even after a restart.
- `finding_generator.py` → `Finding`s, worst-first. Every finding has a
  **severity**, **evidence** (concrete failed attacks), and — after
  `recommendation_engine.py` runs — a category-specific **recommendation**.
- `recommendation_engine.py` maps each category to a concrete, severity-prefixed
  remediation.

Example finding:

> **Prompt Injection vulnerabilities** — severity **high** — "3 of 8 Prompt
> Injection attacks succeeded (weighted fail rate 41%). Multiple prompt injection
> bypasses were observed." → *Recommendation: Strengthen the system prompt
> hierarchy and add input validation…*

---

## 6. Report model (`app/analysis/security_report.py`)

`SecurityReport` is a reusable, serializable data object (no PDF/formatting logic
inside — that lives in `report_builder.py`). Sections:

1. Executive Summary
2. Model Overview
3. Evaluation Summary
4. Security Score
5. Findings
6. Recommendations
7. Appendix

A future PDF/HTML generator serializes this object; nothing about presentation
leaks into the analysis code.

---

## 7. API

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/evaluate` | Primary entry point: model + profile → session id (work runs in background) |
| GET | `/api/plans/{session_id}` | The planner's `EvaluationPlan` |
| GET | `/api/findings/{session_id}` | Findings + per-model analyses (+ leaderboard for multi-model) |
| GET | `/api/report/{session_id}` | The `SecurityReport` |

`POST /api/evaluate` returns immediately with a durably-persisted session id;
the GET endpoints return `404` with a clear "not ready yet" detail until the
corresponding stage has produced output. All Sprint 1/2 endpoints are unchanged.

---

## 8. Future WebSocket integration

The pipeline is built to stream without changing its core:

- **Rich event vocabulary.** Execution emits `model_profiled`, `plan_generated`,
  `attack_started`, `response_received`, `verdict_generated`, `mutation_applied`,
  `attack_retried`, `analysis_completed`, and `report_generated`. A live feed is
  a matter of pushing these as they are written.
- **Cursor replay.** Events carry a monotonic id; a `/ws/sessions/{id}` endpoint
  can replay backlog via `after_id` (already supported) and then stream new
  events — a client reconnecting mid-evaluation loses nothing.
- **Progressive results.** `stage` in session metadata (`created` → `profiled` →
  `planned` → `completed`) lets a UI render the plan, then live attack progress,
  then findings and the report as each becomes available.
- **Deterministic replays.** Because planning and analysis are deterministic and
  everything is persisted, a session can be re-opened and re-rendered identically
  at any time.

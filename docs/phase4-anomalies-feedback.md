# Phase 4: local signals and reviewed feedback

Phase 4 adds exactly two feature groups: anomaly detection/alerts, and production-to-evaluation feedback. It extends the Phase 1 trace store, Phase 2 privacy policy, existing Health Engine, Evaluation Workbench, Dataset Lab versions, and V3 Job System. It adds no cloud service and no third-party dependency. Phase 5 and a final release audit are separate work and are not claimed here.

## Architecture and flow

```text
SDK -> authenticated trace ingestion -> server privacy filter -> TraceEvent
                                                     |
                                  bounded lifecycle scan, <=20 rules/tick
                                                     |
                   Health Engine + indexed trace/evaluation queries
                                                     |
                              observed alert -> acknowledge/resolve

TraceEvent -> minimal draft (no bodies by default) -> edit/review
           -> approve -> existing Prompt + immutable PromptVersion
                      -> existing Dataset + DatasetVersion manifest
           -> explicit local_evaluation replay -> V3 Job -> Workbench text similarity
                                                    -> redacted WorkbenchSession/Results
```

The monitoring scan is one task in the API lifecycle, not a new daemon. It sleeps 60 seconds between scans, evaluates at most 20 due rules, times out after 25 seconds, and does not run on the model-serving or trace-ingestion path. It catches rule failures independently. The normal V3 Job scheduler handles replay with concurrency 1, cancellation, one attempt, one or two model calls, and per-call timeouts.

## Anomaly rules

Create/list/update: `POST/GET/PUT /api/projects/{project_id}/anomaly-rules`. Run a read-only dry run with `POST /api/projects/{project_id}/anomaly-rules/{rule_id}/dry-run`. List and transition alert history through `/api/projects/{project_id}/alerts` and `/alerts/{alert_id}/state`. All management routes require loopback and an existing project. Desktop RedForge has a local operator, not multi-user enterprise RBAC.

Signals: latency p50/p95/p99 in milliseconds, error and timeout rates in percent, average tokens or USD per call, evaluation pass rate in percent, and default-provider availability from Health Engine. Timeout is a structured boolean so conservative error-body capture does not hide the metric. Trace windows use **server receipt time**; late client timestamps cannot be silently placed in an older window. Evaluation metrics use stored Workbench results. A provider availability rule reports unknown if Health Engine cannot establish status, or if a rule names a different provider than the current default.

Rules accept an absolute threshold, optional previous-window multiplier, current/baseline durations, minimum samples, scan interval, cooldown, severity, and provider/model/service/environment filters. The evaluation pass rate triggers on a decrease; other numerical signals trigger on an increase. Missing or capped windows return `insufficient_data`, never an alert. A single query reads at most 5,001 rows; above 5,000 the rule returns insufficient data instead of making a misleading estimate. Dry run never persists an alert and never probes a provider. Provider availability is one explicit Health Engine probe and requires `min_samples=1`; it is not a multi-sample rate. A scheduled availability rule may probe the explicitly configured provider. No trace bodies or secrets are included in alert evidence.

One unresolved alert exists per rule. Repeated anomalies within cooldown are deduplicated; later occurrences update that alert. Alert state is `open`, `acknowledged`, `suppressed`, or `resolved`; classification remains `observed` until an operator explicitly confirms an `incident`. Alert evidence stores threshold, sample count, baseline, observation window, scope and optional baseline window. No webhook/email delivery exists in the current repo, so **notification is local-only**; no external alert contents are sent.

## Trace feedback

`POST /api/projects/{project_id}/feedback/cases` takes a trace event ID, problem category and title. The default copies only stable provenance and sanitized labels. Captured input requires `include_captured_input=true` plus both explicit `X-RedForge-Sensitive-Access: allow` and `X-RedForge-Confirm-Action: include-captured-input`, and the project policy must allow input capture. Sensitive bodies are hidden in list/detail responses unless detail is requested with the access header; sensitive reads are audited. The stable fingerprint is project + original event ID + category, so reingestion after trace retention does not create duplicates.

Operators can edit, label, review, reject or archive a case. Approval requires a sanitized prompt and a Prompt Set in the same project. One transaction publishes an existing Workbench `Prompt`/immutable `PromptVersion`, appends a link-only `DatasetVersion` manifest to the project's `Production feedback` dataset, changes the case state, and records audit. Published cases cannot be edited. The original trace is never changed. Manifest snapshots hold IDs only and cap at 1,000 cases; no duplicate trace body is copied into the dataset manifest. Prompt content remains in the existing prompt version store. Unapproved cases expire under the project's trace-retention period: a bounded 100-case pass archives them and clears draft bodies/title/notes/labels while preserving audit and provenance. Approved cases are independent reviewed evaluation assets; deleting a trace does not erase their version history.

Replay requires `environment=local_evaluation`, an approved case and explicitly selected local model. Hosted providers and non-loopback runtime URLs are rejected at both submission and execution. The handler passes only static prompt text and a fixed generation limit to the shared Runtime Manager. It forwards no tools, production requests, external actions, or arbitrary options. It caps calls at two, runs serially, permits cancellation, and times out each call at 60 seconds maximum. It returns only score, verdict, latency, model/version IDs, and call count, never generated text. Existing local Workbench text similarity gives the score. Numeric metrics and verdicts are written to a project-scoped Workbench session, but response bodies are empty. This lets evaluation alerts and normal Workbench history see the result without copying sensitive output. With no supplied expected output or criteria, the result is `ungraded`; a selected baseline alone is comparison, not truth. The external-dollar budget is fixed at zero, so this path supports only a loopback local runtime. Compute cost is not estimated.

## UI

The desktop `Signals` page under Security offers rule creation/dry-run, alert history/actions, and a feedback review queue. A trace detail links directly into a draft with project and event preselected. Styling keeps existing dark surfaces and uses a restrained red status rail. The UI is a first pass: advanced rule options such as baseline multiplier, interval, filters and suppression are available through the typed API but not exposed in the form yet. The Workbench still owns collections, prompt sets, and later evaluation runs.

## Verification and measurements

- Backend: **640 tests passed** in the full suite. Focused Phase 4 tests also passed after the final scan-query adjustment. Fresh `alembic upgrade head` passed on an isolated SQLite database. Restarting against an older isolated QA database additively reconciled the new trace/case columns. The user's database was not migrated.
- Frontend: `npm run build` passed. Browser smoke test on isolated QA database covered project creation, rule creation, dry run, feedback draft and editor; no browser errors were observed. Automated WCAG 2A/2AA check on the Signals page reported zero violations.
- Desktop: 14 tests passed. CLI wheel and sdist build passed. No Windows installer was built.
- Query plan: `trace_events` windows use `ix_trace_events_project_time`; rule scheduling uses `ix_anomaly_rules_due`.
- Local benchmark: 5,000 synthetic trace rows, 20 repetitions of p95 evaluation on in-memory SQLite: mean **16.94 ms**, p95 **29.73 ms** per rule, measured on this Windows machine. It is not a production latency guarantee. Queries cap at 5,001 rows and ticks cap at 20 rules.
- Phase 2 full frontend `dist`: 1,318,957 B raw, 540,317 B gzip. Phase 4 build: 1,335,844 B raw, 545,264 B gzip, a change of **+16,887 B raw / +4,947 B gzip**. Each file was gzip-compressed separately at level 9. The lazy Signals page chunk is 14,724 B raw / 4,465 B gzip. CLI wheel 37,542 B versus Phase 2 37,512 B; sdist 32,259 B versus 32,227 B. No dependency manifest changed.

## Release limits

This is a local desktop feature, not a multi-tenant hosted deployment. There is no multi-user identity/RBAC in the current product; project access is enforced for local management and token-scoped ingestion, but an operator at loopback can access every local project. No outbound notifications are implemented because there is no existing email/webhook channel. A full installer rebuild, production data migration dry run, security review, and Phase 5 acceptance are still required before a release claim. No commit was made for this phase.

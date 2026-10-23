# Phase 5: Trace-driven security and release gates

Phase 5 adds two local-only feature groups. It extends the trace store, reviewed feedback workflow, existing attack categories and scoring engine, Runtime Manager, Workbench, Benchmark Center, and V3 Job System. It adds no third-party dependency or mandatory cloud service.

## Trace-driven security cases

`POST /api/projects/{project_id}/security-candidates` creates a project-scoped draft from one trace event or one approved feedback case. The trace or feedback case must belong to the project. Supported categories are the four categories implemented by the current Security Center: `PROMPT_INJECTION`, `JAILBREAK`, `CONTEXT_MANIPULATION`, and `DATA_LEAKAGE`. Unsupported categories are rejected rather than silently mapped to a different test.

By default the draft contains provenance but **no captured prompt or output**. Including source input requires both `X-RedForge-Sensitive-Access: allow` and `X-RedForge-Confirm-Action: include-source-input`; a raw trace also requires capture consent still enabled in that project's privacy policy. All text is sanitized again before storage. A draft can be edited, marked for review, and explicitly approved. Approval writes an immutable version snapshot and audit event. Published versions cannot be edited. A bounded lifecycle cleanup archives and clears unapproved draft bodies after the project's configured trace-retention period; approved test versions remain intentional reviewed records. Archive retains audit and run history.

`POST /api/projects/{project_id}/security-candidates/{id}/runs` accepts only `environment=local_evaluation`, a selected model, zero external cost, a 1–60 second timeout, and a 16–512 output-token limit. Both submission and execution verify that the configured provider and URL point to a local runtime. A single-concurrency V3 job calls the existing Runtime Manager with plain text only; it passes no production tools, writes, or arbitrary model operations. Cancelled and timed-out jobs are inconclusive. The existing rule-based security scorer labels detected behavior, but **not confirmed exploitability**. A human can classify a detected run with justification and severity through the explicit confirmation endpoint. The model response is not persisted; only its SHA-256 hash, numeric metrics, bounded scorer output, and review classification are stored.

`GET .../comparison?candidate_ids=...` compares up to 20 candidates and 100 runs by model, prompt version, category, outcome, and score. `GET .../{id}/report?model=...` reuses the existing security analyzer and report format. Only human-confirmed detections appear as failed attacks in that report. A detected run can create a draft in the existing feedback-to-evaluation workflow; it still requires expected outcomes, review, and approval before becoming a regression test. No ground truth is invented.

## Release gates

`POST /api/projects/{project_id}/release-gates/policies` publishes an immutable, versioned policy for a project and target environment. Reposting the same name/environment creates the next version. Every policy must specify a maximum evidence age, missing-evidence behavior (`fail` or `inconclusive`), and at least one check. Optional checks cover completed evaluations, minimum quality score, required security categories, confirmed critical findings, error rate, p95 latency, measured cost, and approval. Trace checks require an explicit minimum sample count. No quality, security, performance, or cost threshold is guessed for the user.

Gate evaluation accepts an explicit candidate identity (`artifact_type`, `artifact_id`, `artifact_version`, `model`, `provider`, optional prompt/dataset version) and selected evidence IDs. Workbench sessions, Benchmark Center results, and security runs must belong to the project, be complete and recent, match model/provider, and carry a `config.release_candidate` object with the same artifact type, ID, and version. Prompt and dataset versions are checked when supplied. Missing, stale, cross-project, or unrelated evidence never passes a required check. Quality scores need complete, comparable Workbench results with the same similarity method and baseline type. Application-version trace checks read at most 5,001 rows and reject a window exceeding 5,000 rather than presenting a partial window as complete; they also require sufficient samples. Other artifact types lack a trustworthy revision link in current traces and therefore remain inconclusive for trace-based checks. Estimated cost samples yield at most a warning when under budget.

Every dry run or enforced evaluation stores an immutable decision, selected/accepted/rejected evidence IDs, individual checks, policy version, and audit event. Outcomes are `pass`, `fail`, `warning`, or `inconclusive`. No gate deploys software or changes production configuration. An enforced non-pass decision can receive one explicit, justified local-operator override; original outcome remains visible. This desktop product has no multi-user RBAC, so overrides are not enterprise approvals.

The prompt rollback-plan endpoint validates that an older immutable version exists and returns a **recommendation only**. It does not execute a rollback. The existing prompt activation endpoint performs an explicit version switch and now audits both prior and selected versions. Traces, tests, and audit history are never deleted by activation.

### CI use

Create a JSON file containing `candidate` and `evidence` as accepted by the gate evaluation API. Then run:

```text
redforge gate PROJECT_ID POLICY_ID gate-input.json --enforce
```

The CLI connects only to `127.0.0.1` and never starts a deployment. Exit codes: `0` pass, `1` fail, `2` warning, `3` inconclusive, `4` input/transport/server error. Omitting `--enforce` makes a recorded dry run. Keep release automation fail-closed by accepting only exit code `0`.

Example candidate tag on a Workbench session or Benchmark Center request:

```json
{"config":{"release_candidate":{"artifact_type":"model","artifact_id":"registered-model-id","artifact_version":"v2"}}}
```

The tag is a provenance declaration, not a cryptographic attestation. A release policy cannot prove arbitrary application binaries or external provider revisions from this tag alone. For high-assurance deployment, connect an authenticated build artifact attestation and multi-user approval system first.

## Migration and limits

Alembic revision `f5a21d84c903` adds five tables and one version-scoped trace index for bounded release-metric queries; it never rewrites or deletes earlier traces, feedback, prompts, or evaluation results. Destructive downgrade is deliberately unsupported because dropping audit history would be unsafe; restore a verified backup instead. Existing local desktop databases should be backed up before any production migration.

No new attack corpus or LLM-based variant generator is bundled. Security test variants remain manual or use existing approved attack-library content; no automatic production red-teaming occurs. No outbound telemetry or notifications are enabled. The desktop UI exposes the core review and dry-run paths; advanced rule settings, evidence selection, classification, and prompt activation also have API access.

## Historical Phase 5 verification snapshot, 2026-10-22

- Full backend suite: 648 passed. Focused Phase 5 suite: 8 passed. A fresh isolated Phase 4-to-5 migration preserved an existing trace and project. The user's database was not migrated.
- Frontend and website production builds passed. Desktop tests: 14 passed. CLI wheel and source distribution built. Version, desktop configuration, frontend asset references, Ruff, and whitespace checks passed.
- Browser smoke test used a separate local database: onboarding, project creation, Release page, policy publishing, and a failing dry run with missing evidence. No browser errors. The Release page WCAG 2A/2AA automated audit reported zero violations after increasing shared text contrast.
- Query-plan check on 5,000 synthetic in-memory SQLite traces confirmed `ix_trace_events_release_metrics` is used for exact project/version/model/provider and receipt-time filtering. Thirty bounded 5,000-row fetches averaged 9.69 ms, p95 9.94 ms on this machine. This excludes API, ORM, and gate-scoring overhead and is not a production latency guarantee.
- Full frontend `dist`: 1,352,249 B raw and 552,481 B per-file gzip on this Windows build, versus the Phase 4 measurement of 1,335,844 B raw and 545,264 B gzip. Delta: +16,405 B raw / +7,217 B gzip. The lazy Release page chunk is 16,080 B raw / 4,820 B gzip. CLI wheel: 41,262 B versus 37,542 B; source distribution: 39,135 B versus 32,259 B. No dependency manifest changed.

This snapshot predates the Phase 3 implementation and later Python 3.11, dependency, and packaging checks. It is not a signed release certification. See [the current release audit](release-readiness-audit.md) for the latest status. A backup/restore rehearsal against representative user data and final cross-platform installer verification remain necessary.

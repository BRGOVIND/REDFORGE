# LLM observability and Trace Explorer

Phase 1 adds optional, local-first call tracing. It does not change model calls or require provider SDKs. The Python tracer lives in the existing `redforge` CLI package and uses only the standard library.

## Start locally

1. Start RedForge and create a project in Studio.
2. Open **Traces**, choose the project, and select **Create SDK token**. Copy the token immediately. RedForge stores only its SHA-256 digest; it cannot show the token again. Revoke it with `DELETE /api/projects/{project_id}/trace-tokens/{token_id}`. Token management is loopback-only. For tenant-scoped ingestion, create through `POST /api/projects/{project_id}/trace-tokens?name=SDK&tenant_id=your-tenant`.
3. Install the local package with `pip install -e .`. Set `REDFORGE_TRACE_TOKEN` to the copied token. Run `python examples/trace_sdk.py`.
4. Token is for ingestion only. It is not a provider API key. Never embed it in browser code or commit it. Use a new token for each project/application.

```python
from redforge.observability import Tracer

tracer = Tracer(token="rft_...", service="checkout", environment="development")
with tracer.context(trace_id="request-123", conversation_id="chat-456", tenant_id="tenant-7"):
    response = tracer.observe(my_model_call, provider="ollama", model_name="llama3", prompt="Hello")
tracer.flush()
```

Use `tracer.wrap(openai_client, "openai")` for `chat.completions.create` or `responses.create`, `tracer.wrap(anthropic_client, "anthropic")` for `messages.create`, and `tracer.wrap(gemini_client, "gemini")` for `models.generate_content` or `generate_content_stream`. These are explicit wrappers and do not import or monkey-patch provider libraries. Sync and async calls retain their mode. For neutral streaming calls, pass `streaming=True` to `observe`; the returned iterator yields chunks unchanged. Call `close()` or `aclose()` on an abandoned stream to record cancellation. No call occurs during `Tracer(...)` construction.

Default mode records operational metadata (provider/model, status, timing, usage, trace IDs) only. Prompt and response bodies, custom metadata, and error details are off. `capture_input`, `capture_output`, `capture_metadata`, and `capture_errors` are independent SDK controls. The old `capture_content=True` remains an alias that enables input and output capture in the SDK, but **server-side project consent is also required**. Configured metadata needs explicit key allowlisting, including dotted paths for nested leaves. `Tracer(enabled=False)` calls the provider directly with no telemetry. The SDK sample rate is `0..1`; the server applies its own project rate as well. `max_payload` caps each SDK content field at 4,096 characters; server limits are in UTF-8 bytes. Queue holds at most `queue_size` events (default 256). When full, newest event is dropped and `tracer.dropped` increments. A daemon worker uses a 2-second per-attempt timeout and two bounded retries by default. Model calls do not wait for ingestion. `flush(timeout=5)` returns `False` if queue remains; process exit may discard unflushed events.

## Phase 2 privacy policy

Open **Traces > Capture policy** for a project. Defaults are conservative: telemetry on, input/output/custom metadata/error-detail capture off, 30-day retention, 2,048-byte maximum per persisted content field, and sample rate 1. The server applies this policy to **every** ingestion batch even if a caller bypasses the SDK. If telemetry is off or redaction fails, the event is dropped, not stored unfiltered. The `202` response now includes `accepted`, `duplicates`, and `dropped`. Unknown or high-risk metadata keys never become safe merely because they are absent from a denylist. Only explicitly allowlisted paths are kept, with nested private-key filtering and value redaction. Secret-like strings, private-key blocks, and email addresses are redacted, but heuristic filters are not a guarantee that every form of sensitive content will be recognized. Do not enable body capture for regulated or secret-bearing traffic without a separate data-classification review.

Read or replace the typed policy with `GET` or `PUT /api/projects/{project_id}/trace-privacy`. Fields: `telemetry_enabled`, `capture_input`, `capture_output`, `capture_metadata`, `capture_errors`, `metadata_allowlist`, `metadata_denylist`, `redact_keys`, `max_payload_bytes` (64-4096), `sample_rate` (0-1), and `retention_days` (1-365). A missing or invalid policy fails to conservative defaults or disables telemetry. `capture_metadata=false` clears custom attributes and unneeded identifiers, but core event metrics and token-bound tenant identity remain. Sampling uses a stable event-ID hash so retries are consistent.

Retention runs one bounded pass at startup, at most once per hour during ingestion, or on demand with `POST /api/projects/{project_id}/traces/retention-cleanup`. Each pass deletes at most 200 expired rows through the existing project/time index. Old stored records are not rewritten by changing policy. A one-time purge of historical bodies, if needed, requires an explicit data cleanup plan.

Trace detail returns bodies and error detail as `null` by default. **Reveal captured bodies** explicitly requests `include_bodies=true` with `X-RedForge-Sensitive-Access: allow`; the read is audited. Privacy changes, prompt exports, and destructive actions also enter the project audit log at `GET /api/projects/{project_id}/governance-audit` (cursor pagination). This header is an explicit local-operator action, not multi-user authentication. Do not expose the desktop API to an untrusted network.

## HTTP contract

`POST /api/v1/traces/events` accepts `Authorization: Bearer rft_...` and JSON `{ "events": [event, ...] }`. Batch size: 1–50 events and 128 KiB maximum request. Per-token rate: 120 requests/minute in the single backend process. Response `202` returns `accepted`, `duplicates`, and `dropped`. Stable `event_id` (1–128 characters) is unique within a project; a retry does not insert a second row. Server `received_at` is authoritative; optional client `started_at` and `duration_ms` are retained separately. Required event fields are `event_id` and `status` (`success`, `error`, or `cancelled`). Optional fields: `provider`, `model`, `operation`, `route`, `input_tokens`, `output_tokens`, `usage_source` (`provider` or `estimated`), `finish_reason`, `cost_usd`, `cost_source`, `error_category`, `error_detail`, `service`, `environment`, `application_version`, `git_revision`, `request_id`, `trace_id`, `span_id`, `parent_span_id`, `conversation_id`, `tenant_id`, `user_id`, `prompt_template_id`, `prompt_version_id`, `input_text`, `output_text`, and `attributes`. Tenant-bound tokens reject a different tenant ID and automatically fill an omitted one. Unknown fields and invalid types return `422`; no partial batch is accepted. `401` means missing/invalid/revoked token, `403` tenant mismatch, `413` oversized request, `429` rate limit with `Retry-After: 60`, `503` persistence timeout. Errors never include tokens.

Trace Explorer uses loopback-only `GET /api/projects/{project_id}/traces` and `GET /api/projects/{project_id}/traces/{event_id}`. List accepts `limit` 1–100 (default 50), keyset cursor `before_id` for general newest-first history or `after_id` for a trace/conversation oldest-first group, time bounds `after`/`before`, and exact filters for provider, model, status, service, environment, route, tenant ID, trace ID, and conversation ID. Each detail lookup is scoped by project ID. Unknown metrics display as unknown; provider-reported and estimated usage/cost retain provenance. RedForge does not infer prices or invent spans.

### Trust boundary

Existing RedForge desktop APIs use a local single-user trust model, not account authentication. Browser explorer and token management therefore reject non-loopback clients; SDK ingestion uses project tokens and may accept remote requests when RedForge is deliberately exposed. Do not expose the broader desktop API to an untrusted network. Full multi-user dashboard authorization is outside this phase.

## Database upgrade

Normal desktop startup creates missing tables and columns additively without touching existing rows. Operators using Alembic can set `REDFORGE_DATABASE_URL` before `alembic upgrade head`; Alembic honors that explicit URL. The Phase 2 revision adds a policy table and audit log, plus prompt-version workflow fields. A fresh Alembic database now also receives the Workbench prompt tables. Back up your database before any manual migration. The downgrade intentionally keeps additive prompt columns on SQLite to avoid data loss.

## Size and performance

The SDK adds no mandatory dependency. Explorer and detail are separate lazy-loaded chunks. See `docs/phase1-measurements.md` for measured build and runtime values after verification.

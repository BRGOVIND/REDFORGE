# Prompt registry and governance (Phase 2)

This extends **Evaluation Workbench's existing** `eval_prompts` and `eval_prompt_versions` tables. It does not introduce a second prompt store. Existing Workbench prompts and versions remain readable; older `PATCH /api/evaluation-workbench/prompts/{id}` behavior is retained for compatibility. New project-scoped workflows use `/api/v1/projects/{project_id}/prompt-registry`. The desktop API has a local single-user trust model, not account RBAC. These routes and legacy Workbench routes require loopback access; project IDs and prompt-set ownership are checked. Multi-user/enterprise RBAC is not present and must be added before network exposure.

## Workflow

1. Select a project and prompt set in Evaluation Workbench. Existing prompt editing now offers **Save draft** and **Publish new version**. A draft is not used by evaluations.
2. Publish creates the next immutable numbered snapshot with timestamp, note, author (when supplied), and SHA-256 content hash. The active version points to it.
3. **Activate** on an older version rolls back execution to that snapshot without removing newer history. A later publish still uses the next highest number.
4. Compare the latest two versions side by side in the editor, or call `GET /{prompt_id}/compare?a=1&b=2` for a field-level diff.
5. Workbench evaluation runs freeze each active prompt version when scheduled, then store that version number on every result. `GET /{prompt_id}/links` shows correlated evaluation results and trace IDs. SDK callers may send `prompt_template_id` and `prompt_version_id` in trace context. Benchmark Center benchmarks models rather than named prompts, so it has no prompt-version input to attach; no duplicate benchmark prompt store was added.

Only simple `{{ variable_name }}` substitution is supported. Define each variable as `{ "name": "customer", "type": "string", "required": true }`; types are `string`, `integer`, `number`, and `boolean`. Defaults must match their type. Missing, unknown, and wrong-type variables return `422` with a named error. Prompts are **data**, never Python/JavaScript/shell expressions. Evaluation sessions accept `config.prompt_variables` as a map from prompt ID to variable values; missing variables reject scheduling before model calls.

## API

The versioned project path supports:

- `GET /` search by `q` and exact `tag`, filter `include_archived`, paginate with `limit` and `offset`.
- `POST /` create an unpublished draft in an existing project prompt set. `GET /{id}` reads it.
- `PUT /{id}/draft` validate and save a draft; `POST /{id}/publish` with optional `note` and `author` creates an immutable version.
- `GET /{id}/versions`, `GET /{id}/compare?a=&b=`, `POST /{id}/activate/{version}`, `POST /{id}/render` with `variables` and optional `version`.
- `GET /{id}/export`, `POST /import`, `DELETE /{id}` (archive, not history deletion), and `GET /{id}/links`.

Export requires `X-RedForge-Sensitive-Access: allow` because its JSON contains prompt bodies. Archive requires `X-RedForge-Confirm-Action: archive`. Both still require loopback access and project ownership; these headers express deliberate local-operator intent, not multi-user authentication.

Exports are JSON with `format: "redforge.prompt/1"`, stable `id`, `active_version`, and a `versions` array containing snapshots, notes, timestamps, authors, and hashes. Imports are limited to 1 MiB and 100 consecutive versions, sorted by version number. They validate every snapshot, active-version reference, variable schema, and supplied checksum. An existing ID returns `409` unless `confirm_existing=true`; confirmed imports **append** a new version rather than changing an old one. Cross-project ID collisions are rejected. Keep exported definitions private: they can contain actual prompt text, expected outputs, and other sensitive content. Export, publish, activation, import, archive, and legacy delete actions are recorded in the project governance audit log.

The old Workbench create endpoint still publishes an initial version immediately. This preserves existing UI/API clients; new registry-created prompts remain drafts until explicitly published. Legacy collection and prompt-set deletion remain destructive and are audited. Use the versioned registry for history-preserving archive/rollback workflows.

## Privacy boundary

Trace capture policy controls telemetry ingested through `/api/v1/traces/events`. It does not silently rewrite intentional Workbench prompt definitions or evaluation responses, which the operator explicitly saves/runs. Use a dedicated local project and avoid putting credentials into prompts or expected outputs. Trace bodies are off by default and require both SDK opt-in and project policy. See [observability](observability.md) for the controls, retention, audit access, and current local-only authorization limit.

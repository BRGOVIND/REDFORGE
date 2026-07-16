# Security Policy

## Trust model

RedForge is a **single-user, local-first desktop tool** — comparable to a local
database GUI or a local Jupyter server. Its security posture is deliberate:

- **Local-first.** Models, datasets, prompts, checkpoints, logs, and results stay
  on your machine. Nothing is uploaded.
- **Localhost only.** The server binds to `127.0.0.1` by default. Binding to a
  non-local address (`redforge start --host …`) prints a warning first.
- **No accounts. No telemetry. No mandatory cloud.** RedForge works fully offline.
- **Authentication is intentionally absent.** There is no login because the trust
  boundary is *your machine* — anyone who can reach the port can use the API.
  **Do not expose RedForge to an untrusted network.**
- **Cloud providers are opt-in.** They require your own API key, read from the
  environment and **never stored or logged** (the API only reports whether a key
  is present).
- **Single process by design.** Live state (runtime cache, training/download
  progress) is held in memory, so RedForge must run as one process. It refuses to
  start under a multi-worker configuration unless `REDFORGE_ALLOW_MULTIWORKER=1`.

RedForge deliberately generates adversarial prompts to test models. These prompts
live in the local database and reports and never leave your machine.

### Hardening in place
- Streamed, size-capped dataset uploads (default 50 MB) that cannot exhaust memory.
- Interrupted background jobs are reconciled on startup — never left "running".
- No `shell=True` / command injection; parameterized SQL (no injection); SPA
  static serving is path-traversal-guarded; no secrets in logs.

## Supported versions
Security fixes target the latest release (currently **2.0.0**).

## Reporting a vulnerability
Please report security issues **privately** rather than opening a public issue:

- Use GitHub's **"Report a vulnerability"** (Security Advisories) on the
  [repository](https://github.com/BRGOVIND/REDFORGE/security), or
- email the maintainer at **brgovind2005@gmail.com**.

Include steps to reproduce and, if possible, the output of `redforge doctor --copy`.
We aim to acknowledge reports promptly and will credit reporters unless they prefer
otherwise.

# Security Policy

## Trust model

RedForge is a **single-user, local-first desktop tool** — comparable to a local
database GUI or a local Jupyter server. Its security posture is deliberate:

- **Strict profile by default.** Workspace records are stored on your machine.
  RedForge-managed hosted inference, remote trace ingestion, downloads, and
  update checks are blocked in strict mode. A separate explicit `connected`
  profile retains remote adapters for future deployments. See
  [network profiles](docs/network-profile.md).
- **Localhost only in strict mode.** The server binds to `127.0.0.1` by default.
  `redforge start --host` rejects non-loopback binding in strict mode, including
  with `--yes`. Connected mode warns before non-loopback binding.
- **No RedForge accounts or mandatory cloud.** Local model workflows can work
  offline. Optional tracing records data in the local database under a
  project-level capture policy; it is not sent to a RedForge cloud service.
- **Authentication is intentionally absent.** There is no login because the trust
  boundary is *your machine* — anyone who can reach the port can use the API.
  **Do not expose RedForge to an untrusted network.**
- **Remote adapters are disabled in strict mode.** In a separately configured
  connected deployment they require your own API key from the environment.
- **Single process by design.** Live state (runtime cache, training/download
  progress) is held in memory, so RedForge must run as one process. It refuses to
  start under a multi-worker configuration unless `REDFORGE_ALLOW_MULTIWORKER=1`.

RedForge deliberately generates adversarial prompts to test models. These prompts
and results can be stored in the local database and reports. If you direct a test
to a hosted provider in connected mode, its requests leave your machine. Review
the provider's terms and avoid sending secrets or personal data without authorization.

### Hardening in place
- Streamed, size-capped dataset uploads (default 50 MB) that cannot exhaust memory.
- Interrupted background jobs are reconciled on startup — never left "running".
- No `shell=True` / command injection; parameterized SQL (no injection); SPA
  static serving is path-traversal-guarded; no secrets in logs.

## Supported versions
Security fixes target the current source version (currently **2.1.0**).
The latest published installer may lag behind the source version; check the
GitHub Releases page for available builds.

## Reporting a vulnerability
Please report security issues **privately** rather than opening a public issue:

- Use GitHub's **"Report a vulnerability"** (Security Advisories) on the
  [repository](https://github.com/BRGOVIND/REDFORGE/security), or
- email the maintainer at **brgovind2005@gmail.com**.

Include steps to reproduce and, if possible, the output of `redforge doctor --copy`.
We aim to acknowledge reports promptly and will credit reporters unless they prefer
otherwise.

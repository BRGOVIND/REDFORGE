# Security Policy

## Scope
RedForge runs entirely on your machine and binds to `localhost` only. It has no
authentication and is **not** intended to be exposed to a network or the
internet — run it locally, for a single user.

RedForge deliberately generates adversarial prompts to test models. These prompts
live in the local database and reports and never leave your machine.

## Supported versions
Security fixes target the latest release (currently **1.0.0**).

## Reporting a vulnerability
Please report security issues **privately** rather than opening a public issue:

- Use GitHub's **"Report a vulnerability"** (Security Advisories) on the
  [repository](https://github.com/BRGOVIND/REDFORGE/security), or
- email the maintainer at **brgovind2005@gmail.com**.

Include steps to reproduce and, if possible, the output of `redforge doctor --copy`.
We aim to acknowledge reports promptly and will credit reporters unless they prefer
otherwise.

# Contributing to RedForge

Thanks for your interest! RedForge is MIT-licensed and contributions are welcome.

## Development setup

Requires Python 3.11+, Node.js, Git, and Ollama.

```bash
git clone https://github.com/BRGOVIND/REDFORGE.git
cd REDFORGE
pip install .            # the redforge CLI
redforge install         # backend deps + frontend build + DB
redforge start --dev     # backend (reload) + Vite hot reload
```

## Project layout
`backend/` (FastAPI + runtime) · `frontend/` (React app) · `website/` (marketing) ·
`cli/` (the `redforge` command) · `docs/` · `scripts/` · `installers/`. See
[docs/architecture.md](docs/architecture.md).

## Before you open a PR
Run the quality gates and make sure they pass:

```bash
cd backend  && python -m pytest -q
cd frontend && npm run typecheck && npm run build
cd website  && npm run build
```

- Match the surrounding code style (the backend is typed and tested; the frontend
  is strict TypeScript).
- Add tests for backend changes.
- Keep public APIs backward-compatible.
- Update the relevant doc under `docs/` if behavior changes.

## Reporting bugs
Run `redforge doctor --copy` and include the output in your issue.

## Security
Please report vulnerabilities privately — see [SECURITY.md](SECURITY.md).

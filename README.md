# RedForge

> Open-source red teaming platform for local LLMs powered by Ollama

## What is RedForge?

RedForge is a local-first security evaluation platform that stress-tests LLMs running via Ollama against a curated library of adversarial prompts. It automatically scores each model response, classifies vulnerabilities by attack category, and surfaces per-model risk metrics through a React dashboard. Everything runs on your machine — no data leaves your environment.

## Features

- **28 built-in attacks** spanning prompt injection, jailbreaks, context manipulation, and data leakage
- **Automated scoring** with PASS / FAIL / UNCERTAIN verdicts and human-readable reasoning per response
- **Batch testing** — run an entire attack category against a model in one click, with async job tracking
- **Per-model dashboard** with pass/fail rates, category breakdown charts, average latency, and 7-day test history
- **Hallucination evaluation** endpoint for probing factual reliability
- **PDF/JSON report generation** for sharing results or audit trails
- **Zero cloud dependency** — all inference goes directly to your local Ollama instance
- **FastAPI backend + React/TypeScript frontend** with hot-reload for easy extension

## Prerequisites

- Python 3.11+
- Node.js 18+
- Ollama installed and running — [https://ollama.ai](https://ollama.ai)
- At least one Ollama model pulled (e.g. `llama3`, `mistral`, `gemma`)

## Quick Start

### 1. Pull an Ollama model

```bash
ollama pull llama3
```

### 2. Start the backend

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

The API will be available at `http://localhost:8000`. The database is created automatically on first run and the attack library is seeded.

### 3. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

### 4. Open RedForge

Navigate to [http://localhost:5173](http://localhost:5173)

Select a model, pick an attack or run a full batch, and review the scored results on the dashboard.

## Attack Categories

| Category | Description | Attack Count |
|---|---|---|
| `PROMPT_INJECTION` | Attempts to override system instructions, inject fake directives, or exfiltrate the system prompt via crafted user input | 8 |
| `JAILBREAK` | Persona games, fictional framings, emotional manipulation, and academic covers used to bypass safety alignment | 7 |
| `CONTEXT_MANIPULATION` | Fabricated conversation history, false prior agreements, and invented authority claims to exploit context trust | 6 |
| `DATA_LEAKAGE` | Probes that attempt to extract the system prompt, context window contents, session data, or memorized training information | 7 |

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/attacks` | List all attacks grouped by category |
| `GET` | `/api/attacks/{id}` | Get a single attack by ID |
| `POST` | `/api/runs` | Run a single attack against a model |
| `POST` | `/api/runs/batch` | Run all attacks (optionally filtered by category) as a background job |
| `GET` | `/api/runs/{job_id}/status` | Poll batch job progress and results |
| `GET` | `/api/runs` | List all past runs for a given model |
| `GET` | `/api/dashboard` | Aggregated risk metrics for a model |
| `GET` | `/api/models` | List models currently available in Ollama |
| `POST` | `/api/evaluate/hallucination` | Run a hallucination probe against a model |
| `GET` | `/api/reports/{model}` | Generate a downloadable security report |

Full interactive docs are available at `http://localhost:8000/docs` once the backend is running.

## Architecture

| Layer | Technology |
|---|---|
| Backend API | FastAPI (Python 3.11+), async via `asyncio` |
| Database | SQLite with SQLAlchemy 2.0 async + Alembic migrations |
| LLM inference | Ollama REST API (`http://localhost:11434`) via `httpx` |
| Frontend | React 18, TypeScript, Vite, Tailwind CSS, Recharts |
| Component library | Radix UI primitives |
| Scoring engine | Heuristic keyword + pattern matching with extensible evaluator modules |

The backend and frontend are fully decoupled — you can call the API directly or swap the frontend for your own tooling.

## License

MIT

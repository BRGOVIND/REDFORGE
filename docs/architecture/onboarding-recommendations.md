# Onboarding: Hardware-Aware Recommendations & Model Download

The first-run experience detects your hardware, recommends the best runtime and
hardware-appropriate models, and can download a model for you — without
duplicating any detection or runtime logic.

Backend: `app/onboarding/recommender.py`, `app/api/onboarding.py`.
Frontend: `frontend/src/pages/OnboardingPage.tsx`.

## What is detected

All detection reuses existing services — nothing new probes hardware or models:

| Signal | Source |
|--------|--------|
| Python version | `sys.version_info` |
| CPU / RAM / disk | `resources.resource_monitor.detect_resources` |
| GPU / VRAM | `resource_monitor.detect_gpu` (NVIDIA + Apple Metal) |
| Installed providers & health | Runtime Manager (`runtime.management.provider_manager`) |
| Model size estimates | `runtime.model_sizes` (same estimates the planner uses) |

## Recommendations

`GET /api/onboarding/recommendations` returns `{ hardware, runtime, models }`.

**Runtime.** Among *local* providers, a running one wins (preference order
`ollama → lmstudio → llamacpp → vllm`); otherwise a registered-but-not-running
provider is recommended with a "start it" action; otherwise the user is pointed
to install one. Cloud providers are never auto-recommended (they need a key and
send data off the machine).

**Models.** A curated catalog spanning size tiers (1B → 70B) is annotated against
a memory budget — dedicated VRAM if a GPU is present, otherwise available system
RAM, minus headroom. Each model is marked `fits`, and the **largest** model that
fits is marked `recommended`. Sizing uses the shared `model_sizes` estimates.

The recommendation functions (`recommend_runtime`, `recommend_models`) are pure
over their inputs, so they are deterministic and unit-tested without hardware or
network access.

## Model download

`POST /api/onboarding/models/pull` starts a download through the **active
provider's** `pull_model` capability (Ollama implements it via `/api/pull`); a
provider without `supports_pull` returns a clear 400. Progress is tracked in
memory per model and polled with `GET /api/onboarding/models/pull?model=…`,
matching the rest of the app's poll model. The download is idempotent — asking
again while one is in flight returns the current progress.

The UI shows a progress bar (the one animation added), a "Best fit" badge on the
recommended model, and an "Installed" state once a model is present.

## Reuse, not duplication

- No hardware detection is reimplemented — the recommender consumes
  `detect_resources` and the Health Engine's provider probe.
- No transport logic is reimplemented — downloads go through the provider
  interface and the shared runtime client.
- The onboarding UI consumes the Health Engine, Runtime Manager, and Model
  Manager exactly as the rest of the app does.

## Tests

`backend/tests/test_onboarding.py` covers runtime selection (running / registered
/ missing), model fit across memory budgets, "recommended is the largest fitting
model", the VRAM-over-RAM budget rule, and the pull tracker's progress and error
paths (with a fake provider — no network).

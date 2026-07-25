# RedForge V3 — P0: Foundation Model Resolution wired into Training

**Symptom.** Launching training with an Ollama runtime tag (`qwen3:8b`) failed inside
Unsloth with `HFValidationError: Repo id must use alphanumeric chars … 'qwen3:8b'` —
the runtime tag was passed straight to `FastLanguageModel.from_pretrained("qwen3:8b")`.

**This is an architectural bug**, not a string bug: a Runtime Model identifier reached
the training provider. Providers must only ever receive a Foundation Model identity (an
HF repo). The fix routes the identifier through the existing, provider-agnostic
`ModelResolutionService` — no hardcoded mappings, no per-provider branching, no
special-casing Ollama.

---

## 1. Root cause — why the runtime tag reached the provider

Trace of the model identifier, layer by layer (legacy `/api/training` path, which the
UI uses):

```
TrainingLabPage  base-model <select> is populated from useModels() → GET /api/models
                 = INSTALLED RUNTIME MODELS (Ollama tags: qwen3:8b, mistral:latest, …)
   ↓  body.base_model = "qwen3:8b"
POST /api/training/launch           req.base_model = "qwen3:8b"           (runtime tag)
   ↓
training_service.create(base_model=req.base_model)     run.base_model = "qwen3:8b"
   ↓
TrainingConfig(base_model=req.base_model)              config.base_model = "qwen3:8b"
   ↓
manager.get_provider("unsloth").run(config)
   ↓
FastLanguageModel.from_pretrained("qwen3:8b")          → HFValidationError
```

**The Resolution Service was never called.** RedForge already ships the exact seam for
this — `FoundationModelService.ensure_foundation_for_base_model()` — and its own
docstring states the gap verbatim:

> "The strangler-fig seam between the existing Training subsystem and the Foundation
> Platform … resolve/register the corresponding foundation-model identity … **Training
> does not call this yet (that wiring is a later epic); the seam exists, is tested, and
> is ready.**"

So the Resolution Service was **bypassed** (never called), not incomplete or wrong. The
legacy training path predates the V3 Foundation Model architecture and consumed a raw
`base_model` string directly.

A second, smaller gap: even when called, the resolution **catalog** (`resolution.py::
_CATALOG`) had no `qwen3` family, so `qwen3:8b` (family `qwen3`, size `8.2B`) produced
zero candidates → could not resolve.

---

## 2. Architecture

| Entity | Identity | Example |
|---|---|---|
| **Runtime Model** | what the operator runs locally (Ollama/…); a *tag* | `qwen3:8b` |
| **Foundation Model** | training identity; a **Hugging Face repo** | `Qwen/Qwen3-8B` |
| **Model Resolution Service** | runtime → foundation, confidence-scored, provider-agnostic (one `ModelResolver` per runtime family + a generic fallback) | `resolve_runtime_to_foundation("qwen3:8b") → Qwen/Qwen3-8B` |

The incorrect substitution was an **absence**: the training launch used the runtime
identity as the foundation identity. The fix inserts the resolution step that the
architecture always intended, at the composition root (the API layer).

---

## 3. Code changes

| File | Why |
|---|---|
| `backend/app/api/training.py` | **Wire the seam.** `launch` now calls `foundation_model_service.ensure_foundation_for_base_model(req.base_model)` and uses the resolved `hf_repo` for both the run record and the `TrainingConfig`. A guard (`_is_hf_repo` + the seam's `unverified` flag) returns **422** if the selection cannot be resolved to a real HF repo — a runtime tag is **never** handed to a provider. Instrumentation logs the identifier at each stage (`[model-id] …`). |
| `backend/app/foundation_models/resolution.py` | **Extend the catalog** (the single, designed home for identity knowledge) with the `qwen3` family (`0.6b/1.7b/4b/8b/14b/32b → Qwen/Qwen3-*`) and the matching parameter buckets; add `qwen3` to the name-based family detector (before `qwen2`/`qwen`). No mapping lives in the training path. |
| `backend/app/training/runner.py` | Instrumentation: log `config.base_model` handed to the provider. |
| `backend/app/training/providers/_unsloth_impl.py` | Instrumentation: log the exact `model_name` passed to `FastLanguageModel.from_pretrained`. |
| `backend/tests/test_training_lab.py` | Updated the CRUD test to use a Foundation identity (HF repo); added two tests locking in the guarantee: a runtime tag resolves to the HF repo on the run, and an unresolvable tag → 422. |

Providers are now **runtime-agnostic**: they only ever receive an HF repo. The fix works
for every runtime because resolution selects its resolver from the active runtime
provider (Ollama/llama.cpp/LM Studio/vLLM/OpenAI-compat/…) with a generic fallback.

---

## 4. Validation

**Resolution (unit):**
```
resolve_runtime_to_foundation("qwen3:8b")  → Qwen/Qwen3-8B   (confidence 0.88, auto-resolved)
ensure_foundation_for_base_model("qwen3:8b") → hf_repo=Qwen/Qwen3-8B  source=resolved_from_runtime  auto_resolved=True
_is_hf_repo("qwen3:8b")=False   _is_hf_repo("Qwen/Qwen3-8B")=True
```

**End-to-end over HTTP — real `qwen3:8b` launch** (backend log; the provider receives the
HF repo, the original `HFValidationError` on the tag is gone):
```
[model-id] launch:   requested base_model='qwen3:8b' backend='unsloth'
[model-id] resolved: runtime_ref='qwen3:8b' → foundation hf_repo='Qwen/Qwen3-8B' source=resolved_from_runtime
[model-id] runner:   config.base_model='Qwen/Qwen3-8B'
[model-id] provider: FastLanguageModel.from_pretrained(model_name='Qwen/Qwen3-8B')
run.base_model = 'Qwen/Qwen3-8B'
→ no HFValidationError; no "Repo id must use alphanumeric"; from_pretrained accepted the repo.
```

**End-to-end completion through the SAME wired seam** (real Unsloth QLoRA run to
completion; here the operator supplied an HF-repo Foundation identity directly, so the
seam's HF-repo branch is exercised and the run finishes):
```
[model-id] launch → resolved (source=hf_hub) → runner config.base_model → provider from_pretrained
step 1/4 … step 4/4 · loss 4.04 → Saving LoRA adapter → Saved checkpoint → training complete
final run status=completed  metrics={final_loss: 4.043, steps: 4, epochs: 1.0}
```

**Regression:** `test_training_lab.py` + `test_foundation_models.py` = **24 passed**
(incl. the 2 new resolution-guard tests) and `test_model_discovery.py`.

---

## 5. Remaining issues

- **Real `Qwen/Qwen3-8B` weight download is environmental, not a code issue.** After the
  fix, `qwen3:8b` correctly resolves to `Qwen/Qwen3-8B` and Unsloth internally maps that
  to its 4-bit repo `unsloth/Qwen3-8B-unsloth-bnb-4bit`; loading then fails only because
  the multi-GB weights can't be fetched over this machine's flaky HF connection (a
  `config.json` fetch times out — the same network flakiness seen earlier). The
  architectural fix is independent of this: the provider receives a valid HF repo, and a
  complete run was demonstrated through the identical wired path on a cached model.
- **UX (not the reported bug):** `TrainingLabPage` still labels its dropdown as
  installed models (runtime tags). With the backend now resolving them, this works, but a
  future polish is to show the resolved Foundation Model identity in the wizard. No change
  was made here to stay within the P0 scope (a backend architectural fix).

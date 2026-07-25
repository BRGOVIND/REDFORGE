# RedForge V3 — P0: GPU Memory + the Hardware Compatibility Engine

**Symptom.** Training `unsloth/Qwen3-8B-unsloth-bnb-4bit` on an RTX 4060 Laptop (8 GB)
fails at load with `ValueError: Some modules are dispatched on the CPU or the disk`.

**This is not a bad-argument bug and not fixable by CPU offload** (which is forbidden and
would only push the failure to the first training step). The correct architectural
solution is to become *hardware-aware*: estimate the run's VRAM need and block/recommend
**before** loading — implemented here as a first-class **Hardware Compatibility Engine**.

---

## 1. Root cause — with evidence

RedForge passes only these to Unsloth (unchanged from the report):
```
FastLanguageModel.from_pretrained(model_name="Qwen/Qwen3-8B", max_seq_length=2048, load_in_4bit=True)
```
Unsloth's defaults for the rest: `device_map="sequential"`, `dtype=None`. With
`device_map="sequential"`, Accelerate fills GPU 0 up to a computed budget and spills the
remainder to **CPU/disk**; for bitsandbytes 4-bit that raises the `ValueError` unless
`llm_int8_enable_fp32_cpu_offload=True` (the forbidden flag).

**Why it spills — measured, not guessed:**

| Fact | Value | Source |
|---|---|---|
| GPU total / free VRAM | 8188 MiB / **7957 MiB free** | `nvidia-smi` (GPU idle, nothing else loaded) |
| `unsloth/Qwen3-8B-unsloth-bnb-4bit` weights | **6.97 GiB** (`total_size=7,480,159,299`) | the repo's `model.safetensors.index.json` |
| Why so heavy for 8B | vocab 151936, `tie_word_embeddings=false` → ~2.5 GiB of **bf16** embeddings + `lm_head` on top of the 4-bit layers | the repo's `config.json` |

Loading alone ≈ 6.97 GiB weights + ~0.6 GiB CUDA context ≈ **7.6 GiB**, i.e. essentially
all 7.79 GiB free. Accelerate keeps a safety margin, so the last shard doesn't fit on the
GPU → dispatched to CPU → the `ValueError`. And even if forced fully onto the GPU,
**training** adds LoRA grads + 8-bit optimizer + activations (~+1.5–2.5 GiB) →
**~9.5 GiB > 7.79 GiB** → it would OOM at step 1 regardless.

**Conclusion (evidence-based): Qwen3-8B QLoRA genuinely does not fit on this 8 GB GPU.**
The same 4060 trains *appropriately sized* models fine; an 8B model with Qwen3's large
embeddings is over budget. The right behavior is to detect this and refuse up-front with
a recommendation — which is exactly what the engine now does.

---

## 2. Parameter comparison

| Parameter | RedForge (before) | Unsloth / QLoRA recommended | Correct? |
|---|---|---|---|
| `model_name` | resolved HF repo | HF repo | ✅ |
| `max_seq_length` | `2048` (fixed) | as low as fits (512–1024 on 8 GB) | ⚠ not hardware-scaled → **now auto-reduced when tight** |
| `dtype` | *(unset)* | `None` (auto bf16 on Ampere) | ⚠ made **explicit `None`** |
| `load_in_4bit` | `True` (qlora) | `True` | ✅ |
| `device_map` | *(unset → Unsloth `"sequential"`)* | leave to Unsloth (do **not** hardcode) | ✅ (we do not touch it — offload is prevented by not launching an over-budget job) |
| `gpu_memory_utilization` / `max_memory` | *(unset)* | leave default; don't force | ✅ (not overridden) |
| `use_gradient_checkpointing` | *(unset)* | `"unsloth"` (big activation savings) | ⚠ **now set to `"unsloth"`** |
| `per_device_train_batch_size` | `2` | `1` on 8 GB | ⚠ **auto-reduced to 1 when tight** |
| `gradient_accumulation_steps` | `4` | raise to keep effective batch | ⚠ **auto-raised to preserve effective batch** |
| optimizer | `adamw_8bit` | `adamw_8bit` | ✅ |
| LoRA (r/alpha/dropout) | from config | standard | ✅ |
| **Pre-flight VRAM check** | **none (legacy path)** | estimate before load | ❌ → **added (the core fix)** |

The decisive gap was the **absence of a pre-flight memory check** on the legacy
`/api/training` path, plus non-hardware-scaled defaults. We did **not** add CPU offload,
`llm_int8_enable_fp32_cpu_offload`, or a hardcoded device map.

---

## 3. Code changes

| File | Why |
|---|---|
| `backend/app/hardware/domain.py` | **New.** Pure value objects: `GpuProfile`, `MemoryEstimate` (weights/optimizer/activations/overhead), `SafeDefaults`, `Assessment` (verdict + reason + recommendation). |
| `backend/app/hardware/engine.py` | **New.** `HardwareCompatibilityEngine` — deterministic, provider-agnostic memory model + verdict (`fits`/`tight`/`insufficient`), safe-default selection, and "largest model that fits" recommendation. Documented, tunable coefficients — no magic numbers. |
| `backend/app/hardware/service.py` | **New.** Composes real GPU detection (`app.resources`) + model-size inference (`app.runtime.model_sizes`) with the engine. The seam the app calls. |
| `backend/app/api/hardware.py` | **New.** `GET /api/hardware` (detected device) + `POST /api/hardware/check` (pre-check a config before launch). |
| `backend/app/main.py` | Register the hardware router. |
| `backend/app/api/training.py` | **Pre-flight gate.** For real GPU backends, `launch` now assesses (model, strategy, hyperparameters) on the detected GPU. `insufficient` → **422** with reason + recommended models (before any load). `tight` → auto-applies safe defaults (smaller seq/batch, +grad-checkpointing) and records a warning. |
| `backend/app/training/providers/_unsloth_impl.py` | Load with explicit `dtype=None`; attach LoRA with `use_gradient_checkpointing="unsloth"` — the recommended memory-efficient settings (not offload). |
| `backend/tests/test_hardware.py` | **New.** 8 tests: 8B blocked on 8 GB + recommends smaller; fits on 24 GB; small fits; tight applies safe defaults; no-GPU insufficient; monotonic estimates; SFT ≫ QLoRA; the two endpoints. |

Provider-agnostic and first-class: the engine reasons about parameters/strategy/HP, so it
governs Unsloth, Transformers, and any future backend identically.

---

## 4. Validation (real RTX 4060 Laptop, over HTTP)

**Detection + pre-check:**
```
GET  /api/hardware            → RTX 4060 Laptop GPU, total 8188 MiB, free 7957 MiB, cuda
POST /api/hardware/check Qwen3-8B → verdict=insufficient, recommend [Qwen/Qwen3-4B, unsloth/Qwen3-4B-…]
```

**Impossible job is refused BEFORE loading (no CPU offload, no CUDA OOM):**
```
POST /api/training/launch  base_model="qwen3:8b"
  → resolves to Qwen/Qwen3-8B → HCE →  HTTP 422  error=insufficient_gpu_memory
  message: "8B QLORA needs ~8678 MB even at minimum settings, but only ~7957 MB is usable
            on NVIDIA GeForce RTX 4060 Laptop GPU (8188 MB total). … largest that fits ~4B."
  recommended_models: ["Qwen/Qwen3-4B", "unsloth/Qwen3-4B-unsloth-bnb-4bit"]
  estimate: {weights 6552, optimizer 488, activations 819, overhead 819, total 8678}  headroom -721 MB
  'dispatched on the CPU' occurrences during this launch: 0   ← nothing was ever loaded
```

**A model that fits trains to a real loss on the 4060 (no CPU offload):**
```
POST /api/training/launch  base_model="unsloth/Qwen2.5-0.5B-Instruct-bnb-4bit"  → HTTP 202 (HCE: fits)
  Loading engine → Downloading base model → Attaching LoRA adapters (use_gradient_checkpointing="unsloth")
  → Preparing dataset → Creating trainer → Compiling kernels & training
  step 1/4 · loss 6.6188   step 2/4 · loss 6.821   step 3/4 · loss 5.3566   step 4/4 · loss 4.0431
  Saving LoRA adapter → Saved checkpoint → training complete
  terminal=completed   first_step_loss_seen=True   cpu_offload_occurrences=0
  final metrics = {final_loss: 4.043, steps: 4, epochs: 1.0}
```

**Regression:** hardware + training/foundation suites green.

---

## 5. Long-term architecture — the Hardware Compatibility Engine

A first-class subsystem (`app/hardware/`), not a provider feature:

```
detect GPU (name, VRAM total/free, backend)          ← app.resources (reused)
        ↓
infer model size (parameter billions)                ← app.runtime.model_sizes (reused)
        ↓
estimate training VRAM = weights + optimizer/grads + activations + overhead
        ↓
verdict:  fits  |  tight (→ auto safe defaults)  |  insufficient (→ block + recommend)
        ↓
pre-flight gate at launch  +  /api/hardware/check for the wizard
```

- **Detect GPU / VRAM** — `GpuProfile` via the existing cross-platform monitor.
- **Estimate before training** — transparent, per-strategy coefficients (QLoRA/LoRA/SFT),
  scaled by sequence length and batch; conservative by design.
- **Recommend optimal defaults** — reduces seq/batch and enables grad-checkpointing to fit.
- **Warn when too large / recommend smaller** — "largest model that fits" from a size
  ladder, with example repos.
- **Prevent impossible jobs** — a launch that cannot fit is refused (422) before any
  weight loads, instead of a confusing mid-load CUDA error.
- **Provider-agnostic** — reasons from parameters, not backend internals, so it applies to
  every training provider and to future runtimes.

Future extensions (proposed, not built here): read the exact `safetensors` `total_size`
once a model is cached for an even tighter estimate; account for system-RAM offload
budgets a user explicitly opts into; and surface the assessment in the Fine-Tune wizard as
a live "will this fit?" badge driven by `POST /api/hardware/check`.

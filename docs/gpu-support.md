# GPU Support

A GPU makes evaluations dramatically faster, but RedForge works on CPU too.

## How it works
GPU acceleration is handled by **your runtime** (Ollama, LM Studio, llama.cpp, or
vLLM), not RedForge — RedForge just talks to the runtime. If your runtime is using
the GPU, so is RedForge. RedForge *detects* your GPU (NVIDIA via `nvidia-smi`,
Apple Silicon via Metal) and shows it in `redforge doctor` and the setup wizard,
and uses it to estimate memory needs. The examples below use Ollama (the default).

## NVIDIA (Windows / Linux)
- Install the NVIDIA driver + CUDA runtime your runtime requires.
- Verify: `nvidia-smi` should list your GPU.
- Most runtimes use the GPU automatically when there's enough free VRAM.
- Check detection: `redforge doctor` → **GPU** row.

## Apple Silicon (macOS)
Ollama (and other Metal-aware runtimes) use the Metal backend automatically on
M-series Macs — no setup needed.

## No GPU / not enough VRAM
Everything still works on CPU, just slower. Tips:
- Use a smaller model (`:8b` or below).
- Use the **Quick Scan** profile.
- If a model is larger than your VRAM, Ollama spills to system RAM (slow) — the
  New Evaluation page warns when the estimate exceeds available memory.

## Checking VRAM
```bash
nvidia-smi                 # NVIDIA: total/free VRAM
redforge doctor            # RedForge's view (GPU + RAM rows)
```

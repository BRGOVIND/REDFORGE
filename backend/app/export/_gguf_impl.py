"""Real llama.cpp GGUF conversion (opt-in, toolchain-only).

The concrete counterpart to :class:`GGUFExportProvider`, isolated in its own module so
the llama.cpp toolchain is invoked only when real export is explicitly enabled
(``REDFORGE_ENABLE_REAL_EXPORT=1``) AND the tooling is present. Never imported on the
default (simulated) path and never imported in CI — hence ``# pragma: no cover``.

Local-first (Constitution §9/§10.8): shells out to llama.cpp's OWN converter +
quantizer exactly as a human operator would; never imports the Runtime Engine.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys


def _llamacpp_dir() -> str | None:
    d = os.environ.get("REDFORGE_LLAMACPP_DIR")
    return d if d and os.path.isdir(d) else None


def _find_converter() -> list[str]:  # pragma: no cover - requires the local llama.cpp toolchain
    """Locate llama.cpp's HF→GGUF converter. Prefers the script inside
    ``REDFORGE_LLAMACPP_DIR``; falls back to a ``convert_hf_to_gguf`` on PATH."""
    d = _llamacpp_dir()
    if d:
        for name in ("convert_hf_to_gguf.py", "convert-hf-to-gguf.py", "convert.py"):
            cand = os.path.join(d, name)
            if os.path.isfile(cand):
                return [sys.executable, cand]
    on_path = shutil.which("convert_hf_to_gguf") or shutil.which("convert-hf-to-gguf")
    if on_path:
        return [on_path]
    raise FileNotFoundError(
        "llama.cpp HF→GGUF converter not found. Set REDFORGE_LLAMACPP_DIR to your "
        "llama.cpp checkout (containing convert_hf_to_gguf.py) or put it on PATH.")


def _find_quantize() -> str:  # pragma: no cover - requires the local llama.cpp toolchain
    d = _llamacpp_dir()
    if d:
        for name in ("llama-quantize", "llama-quantize.exe", "quantize", "quantize.exe"):
            cand = os.path.join(d, name)
            if os.path.isfile(cand):
                return cand
    found = shutil.which("llama-quantize") or shutil.which("quantize")
    if found:
        return found
    raise FileNotFoundError(
        "llama.cpp 'llama-quantize' not found. Set REDFORGE_LLAMACPP_DIR or put it on PATH.")


def convert_to_gguf(source_path: str, out_path: str, quantization: str) -> str:  # pragma: no cover - requires the local llama.cpp toolchain
    """Convert a merged HF model at ``source_path`` to a quantized GGUF at ``out_path``.

    ``source_path`` is the merged-model directory (or a manifest whose directory holds
    the real weights). Runs llama.cpp's converter to produce an f16 GGUF, then
    ``llama-quantize`` to the requested quantization. Raises on any tooling failure so
    the export Job surfaces the real error verbatim (never a silent success)."""
    model_dir = source_path if os.path.isdir(source_path) else os.path.dirname(source_path)
    if not model_dir or not os.path.isdir(model_dir):
        raise FileNotFoundError(f"merged model directory not found for source '{source_path}'")

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    f16_path = os.path.join(os.path.dirname(out_path) or ".", "model.f16.gguf")

    # 1) HF -> f16 GGUF.
    convert_cmd = _find_converter() + [model_dir, "--outfile", f16_path, "--outtype", "f16"]
    subprocess.run(convert_cmd, check=True)

    # 2) f16 GGUF -> quantized GGUF.
    subprocess.run([_find_quantize(), f16_path, out_path, quantization.upper()], check=True)

    if not os.path.isfile(out_path):
        raise RuntimeError(f"llama-quantize reported success but {out_path} is missing")
    return out_path

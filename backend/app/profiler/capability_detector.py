"""Detect a model's capabilities from Ollama metadata (with name fallbacks).

Ollama's ``/api/show`` returns a ``details`` block (parameter size, quantization,
family) and a ``model_info`` block (context length). When that metadata is
unavailable — e.g. Ollama is offline or the model isn't pulled — we fall back to
parsing the model name so a profile can still be produced.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import httpx

from app.runtime.model_sizes import parse_param_billions

OLLAMA_BASE_URL = "http://localhost:11434"


@dataclass
class Capabilities:
    parameter_size: Optional[float]        # billions of parameters
    parameter_label: Optional[str]         # e.g. "8.0B"
    quantization: Optional[str]            # e.g. "Q4_0"
    context_length: Optional[int]
    family: Optional[str]
    source: str                            # "ollama" or "name"


async def fetch_model_metadata(
    model_name: str, base_url: str = OLLAMA_BASE_URL, timeout: float = 15.0
) -> Optional[dict]:
    """Call Ollama ``/api/show``. Returns ``None`` if unreachable/not found."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(f"{base_url}/api/show", json={"name": model_name})
            resp.raise_for_status()
            return resp.json()
    except Exception:
        return None


def _extract_context_length(model_info: dict) -> Optional[int]:
    # Keys look like "llama.context_length", "qwen2.context_length", etc.
    for key, value in model_info.items():
        if key.endswith(".context_length"):
            try:
                return int(value)
            except (TypeError, ValueError):
                return None
    return None


def _param_label_to_billions(label: Optional[str]) -> Optional[float]:
    if not label:
        return None
    return parse_param_billions(label)


def detect_capabilities(model_name: str, ollama_show: Optional[dict]) -> Capabilities:
    """Combine Ollama metadata (preferred) with name-based fallbacks."""
    if ollama_show:
        details = ollama_show.get("details") or {}
        model_info = ollama_show.get("model_info") or {}

        label = details.get("parameter_size")
        billions = _param_label_to_billions(label) or parse_param_billions(model_name)
        family = details.get("family")
        families = details.get("families")
        if not family and isinstance(families, list) and families:
            family = families[0]

        return Capabilities(
            parameter_size=billions,
            parameter_label=label or (f"{billions:g}B" if billions else None),
            quantization=details.get("quantization_level"),
            context_length=_extract_context_length(model_info),
            family=family,
            source="ollama",
        )

    # Fallback: infer what we can from the name alone.
    billions = parse_param_billions(model_name)
    family = model_name.split(":")[0].split("/")[-1] or None
    return Capabilities(
        parameter_size=billions,
        parameter_label=f"{billions:g}B" if billions else None,
        quantization=None,
        context_length=None,
        family=family,
        source="name",
    )

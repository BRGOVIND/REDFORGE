"""Heuristic memory footprint estimates for Ollama models.

These are deliberately rough, quantized (~Q4) estimates keyed off the parameter
count embedded in a model's name (e.g. ``llama3:8b`` -> ~5.5 GB). They exist to
give the UI a *ballpark* so it can warn before a run, not to be exact. When a
size cannot be inferred, a conservative default is used.
"""
from __future__ import annotations

import re

# Approximate resident memory (MB) for a Q4-quantized model of a given size.
_PARAM_RAM_MB: list[tuple[float, int]] = [
    (0.5, 700),
    (1.0, 1200),
    (2.0, 2000),
    (3.0, 3000),
    (7.0, 5000),
    (8.0, 5600),
    (13.0, 9000),
    (14.0, 9500),
    (34.0, 20000),
    (70.0, 42000),
]

DEFAULT_MODEL_RAM_MB = 5000  # assume a ~7-8B model when size is unknown

# Matches "7b", "13B", "1.5b", "0.5b" tokens in a model name.
_SIZE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*b\b", re.IGNORECASE)


def parse_param_billions(model_name: str) -> float | None:
    """Extract the parameter count in billions from a model name, if present."""
    match = _SIZE_RE.search(model_name or "")
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def estimate_model_ram_mb(model_name: str) -> int:
    """Estimated resident memory (MB) to run ``model_name``.

    Picks the closest known parameter size at or above the model's size; falls
    back to :data:`DEFAULT_MODEL_RAM_MB` when the size can't be inferred.
    """
    billions = parse_param_billions(model_name)
    if billions is None:
        return DEFAULT_MODEL_RAM_MB
    for size, ram in _PARAM_RAM_MB:
        if billions <= size:
            return ram
    # Larger than the biggest tabulated size: extrapolate ~0.6 GB per billion.
    return int(billions * 600)

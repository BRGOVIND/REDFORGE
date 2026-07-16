"""Train / validation / test splitting — deterministic, local.

Deterministic given a seed so a split is reproducible. Percentages are
normalized; the split is index-based (optionally shuffled with a seeded PRNG that
does not touch global random state).
"""
from __future__ import annotations

from typing import Any


def _seeded_order(n: int, seed: int) -> list[int]:
    """A reproducible permutation of range(n) via a tiny LCG (no global random)."""
    idx = list(range(n))
    state = (seed or 1) & 0xFFFFFFFF
    for i in range(n - 1, 0, -1):
        state = (1103515245 * state + 12345) & 0x7FFFFFFF
        j = state % (i + 1)
        idx[i], idx[j] = idx[j], idx[i]
    return idx


def split(
    records: list[Any], *, train: float = 0.8, val: float = 0.1, test: float = 0.1,
    shuffle: bool = True, seed: int = 42,
) -> dict:
    """Return ``{train, validation, test, statistics}`` (record lists + counts).

    Percentages are normalized to sum to 1; the test split takes the remainder so
    counts always add up to ``len(records)``.
    """
    total = train + val + test
    if total <= 0:
        train, val, test, total = 0.8, 0.1, 0.1, 1.0
    train, val = train / total, val / total

    n = len(records)
    order = _seeded_order(n, seed) if shuffle else list(range(n))
    n_train = int(n * train)
    n_val = int(n * val)

    tr = [records[i] for i in order[:n_train]]
    va = [records[i] for i in order[n_train:n_train + n_val]]
    te = [records[i] for i in order[n_train + n_val:]]

    return {
        "train": tr,
        "validation": va,
        "test": te,
        "statistics": {
            "total": n,
            "train": len(tr),
            "validation": len(va),
            "test": len(te),
            "ratios": {
                "train": round(train, 3),
                "validation": round(val, 3),
                "test": round(1 - train - val, 3),
            },
            "seed": seed,
            "shuffled": shuffle,
        },
    }

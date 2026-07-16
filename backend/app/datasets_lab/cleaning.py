"""Dataset cleaning — pure, composable transforms.

Each operation takes ``records`` and returns *new* records plus a note; the input
is never mutated, so a caller can preview the result before saving. Saving is a
separate step (a new version) handled by the service — everything is reversible
until then.
"""
from __future__ import annotations

import unicodedata
from typing import Any

# Available cleaning operations, in a stable display order.
OPERATIONS = [
    "remove_duplicates",
    "trim_whitespace",
    "normalize_unicode",
    "remove_empty",
]


def _text(row: Any) -> str:
    if isinstance(row, str):
        return row
    if isinstance(row, dict):
        return " ".join(str(v) for v in row.values() if v is not None)
    return str(row)


def _apply_to_strings(row: Any, fn) -> Any:
    if isinstance(row, str):
        return fn(row)
    if isinstance(row, dict):
        return {k: (fn(v) if isinstance(v, str) else v) for k, v in row.items()}
    return row


def remove_duplicates(records: list[Any]) -> tuple[list[Any], str]:
    seen: set[str] = set()
    out: list[Any] = []
    for r in records:
        key = _text(r).strip().lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out, f"removed {len(records) - len(out)} duplicate record(s)"


def trim_whitespace(records: list[Any]) -> tuple[list[Any], str]:
    out = [_apply_to_strings(r, lambda s: s.strip()) for r in records]
    return out, "trimmed leading/trailing whitespace"


def normalize_unicode(records: list[Any]) -> tuple[list[Any], str]:
    def norm(s: str) -> str:
        return unicodedata.normalize("NFKC", s).replace(" ", " ")
    out = [_apply_to_strings(r, norm) for r in records]
    return out, "normalized unicode (NFKC)"


def remove_empty(records: list[Any]) -> tuple[list[Any], str]:
    out = [r for r in records if _text(r).strip()]
    return out, f"removed {len(records) - len(out)} empty record(s)"


_FUNCS = {
    "remove_duplicates": remove_duplicates,
    "trim_whitespace": trim_whitespace,
    "normalize_unicode": normalize_unicode,
    "remove_empty": remove_empty,
}


def clean(records: list[Any], operations: list[str]) -> tuple[list[Any], list[str]]:
    """Apply operations in the requested order. Returns (new_records, notes).

    Unknown operations are skipped (noted), never fatal. The input list is not
    mutated — the result is a fresh list, so callers can preview safely.
    """
    current = list(records)
    notes: list[str] = []
    for op in operations:
        fn = _FUNCS.get(op)
        if fn is None:
            notes.append(f"skipped unknown operation '{op}'")
            continue
        current, note = fn(current)
        notes.append(note)
    return current, notes

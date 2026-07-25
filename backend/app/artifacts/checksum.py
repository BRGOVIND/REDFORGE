"""Pure checksum helpers for file-backed artifacts (RedForge V3, Epic 2).

Deterministic (§2.11), dependency-free. Used by the storage layer to compute and
verify the checksums that make file-backed artifacts integrity-checkable (§6.8) —
closing the prior architecture's "unverified path string" gap.
"""
from __future__ import annotations

import hashlib
from typing import Optional

_CHUNK = 1024 * 1024  # 1 MiB


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str) -> Optional[str]:
    """SHA-256 of a file's contents, streamed. Returns None if the file cannot be
    read (missing/permission) — the caller treats that as an integrity failure
    honestly rather than crashing."""
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(_CHUNK), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None

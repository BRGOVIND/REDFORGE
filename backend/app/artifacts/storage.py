"""Artifact storage abstraction (RedForge V3, Epic 2).

A :class:`StorageProvider` is a pluggable backend for *file-backed* artifact bytes.
The Constitution keeps the Artifact domain deliberately ignorant of *how* bytes are
stored (§6.9): the registry knows an artifact is file-backed at a location; it does
not know whether that location is local disk, and — by design — the storage
provider could later be S3/Azure/GCS with no change to the artifact domain.

Epic 2 ships **only** :class:`LocalStorageProvider` (local-first, §2.1). The cloud
providers are intentionally *not* implemented; the abstraction exists so they can be
added later without touching artifacts. Registration follows the same flat-registry
provider pattern used everywhere else in RedForge.

Data-backed artifacts (results/reports/models-as-rows) do not use storage at all —
their bytes are a DB row referenced by ``table_ref``.
"""
from __future__ import annotations

import os
import shutil
from abc import ABC, abstractmethod
from typing import Optional

from app.artifacts.checksum import sha256_file


class StorageProvider(ABC):
    """Backend for file-backed artifact bytes. All paths are provider-relative
    identifiers; ``resolve`` turns one into something a consumer can open."""

    name: str = "storage"

    @abstractmethod
    def exists(self, location: str) -> bool: ...

    @abstractmethod
    def size(self, location: str) -> Optional[int]: ...

    @abstractmethod
    def checksum(self, location: str) -> Optional[str]: ...

    @abstractmethod
    def move(self, src: str, dst: str) -> bool: ...

    @abstractmethod
    def delete(self, location: str) -> bool: ...

    @abstractmethod
    def resolve(self, location: str) -> str: ...


class LocalStorageProvider(StorageProvider):
    """Local filesystem storage. The only provider in Epic 2 (local-first)."""

    name = "local"

    def exists(self, location: str) -> bool:
        try:
            return bool(location) and os.path.exists(location)
        except OSError:
            return False

    def size(self, location: str) -> Optional[int]:
        try:
            return os.path.getsize(location) if self.exists(location) else None
        except OSError:
            return None

    def checksum(self, location: str) -> Optional[str]:
        return sha256_file(location) if self.exists(location) else None

    def move(self, src: str, dst: str) -> bool:
        try:
            if not self.exists(src):
                return False
            os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
            shutil.move(src, dst)
            return True
        except OSError:
            return False

    def delete(self, location: str) -> bool:
        try:
            if not self.exists(location):
                return False
            if os.path.isdir(location):
                shutil.rmtree(location, ignore_errors=True)
            else:
                os.remove(location)
            return True
        except OSError:
            return False

    def resolve(self, location: str) -> str:
        return location


# Flat provider registry (same pattern as runtime/training providers). Local is the
# built-in default; cloud providers register here in a later effort, no domain change.
_PROVIDERS: dict[str, StorageProvider] = {"local": LocalStorageProvider()}
_DEFAULT = "local"


def register_storage_provider(provider: StorageProvider) -> None:
    _PROVIDERS[provider.name] = provider


def get_storage_provider(name: Optional[str] = None) -> StorageProvider:
    return _PROVIDERS.get(name or _DEFAULT, _PROVIDERS[_DEFAULT])


def list_storage_providers() -> list[str]:
    return sorted(_PROVIDERS)

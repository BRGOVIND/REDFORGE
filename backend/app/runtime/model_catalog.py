"""Model Manager service — the provider-agnostic model catalog.

Reuses the existing model discovery (``Provider.list_models_raw`` / ``show_model``)
and the shared :class:`RuntimeClient`; it never re-implements listing, transport,
or runtime logic. All provider-specific translation happens here in pure mapper
functions, so the frontend consumes one canonical shape and never learns which
provider a model belongs to.

Two tiers (performance: fast catalog > complete metadata):
  * **basic**    — cheap, from a single ``list_models_raw`` per provider.
  * **extended** — expensive, from ``show_model`` (or a richer list entry), loaded
                   only when the user opens a model's Details.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional

from app.config import settings
from app.runtime import manager
from app.runtime.client import Provider
from app.runtime.errors import RuntimeLLMError
from app.runtime.manager import get_runtime


# ---------------------------------------------------------------------------
# Pure, provider-agnostic mappers
# ---------------------------------------------------------------------------

def _unix_to_iso(value) -> Optional[str]:
    try:
        return datetime.fromtimestamp(float(value), timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return None


def _coalesce_modified(raw: dict) -> Optional[str]:
    if raw.get("modified_at"):
        return raw["modified_at"]
    if raw.get("created_at"):
        return raw["created_at"]
    if raw.get("created") is not None:
        return _unix_to_iso(raw["created"])
    return None


def to_basic(provider: str, label: str, capabilities: dict, online: bool, raw: dict) -> dict:
    """Map one native list entry to the canonical *basic* model shape.

    Reads well-known keys across dialects; absent fields become ``None`` — never
    an error. Extra provider-native keys are ignored here (they surface in the
    extended view).
    """
    details = raw.get("details") or {}
    return {
        "name": raw.get("name"),
        "provider": provider,
        "provider_label": label,
        "size": raw.get("size"),
        "quantization": details.get("quantization_level") or raw.get("quantization"),
        "family": details.get("family") or raw.get("family"),
        "modified_at": _coalesce_modified(raw),
        "digest": raw.get("digest"),
        "status": "available" if online else "unreachable",
        "capabilities": capabilities,
    }


def _find_by_suffix(info: dict, suffix: str):
    for key, value in info.items():
        if key.endswith(suffix):
            return value
    return None


def _parse_stop_tokens(parameters: Optional[str]) -> list[str]:
    """Pull ``stop "..."`` entries out of Ollama's newline ``parameters`` blob."""
    if not parameters:
        return []
    tokens: list[str] = []
    for line in parameters.splitlines():
        line = line.strip()
        if line.lower().startswith("stop"):
            rest = line[4:].strip().strip('"')
            if rest:
                tokens.append(rest)
    return tokens


def to_extended(raw_basic: dict, show: Optional[dict]) -> dict:
    """Map a provider's ``show_model`` payload to the canonical *extended* shape.

    Handles Ollama's rich ``/api/show`` (``model_info`` + ``details`` + ``modelfile``)
    and the generic best-effort dict other providers return, always degrading to
    ``None``/empty rather than failing.
    """
    show = show or {}
    model_info = show.get("model_info") or {}
    details = show.get("details") or {}

    context_length = (
        _find_by_suffix(model_info, ".context_length")
        or show.get("context_length")
        or raw_basic.get("context_length")
    )
    parameter_count = (
        details.get("parameter_size")
        or model_info.get("general.parameter_count")
        or show.get("parameter_count")
    )
    architecture = model_info.get("general.architecture") or show.get("architecture")
    tokenizer = model_info.get("tokenizer.ggml.model") or _find_by_suffix(model_info, ".model")

    # Everything not already surfaced, for the "provider-specific metadata" panel.
    known = {"model_info", "details", "modelfile", "template", "license", "parameters", "capabilities"}
    provider_metadata = {k: v for k, v in show.items() if k not in known}

    return {
        "context_length": context_length,
        "parameter_count": parameter_count,
        "architecture": architecture,
        "template": show.get("template"),
        "license": show.get("license"),
        "families": details.get("families") or show.get("families"),
        "tokenizer": tokenizer,
        "modelfile": show.get("modelfile"),
        "stop_tokens": _parse_stop_tokens(show.get("parameters")),
        "provider_metadata": provider_metadata,
    }


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class ModelCatalog:
    def _default(self) -> str:
        return settings.RUNTIME_PROVIDER.lower()

    def _provider_for(self, name: str) -> Provider:
        # Route the default through the shared RuntimeClient (single source of truth).
        if name == self._default():
            return get_runtime().provider
        return manager.build_provider(name)

    async def _list_raw(self, name: str, provider: Provider) -> list[dict]:
        if name == self._default():
            return await get_runtime().list_models_raw()
        return await provider.list_models_raw()

    async def _group(self, name: str) -> dict:
        provider = self._provider_for(name)
        label = getattr(provider, "label", name)
        caps = provider.capabilities()

        online = False
        error: Optional[str] = None
        try:
            online = await provider.health()
        except Exception as exc:  # noqa: BLE001
            error = str(exc)

        models: list[dict] = []
        if online:
            try:
                raw_entries = await self._list_raw(name, provider)
                models = [
                    to_basic(name, label, caps, online, r)
                    for r in raw_entries
                    if r.get("name")
                ]
            except RuntimeLLMError as exc:
                error = exc.message
            except Exception as exc:  # noqa: BLE001
                error = str(exc)

        return {
            "provider": name,
            "label": label,
            "online": bool(online),
            "healthy": bool(online) and error is None,
            "can_delete": caps["supports_delete"],
            "capabilities": caps,
            "error": error,
            "model_count": len(models),
            "models": models,
        }

    async def catalog(self) -> dict:
        names = manager.available_providers()
        groups = await asyncio.gather(*(self._group(n) for n in names))
        total = sum(g["model_count"] for g in groups)
        return {"providers": groups, "total": total, "default": self._default()}

    async def detail(self, provider_name: str, model_name: str) -> Optional[dict]:
        key = provider_name.lower()
        if not manager_knows(key):
            raise KeyError(key)
        provider = self._provider_for(key)
        label = getattr(provider, "label", key)
        caps = provider.capabilities()

        online = False
        try:
            online = await provider.health()
        except Exception:  # noqa: BLE001
            online = False

        # Basic fields from the (cheap) list; note whether the model was found.
        raw_basic = {"name": model_name}
        found_in_list = False
        if online:
            try:
                for r in await self._list_raw(key, provider):
                    if r.get("name") == model_name:
                        raw_basic, found_in_list = r, True
                        break
            except Exception:  # noqa: BLE001
                pass

        # Extended fields loaded on demand.
        show = None
        if online:
            try:
                show = await provider.show_model(model_name)
            except Exception:  # noqa: BLE001
                show = None

        # 404 only when the provider is reachable but truly has no such model.
        if online and not found_in_list and show is None:
            return None

        basic = to_basic(key, label, caps, online, raw_basic)
        extended = to_extended(raw_basic, show)
        return {**basic, **extended, "capabilities": caps}

    async def delete(self, provider_name: str, model_name: str) -> None:
        key = provider_name.lower()
        if not manager_knows(key):
            raise KeyError(key)
        provider = self._provider_for(key)
        if not getattr(provider, "supports_deletion", False):
            raise UnsupportedCapability(
                f"provider '{key}' does not support model deletion"
            )
        await provider.delete_model(model_name)  # raises RuntimeLLMError on failure
        # Drop cached model lists so the catalog reflects the deletion.
        if key == self._default():
            get_runtime().invalidate_cache()


class UnsupportedCapability(Exception):
    """Raised when a provider is asked to do something it does not support."""


def manager_knows(name: str) -> bool:
    return name.lower() in manager._PROVIDERS


model_catalog = ModelCatalog()

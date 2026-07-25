"""Model Hub — the ``model_download`` Job handler.

Downloading a model is a first-class Job, so it flows through the ONE Execution
Platform and appears in the Global Task Manager (progress, ETA, cancel, logs, retry)
like every other long-running operation — no terminal, no ``huggingface-cli``/``ollama
pull`` for the user. Network + filesystem paths are ``# pragma: no cover`` (not run in
CI); the routing/validation is unit-tested.

Post-download it registers the identity so the model is immediately usable:
  • Hugging Face  → Foundation Model (hf_repo + local cache path, status LOCAL).
  • Ollama        → queues a runtime scan so discovery registers the runtime model.
"""
from __future__ import annotations

import asyncio
import json
import os
import threading

from app.jobs.domain import JobResult
from app.logging_config import get_logger
from app.model_hub import catalog

logger = get_logger("model-hub")


def register_model_hub_handlers() -> None:
    from app.jobs.handlers import handler_registry
    handler_registry.register("model_download", _handle_model_download)


async def _handle_model_download(job, ctx) -> JobResult:
    p = job.params or {}
    entry = catalog.get(p.get("model_id"))
    if entry is None:
        return JobResult(success=False, message=f"unknown model '{p.get('model_id')}'")
    source = (p.get("source") or ("huggingface" if entry.hf_repo else "ollama")).lower()
    await ctx.report_progress(0.0, f"Preparing to download {entry.name}…")
    await ctx.log(f"Model Hub: downloading {entry.name} via {source}")
    if source == "ollama":
        if not entry.ollama_tag:
            return JobResult(success=False, message=f"{entry.name} is not available via Ollama")
        return await _download_ollama(ctx, entry)
    if not entry.hf_repo:
        return JobResult(success=False, message=f"{entry.name} has no Hugging Face source — use Ollama")
    return await _download_hf(ctx, entry)


# --- Hugging Face ---------------------------------------------------------------

def _hf_cache_dir(repo: str) -> str:  # pragma: no cover - env-dependent
    try:
        from huggingface_hub.constants import HF_HUB_CACHE
        base = HF_HUB_CACHE
    except Exception:  # noqa: BLE001
        base = os.path.join(os.path.expanduser("~"), ".cache", "huggingface", "hub")
    return os.path.join(base, "models--" + repo.replace("/", "--"))


def _dir_size(path: str) -> int:  # pragma: no cover
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def _hf_total_bytes(repo: str) -> int:  # pragma: no cover - network
    try:
        from huggingface_hub import HfApi
        info = HfApi().model_info(repo, files_metadata=True)
        return sum(int(s.size or 0) for s in (info.siblings or []))
    except Exception:  # noqa: BLE001
        return 0


async def _register_foundation(repo: str, path: str) -> dict | None:  # pragma: no cover
    try:
        from app.foundation_models import foundation_model_service
        return await foundation_model_service.register(hf_repo=repo, cache_path=path, source="hf_hub")
    except Exception as exc:  # noqa: BLE001
        logger.warning("post-download foundation registration failed: %s", exc)
        return None


async def _download_hf(ctx, entry) -> JobResult:  # pragma: no cover - network + FS
    repo = entry.hf_repo
    total = await asyncio.to_thread(_hf_total_bytes, repo)
    cache_dir = _hf_cache_dir(repo)
    holder: dict = {"path": None, "error": None}

    def _work():
        try:
            from huggingface_hub import snapshot_download
            holder["path"] = snapshot_download(repo, max_workers=2)
        except BaseException as exc:  # noqa: BLE001 - surface the real error
            holder["error"] = exc

    thread = threading.Thread(target=_work, daemon=True)
    thread.start()
    await ctx.report_progress(0.02, f"Downloading {entry.name} ({entry.download_size_gb:g} GB)…")
    est_total = total or int(entry.download_size_gb * 1e9)
    while thread.is_alive():
        if ctx.is_cancelled():
            await ctx.log("cancellation requested — the current file finishes in the background")
            return JobResult(success=False, message="download cancelled")
        got = _dir_size(cache_dir)
        frac = min(0.97, got / est_total) if est_total else 0.5
        await ctx.report_progress(frac, f"Downloading {entry.name}… {got/1e9:.1f}/{entry.download_size_gb:g} GB")
        await asyncio.sleep(1.0)
    if holder["error"] is not None:
        return JobResult(success=False, message=f"download failed: {holder['error']}")

    path = holder["path"]
    await ctx.report_progress(0.98, "Verifying files…")
    verified = bool(path and os.path.isdir(path))
    await ctx.log(f"downloaded to {path}")
    fm = await _register_foundation(repo, path)
    await ctx.report_progress(1.0, "Ready")
    return JobResult(
        success=True, message=f"{entry.name} downloaded and ready",
        data={"model_id": entry.id, "source": "huggingface", "hf_repo": repo, "path": path,
              "verified": verified, "foundation_model_id": (fm or {}).get("id"),
              "ready": True})


# --- Ollama ---------------------------------------------------------------------

def _ollama_base() -> str:
    try:
        from app.config import settings
        return (settings.OLLAMA_BASE_URL or "http://localhost:11434").rstrip("/")
    except Exception:  # noqa: BLE001
        return "http://localhost:11434"


async def _download_ollama(ctx, entry) -> JobResult:  # pragma: no cover - needs ollama
    tag = entry.ollama_tag
    base = _ollama_base()
    try:
        import httpx
    except Exception as exc:  # noqa: BLE001
        return JobResult(success=False, message=f"httpx unavailable: {exc}")
    await ctx.report_progress(0.02, f"Pulling {tag} via Ollama…")
    try:
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("POST", f"{base}/api/pull", json={"model": tag}) as resp:
                if resp.status_code != 200:
                    return JobResult(success=False, message=f"ollama pull failed: HTTP {resp.status_code}")
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    if ctx.is_cancelled():
                        return JobResult(success=False, message="download cancelled")
                    try:
                        ev = json.loads(line)
                    except ValueError:
                        continue
                    status = ev.get("status", "")
                    completed, total = ev.get("completed"), ev.get("total")
                    if completed and total:
                        await ctx.report_progress(min(0.99, completed / total),
                                                  f"{status} — {completed/1e9:.1f}/{total/1e9:.1f} GB")
                    elif status:
                        await ctx.log(status)
    except Exception as exc:  # noqa: BLE001
        return JobResult(success=False, message=f"ollama pull error: {exc}")

    # The runtime model is now installed — queue a scan so discovery registers it.
    try:
        from app.jobs import job_service
        await job_service.submit(type="runtime_discovery")
    except Exception:  # noqa: BLE001
        pass
    await ctx.report_progress(1.0, "Ready")
    return JobResult(success=True, message=f"{entry.name} pulled via Ollama and ready",
                     data={"model_id": entry.id, "source": "ollama", "ollama_tag": tag, "ready": True})

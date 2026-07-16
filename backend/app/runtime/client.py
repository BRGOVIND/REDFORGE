"""The unified runtime engine and provider abstraction.

Everything that talks to an LLM goes through :class:`RuntimeClient` (the runtime
"manager"). It owns the queue, cancellation, timeouts, retries, metrics, model
cache, and logging, and delegates only the wire transport to a :class:`Provider`.

Providers live in :mod:`app.runtime.providers` and implement *nothing* but
provider-specific communication — no queue/retry/metrics/cancellation logic is
ever duplicated there. No raw ``httpx`` exception escapes a provider: each maps
transport failures to :mod:`app.runtime.errors` via :mod:`app.runtime.transport`.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from abc import ABC, abstractmethod
from typing import AsyncIterator, Optional
from uuid import uuid4

from app.config import settings
from app.logging_config import get_logger, log_op
from app.runtime.cancel import CancellationToken, CancelRegistry
from app.runtime.errors import (
    CancelledGeneration,
    ConnectionFailure,
    GenerationTimeout,
    ProviderUnavailable,
)
from app.runtime.metrics import metrics
from app.runtime.models import ModelCache
from app.runtime.queue import GenerationQueue
from app.runtime.responses import GenerationResult, StreamEvent
from app.runtime.stream import run_stream

logger = get_logger("runtime")


# ---------------------------------------------------------------------------
# Provider abstraction
# ---------------------------------------------------------------------------

class Provider(ABC):
    """A backend that can run generations. Implement one per LLM server/API.

    A provider is responsible for *communication only*: build the request, parse
    the response, and map transport errors. The shared runtime concerns (queue,
    retries, metrics, cancellation, streaming assembly) live in
    :class:`RuntimeClient` and must never be reimplemented here.

    Contract:
      * :meth:`generate` returns a :class:`GenerationResult`.
      * :meth:`stream_generate` yields raw chunk dicts shaped like
        ``{"response": <delta>, "done": <bool>, "eval_count"?, "done_reason"?}``;
        the streaming engine turns these into :class:`StreamEvent`s uniformly.
      * :meth:`health`, :meth:`list_models_raw`, :meth:`show_model` are metadata.
    """

    name: str = "provider"
    label: str = "Provider"          # human-facing name (override per provider)

    # -- setup guidance (declarative, provider-owned) -----------------------
    # Surfaced by onboarding / the Setup page / the CLI so guidance always comes
    # from the *active* provider — never hardcoded per call site.
    docs_url: str = ""               # where to install / get a key
    setup_hint: str = ""             # one-line "how to make this provider ready"

    # -- capabilities -------------------------------------------------------
    # Lightweight, declarative feature flags. Providers override the class
    # attributes; the management/model layers and the frontend read the
    # ``capabilities()`` object rather than checking provider names. Defaults are
    # conservative (a minimal provider exposes only name + streaming).
    supports_deletion: bool = False        # can delete an installed model
    supports_metadata: bool = False        # exposes more than just a model name
    supports_context_length: bool = False  # can report a model's context window
    supports_streaming: bool = True        # implements stream_generate
    supports_embeddings: bool = False       # exposes an embeddings endpoint
    supports_pull: bool = False             # can download/install a model locally

    def capabilities(self) -> dict:
        """A provider-agnostic capabilities object (see the class attributes)."""
        return {
            "supports_delete": self.supports_deletion,
            "supports_metadata": self.supports_metadata,
            "supports_context_length": self.supports_context_length,
            "supports_streaming": self.supports_streaming,
            "supports_embeddings": self.supports_embeddings,
            "supports_pull": self.supports_pull,
        }

    async def pull_model(self, model: str):
        """Download/install a model, yielding progress dicts
        ``{"status", "completed"?, "total"?}``. Only providers with
        ``supports_pull`` implement this (e.g. Ollama)."""
        raise NotImplementedError(f"provider '{self.name}' cannot pull models")
        yield  # pragma: no cover - makes this an async generator

    @abstractmethod
    async def generate(self, model: str, prompt: str, *, options: Optional[dict] = None) -> GenerationResult:
        """Generate a completion. ``options`` (optional) carries sampling params
        — ``temperature``, ``top_p``, ``max_tokens``, ``seed``, ``system`` — used
        by the Playground; providers apply what they support and ignore the rest."""
        ...

    @abstractmethod
    def stream_generate(self, model: str, prompt: str) -> AsyncIterator[dict]:
        """Yield raw provider chunks (dicts). Streaming engine turns these into
        :class:`StreamEvent`s."""
        ...

    @abstractmethod
    async def health(self) -> bool: ...

    @abstractmethod
    async def list_models_raw(self) -> list[dict]:
        """Return the provider's native model entries (dicts, each with a name)."""
        ...

    async def list_models(self) -> list[str]:
        """Model names, derived from :meth:`list_models_raw`."""
        return [m.get("name", "") for m in await self.list_models_raw() if m.get("name")]

    @abstractmethod
    async def show_model(self, model: str) -> Optional[dict]: ...


# ---------------------------------------------------------------------------
# Runtime client
# ---------------------------------------------------------------------------

class RuntimeClient:
    def __init__(
        self,
        provider: Provider,
        *,
        queue: Optional[GenerationQueue] = None,
        cache: Optional[ModelCache] = None,
    ) -> None:
        self.provider = provider
        self.queue = queue or GenerationQueue()
        self.cache = cache or ModelCache()
        self._cancels = CancelRegistry()
        self._retries = settings.RUNTIME_RETRY_COUNT
        self._backoff = settings.RUNTIME_RETRY_BACKOFF
        self._gen_timeout = settings.OLLAMA_TIMEOUT

    # -- generation --------------------------------------------------------

    async def generate(
        self,
        model: str,
        prompt: str,
        *,
        timeout: Optional[float] = None,
        cancel_token: Optional[CancellationToken] = None,
        request_id: Optional[str] = None,
        retries: Optional[int] = None,
        options: Optional[dict] = None,
    ) -> GenerationResult:
        request_id = request_id or str(uuid4())
        token = self._cancels.register(request_id, cancel_token)
        gen_timeout = timeout or self._gen_timeout
        max_retries = self._retries if retries is None else retries

        metrics.record_start()
        log_op(logger, logging.INFO, "generation started", op="generate", model=model)
        try:
            async with self.queue.slot(model):
                attempt = 0
                while True:
                    token.raise_if_cancelled()
                    start = time.monotonic()
                    try:
                        # Pass sampling options only when supplied, so existing
                        # 2-arg providers/fakes are called exactly as before.
                        coro = (
                            self.provider.generate(model, prompt)
                            if options is None
                            else self.provider.generate(model, prompt, options=options)
                        )
                        result = await self._await_with_cancel(coro, token, gen_timeout)
                        result.latency_ms = int((time.monotonic() - start) * 1000)
                        metrics.record_complete(result.latency_ms, result.tokens_per_sec)
                        log_op(logger, logging.INFO, "generation completed", op="generate",
                               model=model, duration=result.latency_ms / 1000.0)
                        return result
                    except CancelledGeneration:
                        metrics.record_cancel()
                        log_op(logger, logging.INFO, "generation cancelled", op="generate", model=model)
                        raise
                    except GenerationTimeout:
                        metrics.record_fail()
                        log_op(logger, logging.WARNING, "generation timeout", op="generate", model=model)
                        raise
                    except (ConnectionFailure, ProviderUnavailable) as exc:
                        if attempt < max_retries:
                            attempt += 1
                            metrics.record_retry()
                            log_op(logger, logging.WARNING, f"retry {attempt} after {exc.code}",
                                   op="generate", model=model)
                            await asyncio.sleep(self._backoff * attempt)
                            continue
                        metrics.record_fail()
                        raise
        finally:
            self._cancels.discard(request_id)
            metrics.record_end()

    async def generate_stream(
        self,
        model: str,
        prompt: str,
        *,
        cancel_token: Optional[CancellationToken] = None,
        request_id: Optional[str] = None,
    ) -> AsyncIterator[StreamEvent]:
        request_id = request_id or str(uuid4())
        token = self._cancels.register(request_id, cancel_token)
        metrics.record_start()
        log_op(logger, logging.INFO, "stream started", op="stream", model=model)
        try:
            async with self.queue.slot(model):
                async for event in run_stream(self.provider, model, prompt, token=token):
                    yield event
            log_op(logger, logging.INFO, "stream closed", op="stream", model=model)
        finally:
            self._cancels.discard(request_id)
            metrics.record_end()

    # -- metadata (cached) -------------------------------------------------

    async def health(self) -> bool:
        return await self.provider.health()

    async def list_models_raw(self, *, use_cache: bool = True) -> list[dict]:
        if not use_cache:
            self.cache.invalidate()  # force a fresh fetch (e.g. health checks)
        return await self.cache.get_tags(self.provider.list_models_raw)

    async def list_models(self, *, use_cache: bool = True) -> list[str]:
        raw = await self.list_models_raw(use_cache=use_cache)
        return [m.get("name", "") for m in raw if m.get("name")]

    async def show_model(self, model: str) -> Optional[dict]:
        return await self.cache.get_show(model, lambda: self.provider.show_model(model))

    def invalidate_cache(self, model: Optional[str] = None) -> None:
        self.cache.invalidate(model)

    # -- cancellation ------------------------------------------------------

    def cancel(self, request_id: str) -> bool:
        return self._cancels.cancel(request_id)

    # -- internals ---------------------------------------------------------

    @staticmethod
    async def _await_with_cancel(coro, token: CancellationToken, timeout: float) -> GenerationResult:
        """Await ``coro`` but abort on cancellation or timeout."""
        task = asyncio.ensure_future(coro)
        cancel_task = asyncio.ensure_future(token.wait())
        done, _pending = await asyncio.wait(
            {task, cancel_task}, timeout=timeout, return_when=asyncio.FIRST_COMPLETED
        )
        if task in done:
            cancel_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await cancel_task
            return task.result()  # may raise a provider error

        # Cancelled or timed out — clean up the pending generation.
        task.cancel()
        cancel_task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task
        with contextlib.suppress(asyncio.CancelledError):
            await cancel_task
        if token.cancelled:
            raise CancelledGeneration("generation was cancelled")
        raise GenerationTimeout(f"generation exceeded {timeout}s")

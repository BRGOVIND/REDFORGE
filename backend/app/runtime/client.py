"""The unified runtime client and provider abstraction.

Everything that talks to an LLM goes through :class:`RuntimeClient`. It owns the
queue, cancellation, timeouts, retries, metrics, model cache, and logging, and
delegates the actual transport to a :class:`Provider`. Ollama is the only
provider today, but nothing above the provider layer knows that — adding
LM Studio / llama.cpp / vLLM / an OpenAI-compatible API is a new ``Provider``.

No raw ``httpx`` exception escapes this module: the provider maps them all to
:mod:`app.runtime.errors`.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from abc import ABC, abstractmethod
from typing import AsyncIterator, Optional
from uuid import uuid4

import httpx

from app.config import settings
from app.logging_config import get_logger, log_op
from app.runtime.cancel import CancellationToken, CancelRegistry
from app.runtime.errors import (
    CancelledGeneration,
    ConnectionFailure,
    GenerationTimeout,
    ModelNotFound,
    OllamaUnavailable,
    ProviderUnavailable,
    RuntimeLLMError,
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
    """A backend that can run generations. Implement one per LLM server."""

    name: str = "provider"

    @abstractmethod
    async def generate(self, model: str, prompt: str) -> GenerationResult: ...

    @abstractmethod
    def stream_generate(self, model: str, prompt: str) -> AsyncIterator[dict]:
        """Yield raw provider chunks (dicts). Streaming engine turns these into
        :class:`StreamEvent`s."""
        ...

    @abstractmethod
    async def health(self) -> bool: ...

    @abstractmethod
    async def list_models(self) -> list[str]: ...

    @abstractmethod
    async def show_model(self, model: str) -> Optional[dict]: ...


class OllamaProvider(Provider):
    name = "ollama"

    def __init__(self, base_url: Optional[str] = None) -> None:
        self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")

    def _timeout(self, read: float) -> httpx.Timeout:
        return httpx.Timeout(read, connect=settings.RUNTIME_CONNECT_TIMEOUT)

    @staticmethod
    def _map_error(exc: Exception, model: str = "") -> RuntimeLLMError:
        if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout)):
            return OllamaUnavailable(f"Ollama is offline or unreachable")
        if isinstance(exc, httpx.TimeoutException):
            return ConnectionFailure("Ollama request timed out")
        if isinstance(exc, httpx.HTTPStatusError):
            if exc.response.status_code == 404:
                return ModelNotFound(f"model '{model}' not found")
            return ProviderUnavailable(f"Ollama returned HTTP {exc.response.status_code}")
        return ProviderUnavailable(f"Ollama error: {exc}")

    async def generate(self, model: str, prompt: str) -> GenerationResult:
        start = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=self._timeout(settings.OLLAMA_TIMEOUT)) as client:
                resp = await client.post(
                    f"{self.base_url}/api/generate",
                    json={"model": model, "prompt": prompt, "stream": False},
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:  # noqa: BLE001 - normalize every transport error
            raise self._map_error(exc, model) from exc
        latency_ms = int((time.monotonic() - start) * 1000)
        return GenerationResult(
            model=model,
            text=data.get("response", ""),
            latency_ms=latency_ms,
            eval_count=data.get("eval_count"),
            done_reason=data.get("done_reason"),
        )

    async def stream_generate(self, model: str, prompt: str) -> AsyncIterator[dict]:
        try:
            async with httpx.AsyncClient(timeout=self._timeout(settings.OLLAMA_TIMEOUT)) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/api/generate",
                    json={"model": model, "prompt": prompt, "stream": True},
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line.strip():
                            continue
                        import json

                        yield json.loads(line)
        except Exception as exc:  # noqa: BLE001
            raise self._map_error(exc, model) from exc

    async def health(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=settings.OLLAMA_HEALTH_TIMEOUT) as client:
                resp = await client.get(f"{self.base_url}/api/version")
                return resp.status_code == 200
        except Exception:  # noqa: BLE001
            return False

    async def list_models(self) -> list[str]:
        try:
            async with httpx.AsyncClient(timeout=settings.OLLAMA_TAGS_TIMEOUT) as client:
                resp = await client.get(f"{self.base_url}/api/tags")
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:  # noqa: BLE001
            raise self._map_error(exc) from exc
        return [m.get("name", "") for m in data.get("models", []) if m.get("name")]

    async def show_model(self, model: str) -> Optional[dict]:
        try:
            async with httpx.AsyncClient(timeout=settings.OLLAMA_SHOW_TIMEOUT) as client:
                resp = await client.post(f"{self.base_url}/api/show", json={"name": model})
                resp.raise_for_status()
                return resp.json()
        except Exception:  # noqa: BLE001 - metadata is best-effort
            return None


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
                        result = await self._await_with_cancel(
                            self.provider.generate(model, prompt), token, gen_timeout
                        )
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

    async def list_models(self) -> list[str]:
        return await self.cache.get_tags(self.provider.list_models)

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

"""Optional, standard-library-only LLM call tracing for RedForge.

Instrumentation is explicit. This module never imports provider SDKs, patches
global objects, or contacts the server during construction.
"""
from __future__ import annotations

import asyncio
import contextlib
import contextvars
from itertools import islice
import json
import queue
import random
import re
import threading
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

_context: contextvars.ContextVar[dict[str, str]] = contextvars.ContextVar("redforge_trace_context", default={})
_secret = re.compile(r"(?i)(bearer\s+|sk-[a-z0-9_-]{8,}|api[_-]?key\s*[:=]\s*)[^\s,;]+")
_private = re.compile(r"(?i)(password|secret|token|authorization|api[_-]?key|cookie)")
_ids = {"request_id", "trace_id", "span_id", "parent_span_id", "conversation_id", "tenant_id", "user_id", "prompt_template_id", "prompt_version_id"}


def _get(obj: Any, *names: str) -> Any:
    for name in names:
        value = obj.get(name) if isinstance(obj, dict) else getattr(obj, name, None)
        if value is not None:
            return value
    return None


def _scrub(value: Any, limit: int) -> str | None:
    if value is None:
        return None
    try:
        def bounded(item: Any, depth: int = 0) -> Any:
            if isinstance(item, str):
                return item[:limit]
            if depth >= 3:
                return type(item).__name__
            if isinstance(item, dict):
                return {str(k)[:64]: "[REDACTED]" if _private.search(str(k)[:64]) else bounded(v, depth + 1)
                        for k, v in islice(item.items(), 16)}
            if isinstance(item, (tuple, list)):
                return [bounded(v, depth + 1) for v in item[:16]]
            return item if isinstance(item, (int, float, bool)) or item is None else type(item).__name__

        raw = value[:limit] if isinstance(value, str) else json.dumps(bounded(value), ensure_ascii=False)
    except Exception:
        raw = str(type(value).__name__)
    return _secret.sub("[REDACTED]", raw[:limit])


def _usage(response: Any) -> tuple[int | None, int | None, str | None]:
    usage = _get(response, "usage", "usage_metadata")
    if usage is None:
        return None, None, None
    inputs = _get(usage, "prompt_tokens", "input_tokens", "prompt_token_count")
    outputs = _get(usage, "completion_tokens", "output_tokens", "candidates_token_count")
    return inputs, outputs, "provider" if inputs is not None or outputs is not None else None


def _finish(response: Any) -> str | None:
    reason = _get(response, "stop_reason", "finish_reason")
    choices = _get(response, "choices")
    if reason is None and choices:
        reason = _get(choices[0], "finish_reason")
    candidates = _get(response, "candidates")
    if reason is None and candidates:
        reason = _get(candidates[0], "finish_reason")
    return str(reason)[:100] if reason is not None else None


class _Stream:
    def __init__(self, stream: Any, finish: Callable[[Any, str, BaseException | None], None]):
        self._stream = stream
        self._manager = stream
        self._finish = finish
        self._last = None
        self._last_usage = None
        self._done = False

    def __getattr__(self, key: str) -> Any:
        return getattr(self._stream, key)

    def _end(self, status: str, error: BaseException | None = None) -> None:
        if not self._done:
            self._done = True
            self._finish(self._last_usage or self._last, status, error)

    def __iter__(self):
        try:
            for chunk in self._stream:
                self._last = chunk
                if _usage(chunk)[2]:
                    self._last_usage = chunk
                yield chunk
        except BaseException as error:
            self._end("error", error)
            raise
        else:
            self._end("success")

    async def __aiter__(self):
        try:
            async for chunk in self._stream:
                self._last = chunk
                if _usage(chunk)[2]:
                    self._last_usage = chunk
                yield chunk
        except BaseException as error:
            self._end("error", error)
            raise
        else:
            self._end("success")

    def close(self):
        try:
            close = getattr(self._stream, "close", None)
            if close:
                return close()
        finally:
            self._end("cancelled")

    async def aclose(self):
        try:
            close = getattr(self._stream, "aclose", None)
            if close:
                return await close()
        finally:
            self._end("cancelled")

    def __enter__(self):
        enter = getattr(self._manager, "__enter__", None)
        if enter:
            self._stream = enter() or self._manager
        return self

    def __exit__(self, *exc):
        try:
            exit_method = getattr(self._manager, "__exit__", None)
            if exit_method:
                return exit_method(*exc)
        finally:
            self._end("error" if exc[0] else "cancelled")

    async def __aenter__(self):
        enter = getattr(self._manager, "__aenter__", None)
        if enter:
            self._stream = await enter() or self._manager
        return self

    async def __aexit__(self, *exc):
        try:
            exit_method = getattr(self._manager, "__aexit__", None)
            if exit_method:
                return await exit_method(*exc)
        finally:
            self._end("error" if exc[0] else "cancelled")


class _Path:
    def __init__(self, target: Any, tracer: "Tracer", provider: str, path: str = ""):
        self._target, self._tracer, self._provider, self._path = target, tracer, provider, path

    def __getattr__(self, name: str) -> Any:
        target = getattr(self._target, name)
        path = f"{self._path}.{name}" if self._path else name
        if callable(target) and name in {"create", "stream", "generate_content", "generate_content_stream"}:
            return lambda *args, **kwargs: self._tracer.observe(target, *args, provider=self._provider, operation=path,
                                                                  streaming=bool(kwargs.get("stream") or name in {"stream", "generate_content_stream"}), **kwargs)
        return _Path(target, self._tracer, self._provider, path) if not callable(target) else target


class Tracer:
    """Bounded, fire-and-forget telemetry. Call `flush()` before process exit."""

    def __init__(self, *, endpoint: str = "http://127.0.0.1:8000", token: str = "", enabled: bool = True,
                 service: str = "", environment: str = "", application_version: str = "", git_revision: str = "",
                 capture_content: bool = False, sample_rate: float = 1.0, max_payload: int = 4096,
                 queue_size: int = 256, timeout: float = 2.0, retries: int = 2,
                 metadata_allowlist: set[str] | None = None, metadata_denylist: set[str] | None = None,
                 capture_input: bool | None = None, capture_output: bool | None = None,
                 capture_metadata: bool | None = None, capture_errors: bool = False,
                 redact_keys: set[str] | None = None):
        if not 0 <= sample_rate <= 1 or queue_size < 1 or max_payload < 1 or timeout <= 0 or retries < 0:
            raise ValueError("Invalid tracer limits")
        self.endpoint = endpoint.rstrip("/") + "/api/v1/traces/events"
        self.token = token
        self.enabled = enabled
        self.service, self.environment = service[:120], environment[:80]
        self.application_version, self.git_revision = application_version[:80], git_revision[:80]
        self.capture_input = capture_content if capture_input is None else capture_input
        self.capture_output = capture_content if capture_output is None else capture_output
        self.capture_metadata = (metadata_allowlist is not None) if capture_metadata is None else capture_metadata
        self.capture_errors = capture_errors
        self.sample_rate, self.max_payload = sample_rate, min(max_payload, 4096)
        self.timeout, self.retries = timeout, retries
        self.metadata_allowlist, self.metadata_denylist = metadata_allowlist or set(), metadata_denylist or set()
        self.redact_keys = redact_keys or set()
        self._queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=queue_size)
        self._worker: threading.Thread | None = None
        self._lock = threading.Lock()
        self.dropped = 0

    @contextlib.contextmanager
    def context(self, **identifiers: str):
        invalid = identifiers.keys() - _ids
        if invalid:
            raise ValueError(f"Unknown trace identifiers: {', '.join(sorted(invalid))}")
        marker = _context.set({**_context.get(), **{k: str(v)[:128] for k, v in identifiers.items()}})
        try:
            yield
        finally:
            _context.reset(marker)

    def wrap(self, client: Any, provider: str) -> Any:
        """Explicit client wrapper. Supports OpenAI, Anthropic, Gemini SDK paths."""
        return _Path(client, self, provider)

    def _enqueue(self, event: dict[str, Any]) -> None:
        if not self.enabled or not self.token:
            return
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            self.dropped += 1
            return
        with self._lock:
            if self._worker is None or not self._worker.is_alive():
                self._worker = threading.Thread(target=self._run, name="redforge-telemetry", daemon=True)
                self._worker.start()

    def _run(self) -> None:
        while True:
            try:
                event = self._queue.get(timeout=0.2)
            except queue.Empty:
                return
            body = json.dumps({"events": [event]}, default=str).encode()
            req = urllib.request.Request(self.endpoint, body, {"Content-Type": "application/json", "Authorization": "Bearer " + self.token})
            try:
                for attempt in range(self.retries + 1):
                    try:
                        with urllib.request.urlopen(req, timeout=self.timeout):
                            break
                    except (urllib.error.URLError, TimeoutError, OSError):
                        if attempt < self.retries:
                            time.sleep(min(0.2 * 2 ** attempt, 1.0))
            finally:
                self._queue.task_done()

    def flush(self, timeout: float = 5.0) -> bool:
        """Wait for queued events up to timeout seconds; return False if still pending."""
        deadline = time.monotonic() + timeout
        while self._queue.unfinished_tasks and time.monotonic() < deadline:
            time.sleep(0.01)
        return self._queue.unfinished_tasks == 0

    def shutdown(self, timeout: float = 5.0) -> bool:
        self.enabled = False
        return self.flush(timeout)

    def observe(self, call: Callable, *args: Any, provider: str = "", model_name: str = "", operation: str = "generate",
                route: str = "", streaming: bool = False, trace_metadata: dict[str, Any] | None = None, **kwargs: Any) -> Any:
        """Call provider unchanged. Works with sync functions, coroutines, and streams."""
        if not self.enabled or not self.token or random.random() >= self.sample_rate:
            return call(*args, **kwargs)
        started = datetime.now(timezone.utc).isoformat()
        began = time.perf_counter()
        event: dict[str, Any] = {"event_id": str(uuid.uuid4()), "started_at": started, "provider": provider,
                                  "model": (model_name or str(kwargs.get("model", "")))[:200], "operation": operation[:80], "route": route[:240],
                                  "service": self.service, "environment": self.environment,
                                  "application_version": self.application_version, "git_revision": self.git_revision,
                                  **_context.get()}
        if self.capture_input:
            event["input_text"] = _scrub(kwargs.get("messages", kwargs.get("contents", kwargs.get("prompt", args[:1]))), self.max_payload)
        attrs = {}
        for key, value in islice((trace_metadata or {}).items(), 32) if self.capture_metadata else ():
            key = str(key)[:64]
            if _private.search(key) or key in self.redact_keys or key in self.metadata_denylist or key not in self.metadata_allowlist:
                continue
            if isinstance(value, (str, int, float, bool)) or value is None:
                attrs[key] = _scrub(value, 256) if isinstance(value, str) else value
        event["attributes"] = attrs

        def finish(response: Any, status: str, error: BaseException | None = None) -> None:
            try:
                event["duration_ms"] = round((time.perf_counter() - began) * 1000, 3)
                event["status"] = status
                event["input_tokens"], event["output_tokens"], event["usage_source"] = _usage(response)
                event["finish_reason"] = _finish(response)
                event["timed_out"] = bool(error and "timeout" in type(error).__name__.lower())
                if error:
                    event["error_category"] = type(error).__name__[:100]
                    if self.capture_errors:
                        event["error_detail"] = _scrub(str(error), 500)
                if self.capture_output and response is not None:
                    event["output_text"] = _scrub(_get(response, "output_text", "text", "content") or response, self.max_payload)
                self._enqueue(event)
            except Exception:
                # Telemetry is best effort; never replace a provider result or error.
                self.dropped += 1

        async def await_result(coroutine):
            try:
                result = await coroutine
            except BaseException as error:
                finish(None, "error", error)
                raise
            if streaming or hasattr(result, "__aiter__"):
                return _Stream(result, finish)
            finish(result, "success")
            return result

        try:
            result = call(*args, **kwargs)
        except BaseException as error:
            finish(None, "error", error)
            raise
        if asyncio.iscoroutine(result):
            return await_result(result)
        if streaming or hasattr(result, "__aiter__"):
            return _Stream(result, finish)
        finish(result, "success")
        return result

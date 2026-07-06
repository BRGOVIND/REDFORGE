"""Regression tests for the unified runtime (no real Ollama)."""
from __future__ import annotations

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from app.runtime.cancel import CancellationToken
from app.runtime.client import Provider, RuntimeClient
from app.runtime.errors import (
    CancelledGeneration,
    GenerationTimeout,
    ModelNotFound,
    OllamaUnavailable,
)
from app.runtime.metrics import metrics
from app.runtime.queue import GenerationQueue
from app.runtime.responses import GenerationResult, StreamEventKind


class FakeProvider(Provider):
    name = "fake"

    def __init__(self, *, fail=0, slow=0.0, stream_error=False, not_found=False):
        self.fail_remaining = fail        # number of leading calls that fail
        self.slow = slow
        self.stream_error = stream_error
        self.not_found = not_found
        self.calls = 0
        self.active = 0
        self.max_active = 0
        self.models = [{"name": "m1", "size": 1}, {"name": "m2", "size": 2}]

    async def generate(self, model, prompt):
        self.calls += 1
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            if self.not_found:
                raise ModelNotFound(f"{model} not found")
            if self.fail_remaining > 0:
                self.fail_remaining -= 1
                raise OllamaUnavailable("down")
            if self.slow:
                await asyncio.sleep(self.slow)
            return GenerationResult(model, f"echo:{prompt}", 5, eval_count=4)
        finally:
            self.active -= 1

    async def stream_generate(self, model, prompt):
        if self.stream_error:
            raise OllamaUnavailable("stream down")
        for tok in ["Hel", "lo"]:
            yield {"response": tok, "done": False}
        yield {"response": "", "done": True, "eval_count": 2}

    async def health(self):
        return True

    async def list_models_raw(self):
        self.calls += 1
        return self.models

    async def show_model(self, model):
        return {"model": model}


# --- generation ------------------------------------------------------------

@pytest.mark.asyncio
async def test_generate_basic():
    rc = RuntimeClient(FakeProvider(slow=0.02))  # non-zero latency for tokens/sec
    result = await rc.generate("m1", "hi")
    assert result.text == "echo:hi"
    assert result.eval_count == 4
    assert result.tokens_per_sec is not None


@pytest.mark.asyncio
async def test_model_not_found_propagates():
    rc = RuntimeClient(FakeProvider(not_found=True))
    with pytest.raises(ModelNotFound):
        await rc.generate("ghost", "hi")


# --- streaming -------------------------------------------------------------

@pytest.mark.asyncio
async def test_stream_yields_tokens_then_completion():
    rc = RuntimeClient(FakeProvider())
    events = [e async for e in rc.generate_stream("m1", "hi")]
    kinds = [e.kind for e in events]
    assert kinds[0] == StreamEventKind.TOKEN
    assert kinds[-1] == StreamEventKind.COMPLETION
    assert events[-1].result.text == "Hello"


@pytest.mark.asyncio
async def test_stream_falls_back_when_unavailable():
    # Streaming errors before any token → fall back to non-stream generate.
    rc = RuntimeClient(FakeProvider(stream_error=True))
    events = [e async for e in rc.generate_stream("m1", "hi")]
    assert events[-1].kind == StreamEventKind.COMPLETION
    assert events[-1].result.text == "echo:hi"


# --- timeouts & retries ----------------------------------------------------

@pytest.mark.asyncio
async def test_generation_timeout():
    rc = RuntimeClient(FakeProvider(slow=5.0))
    with pytest.raises(GenerationTimeout):
        await rc.generate("m1", "hi", timeout=0.1)


@pytest.mark.asyncio
async def test_retries_then_fails():
    provider = FakeProvider(fail=10)  # always fails
    rc = RuntimeClient(provider)
    with pytest.raises(OllamaUnavailable):
        await rc.generate("m1", "hi", retries=2)
    assert provider.calls == 3  # 1 initial + 2 retries


@pytest.mark.asyncio
async def test_retries_then_succeeds():
    provider = FakeProvider(fail=1)  # fail once, then succeed
    rc = RuntimeClient(provider)
    result = await rc.generate("m1", "hi", retries=2)
    assert result.text == "echo:hi"
    assert provider.calls == 2


# --- cancellation ----------------------------------------------------------

@pytest.mark.asyncio
async def test_cancellation_via_token():
    rc = RuntimeClient(FakeProvider(slow=5.0))
    token = CancellationToken()
    task = asyncio.ensure_future(rc.generate("m1", "hi", timeout=5, cancel_token=token))
    await asyncio.sleep(0.05)
    token.cancel()
    with pytest.raises(CancelledGeneration):
        await task


@pytest.mark.asyncio
async def test_cancellation_via_request_id():
    rc = RuntimeClient(FakeProvider(slow=5.0))
    task = asyncio.ensure_future(rc.generate("m1", "hi", timeout=5, request_id="req-1"))
    await asyncio.sleep(0.05)
    assert rc.cancel("req-1") is True
    with pytest.raises(CancelledGeneration):
        await task
    assert rc.cancel("req-1") is False  # discarded after completion


# --- queue -----------------------------------------------------------------

@pytest.mark.asyncio
async def test_queue_serializes_same_model():
    provider = FakeProvider(slow=0.1)
    rc = RuntimeClient(provider, queue=GenerationQueue(concurrency=1))
    await asyncio.gather(rc.generate("m1", "a"), rc.generate("m1", "b"))
    assert provider.max_active == 1  # never ran concurrently


@pytest.mark.asyncio
async def test_queue_parallel_across_models():
    provider = FakeProvider(slow=0.1)
    rc = RuntimeClient(provider, queue=GenerationQueue(concurrency=1))
    await asyncio.gather(rc.generate("m1", "a"), rc.generate("m2", "b"))
    assert provider.max_active == 2  # different models run in parallel


# --- cache -----------------------------------------------------------------

@pytest.mark.asyncio
async def test_model_cache_hit_and_invalidate():
    provider = FakeProvider()
    rc = RuntimeClient(provider)
    await rc.list_models()
    await rc.list_models()
    assert provider.calls == 1  # second call served from cache
    rc.invalidate_cache()
    await rc.list_models()
    assert provider.calls == 2  # refetched after invalidation


# --- metrics ---------------------------------------------------------------

@pytest.mark.asyncio
async def test_metrics_track_activity():
    before = metrics.snapshot()
    rc = RuntimeClient(FakeProvider())
    await rc.generate("m1", "hi")
    after = metrics.snapshot()
    assert after["total_requests"] == before["total_requests"] + 1
    assert after["completed_requests"] == before["completed_requests"] + 1
    assert after["active_requests"] == 0


@pytest.mark.asyncio
async def test_runtime_status_endpoint():
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/runtime/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["provider"] == "ollama"
    assert "metrics" in body
    assert "active_requests" in body["metrics"]

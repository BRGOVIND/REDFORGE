"""Token streaming engine.

Turns a provider's raw chunk stream into a clean sequence of
:class:`StreamEvent`s (``token`` → … → ``completion``). Consumers never touch
transport details. If streaming is unavailable or fails before any token
arrives, it falls back to a single non-streamed generation and emits one
``completion`` — graceful degradation, as required.
"""
from __future__ import annotations

import time
from typing import AsyncIterator

from app.logging_config import get_logger
from app.runtime.errors import CancelledGeneration, RuntimeLLMError
from app.runtime.metrics import metrics
from app.runtime.responses import GenerationResult, StreamEvent

logger = get_logger("runtime.stream")


async def run_stream(provider, model: str, prompt: str, *, token) -> AsyncIterator[StreamEvent]:
    start = time.monotonic()
    pieces: list[str] = []
    eval_count = None
    done_reason = None
    emitted = False

    try:
        async for chunk in provider.stream_generate(model, prompt):
            if token.cancelled:
                metrics.record_cancel()
                yield StreamEvent.was_cancelled()
                return
            piece = chunk.get("response", "")
            if piece:
                emitted = True
                pieces.append(piece)
                yield StreamEvent.of_token(piece, "".join(pieces))
            if chunk.get("done"):
                eval_count = chunk.get("eval_count")
                done_reason = chunk.get("done_reason")

        text = "".join(pieces)
        latency = int((time.monotonic() - start) * 1000)
        result = GenerationResult(model, text, latency, eval_count, done_reason)
        metrics.record_complete(latency, result.tokens_per_sec)
        yield StreamEvent.completed(result)

    except CancelledGeneration:
        metrics.record_cancel()
        yield StreamEvent.was_cancelled()

    except RuntimeLLMError as exc:
        # Streaming failed. If nothing was emitted yet, fall back to a single
        # non-streamed generation; otherwise surface the error.
        if emitted:
            metrics.record_fail()
            yield StreamEvent.failed(exc.message)
            return
        logger.info("streaming unavailable, falling back to non-stream generate")
        try:
            result = await provider.generate(model, prompt)
            metrics.record_complete(result.latency_ms, result.tokens_per_sec)
            yield StreamEvent.completed(result)
        except RuntimeLLMError as fallback_exc:
            metrics.record_fail()
            yield StreamEvent.failed(fallback_exc.message)

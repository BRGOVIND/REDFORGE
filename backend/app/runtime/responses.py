"""Provider-agnostic result and streaming event types."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class GenerationResult:
    model: str
    text: str
    latency_ms: int
    eval_count: Optional[int] = None       # tokens generated, if the provider reports it
    done_reason: Optional[str] = None

    @property
    def tokens_per_sec(self) -> Optional[float]:
        if self.eval_count and self.latency_ms > 0:
            return round(self.eval_count / (self.latency_ms / 1000.0), 2)
        return None


class StreamEventKind:
    TOKEN = "token"
    PARTIAL = "partial"
    COMPLETION = "completion"
    ERROR = "error"
    CANCELLED = "cancelled"


@dataclass
class StreamEvent:
    kind: str
    token: Optional[str] = None            # the newest token (TOKEN events)
    text: Optional[str] = None             # accumulated text so far (PARTIAL/COMPLETION)
    result: Optional[GenerationResult] = None  # final result (COMPLETION)
    error: Optional[str] = None            # message (ERROR)

    @classmethod
    def of_token(cls, token: str, text: str) -> "StreamEvent":
        return cls(kind=StreamEventKind.TOKEN, token=token, text=text)

    @classmethod
    def completed(cls, result: GenerationResult) -> "StreamEvent":
        return cls(kind=StreamEventKind.COMPLETION, text=result.text, result=result)

    @classmethod
    def failed(cls, error: str) -> "StreamEvent":
        return cls(kind=StreamEventKind.ERROR, error=error)

    @classmethod
    def was_cancelled(cls) -> "StreamEvent":
        return cls(kind=StreamEventKind.CANCELLED)

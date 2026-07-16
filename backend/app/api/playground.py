"""AI Playground — chat generation (RedForge V2, Phase 1).

Every generation flows through the **Runtime Manager / provider abstraction** —
the default shared ``RuntimeClient`` for the active provider, or a transient one
built from the provider registry when the Playground selects a different
provider. No provider is ever called directly, and no provider logic is
duplicated here.

Phase 1 is non-streaming (single request → full completion). Sampling params are
passed through the runtime's optional ``options`` channel to whichever provider
supports them. Token streaming (SSE) is the documented next step.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.runtime import manager
from app.runtime.client import RuntimeClient
from app.runtime.errors import RuntimeLLMError
from app.runtime.manager import get_runtime

router = APIRouter(prefix="/api/playground", tags=["playground"])


class Message(BaseModel):
    role: str  # "user" | "assistant" | "system"
    content: str


class ChatRequest(BaseModel):
    model: str
    messages: list[Message]
    provider: Optional[str] = None            # None → active default provider
    system: Optional[str] = None
    temperature: Optional[float] = Field(None, ge=0, le=2)
    top_p: Optional[float] = Field(None, ge=0, le=1)
    max_tokens: Optional[int] = Field(None, ge=1, le=32000)
    seed: Optional[int] = None


class ChatResponse(BaseModel):
    response: str
    model: str
    provider: str
    latency_ms: int
    eval_count: Optional[int] = None


def _runtime_for(provider: Optional[str]) -> tuple[RuntimeClient, str]:
    """Reuse the shared client for the default provider; build a transient one for
    any other registered provider (same registry, same RuntimeClient plumbing)."""
    default = manager.settings.RUNTIME_PROVIDER.lower()
    name = (provider or default).lower()
    if name == default:
        return get_runtime(), name
    if name not in manager._PROVIDERS:
        raise HTTPException(status_code=400, detail=f"unknown provider '{name}'")
    return RuntimeClient(manager.build_provider(name)), name


def _compose_prompt(messages: list[Message]) -> str:
    """Flatten the conversation into a single prompt (the provider interface is
    prompt-based). Role-tagged so the model keeps turn context."""
    parts: list[str] = []
    for m in messages:
        if m.role == "system":
            continue  # system goes through options, not the prompt body
        tag = "User" if m.role == "user" else "Assistant"
        parts.append(f"{tag}: {m.content}")
    parts.append("Assistant:")
    return "\n".join(parts)


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    if not req.messages:
        raise HTTPException(status_code=422, detail="messages must not be empty")

    runtime, provider_name = _runtime_for(req.provider)
    system = req.system or next((m.content for m in req.messages if m.role == "system"), None)
    options = {
        "system": system,
        "temperature": req.temperature,
        "top_p": req.top_p,
        "max_tokens": req.max_tokens,
        "seed": req.seed,
    }
    options = {k: v for k, v in options.items() if v is not None}
    prompt = _compose_prompt(req.messages)

    try:
        result = await runtime.generate(req.model, prompt, options=options or None)
    except RuntimeLLMError as exc:
        status = exc.http_status if exc.http_status in (404, 503, 504) else 502
        raise HTTPException(status_code=status, detail=exc.message) from exc

    return ChatResponse(
        response=result.text,
        model=req.model,
        provider=provider_name,
        latency_ms=result.latency_ms,
        eval_count=result.eval_count,
    )

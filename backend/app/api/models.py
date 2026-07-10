import time
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from app.runtime.errors import RuntimeLLMError
from app.runtime.manager import get_runtime

router = APIRouter(prefix="/api/models", tags=["models"])


class ModelInfo(BaseModel):
    name: str
    size: int
    modified_at: str
    digest: str


class PingResult(BaseModel):
    model: str
    online: bool
    latency_ms: Optional[float] = None
    error: Optional[str] = None


@router.get("")
async def list_models():
    try:
        raw = await get_runtime().list_models_raw()
    except RuntimeLLMError as exc:
        # Provider-agnostic: the runtime may be Ollama or any registered provider.
        return {
            "error": "The runtime provider is offline",
            "detail": exc.message or "Cannot reach the active runtime provider. Ensure it is running.",
            "models": [],
        }
    models = [
        ModelInfo(
            name=m["name"],
            size=m.get("size", 0),
            modified_at=m.get("modified_at", ""),
            digest=m.get("digest", ""),
        )
        for m in raw
        if m.get("name")
    ]
    return {"models": models}


@router.post("/{model_name}/ping")
async def ping_model(model_name: str):
    start = time.monotonic()
    try:
        await get_runtime().generate(model_name, "Hi")
        latency_ms = (time.monotonic() - start) * 1000
        return PingResult(model=model_name, online=True, latency_ms=round(latency_ms, 2))
    except RuntimeLLMError as exc:
        return PingResult(model=model_name, online=False, error=exc.message)
    except Exception as exc:  # noqa: BLE001
        return PingResult(model=model_name, online=False, error=str(exc))

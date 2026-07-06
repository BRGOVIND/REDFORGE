import time
from typing import Optional

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

from app.config import settings

router = APIRouter(prefix="/api/models", tags=["models"])

OLLAMA_BASE_URL = settings.OLLAMA_BASE_URL
OLLAMA_TIMEOUT = settings.OLLAMA_TAGS_TIMEOUT


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
        async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT) as client:
            response = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            response.raise_for_status()
            data = response.json()
            models = [
                ModelInfo(
                    name=m["name"],
                    size=m["size"],
                    modified_at=m["modified_at"],
                    digest=m["digest"],
                )
                for m in data.get("models", [])
            ]
            return {"models": models}
    except (httpx.ConnectError, httpx.TimeoutException):
        return {
            "error": "Ollama is offline",
            "detail": "Cannot connect to Ollama at localhost:11434. Ensure Ollama is running.",
            "models": [],
        }


@router.post("/{model_name}/ping")
async def ping_model(model_name: str):
    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT) as client:
            response = await client.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json={"model": model_name, "prompt": "Hi", "stream": False},
            )
            response.raise_for_status()
            latency_ms = (time.monotonic() - start) * 1000
            return PingResult(model=model_name, online=True, latency_ms=round(latency_ms, 2))
    except (httpx.ConnectError, httpx.TimeoutException) as e:
        return PingResult(model=model_name, online=False, error=str(e))
    except httpx.HTTPStatusError as e:
        return PingResult(model=model_name, online=False, error=f"HTTP {e.response.status_code}: {e.response.text}")
    except Exception as e:
        return PingResult(model=model_name, online=False, error=str(e))

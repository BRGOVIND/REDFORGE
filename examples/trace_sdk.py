"""Local development example. Install `pip install -e .` at repo root first."""
import os

from redforge.observability import Tracer


def local_model(prompt: str) -> dict:
    # Replace with an Ollama, LM Studio, vLLM, or hosted provider call.
    return {"text": f"Echo: {prompt}", "usage": {"input_tokens": 2, "output_tokens": 3}}


tracer = Tracer(
    endpoint=os.getenv("REDFORGE_URL", "http://127.0.0.1:8000"),
    token=os.getenv("REDFORGE_TRACE_TOKEN", ""),
    service="example-app",
    environment="development",
    capture_content=False,
)

with tracer.context(trace_id="demo-trace", conversation_id="demo-conversation"):
    result = tracer.observe(local_model, "Hello", provider="local", model_name="example", operation="generate")
    print(result)

tracer.flush()

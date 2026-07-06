"""Runtime-specific exceptions.

No raw ``httpx`` exception ever escapes the runtime — the provider layer maps
every transport failure to one of these. Each carries a stable ``code`` so the
API error envelope and logs are consistent regardless of the underlying
provider (Ollama today, others tomorrow).
"""
from __future__ import annotations


class RuntimeLLMError(Exception):
    """Base class for every runtime error."""

    code = "runtime_error"
    http_status = 503

    def __init__(self, message: str = "", *, details: object = None) -> None:
        super().__init__(message or self.__class__.__name__)
        self.message = message or self.__class__.__name__
        self.details = details


class ProviderUnavailable(RuntimeLLMError):
    """The backing provider is offline or unreachable."""

    code = "provider_unavailable"
    http_status = 503


class OllamaUnavailable(ProviderUnavailable):
    """Ollama specifically is offline/unreachable."""

    code = "ollama_unavailable"


class ConnectionFailure(ProviderUnavailable):
    """A transient connection error (candidate for retry)."""

    code = "connection_failure"


class ModelNotFound(RuntimeLLMError):
    code = "model_not_found"
    http_status = 404


class GenerationTimeout(RuntimeLLMError):
    code = "generation_timeout"
    http_status = 504


class CancelledGeneration(RuntimeLLMError):
    code = "cancelled"
    http_status = 499  # client closed request (nginx convention)


class StreamingFailure(RuntimeLLMError):
    code = "streaming_failure"
    http_status = 502

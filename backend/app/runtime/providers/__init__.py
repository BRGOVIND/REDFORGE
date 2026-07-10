"""Runtime providers.

Each provider implements the :class:`~app.runtime.client.Provider` interface and
nothing else — all shared concerns (queue, retries, metrics, cancellation,
streaming assembly) stay in :class:`~app.runtime.client.RuntimeClient`.

``BUILTIN_PROVIDERS`` is the one place providers are registered. To add a
provider: create the class (usually a subclass of an existing family base), then
add one line here (or call :func:`app.runtime.manager.register_provider` at
runtime). No engine code changes.
"""
from __future__ import annotations

from app.runtime.client import Provider
from app.runtime.providers.anthropic import AnthropicProvider
from app.runtime.providers.base import HttpProvider
from app.runtime.providers.gemini import GeminiProvider
from app.runtime.providers.ollama import OllamaProvider
from app.runtime.providers.openai_compat import (
    GroqProvider,
    LlamaCppProvider,
    LMStudioProvider,
    OpenAICompatibleProvider,
    OpenAIProvider,
    OpenRouterProvider,
    VLLMProvider,
    # wire helpers re-exported for tests / reuse:
    _normalize_models,
    _parse_chat_completion,
    _parse_sse_line,
)

# name (the value of REDFORGE_RUNTIME_PROVIDER) → provider class.
BUILTIN_PROVIDERS: dict[str, type[Provider]] = {
    OllamaProvider.name: OllamaProvider,
    LMStudioProvider.name: LMStudioProvider,
    LlamaCppProvider.name: LlamaCppProvider,
    VLLMProvider.name: VLLMProvider,
    OpenAIProvider.name: OpenAIProvider,
    AnthropicProvider.name: AnthropicProvider,
    GeminiProvider.name: GeminiProvider,
    GroqProvider.name: GroqProvider,
    OpenRouterProvider.name: OpenRouterProvider,
}

__all__ = [
    "BUILTIN_PROVIDERS",
    "HttpProvider",
    "OpenAICompatibleProvider",
    "OllamaProvider",
    "LMStudioProvider",
    "LlamaCppProvider",
    "VLLMProvider",
    "OpenAIProvider",
    "AnthropicProvider",
    "GeminiProvider",
    "GroqProvider",
    "OpenRouterProvider",
    "_normalize_models",
    "_parse_chat_completion",
    "_parse_sse_line",
]

"""LLM provider abstraction layer."""

from codecraft.llm.base import LLMFallbackProvider, LLMMessage, LLMProvider, LLMResponse, LLMToolDefinition, LLMProviderRegistry
from codecraft.llm.openai import OpenAIProvider
from codecraft.llm.openrouter import OpenRouterProvider
from codecraft.llm.ollama import OllamaProvider
from codecraft.llm.groq import GroqProvider
from codecraft.llm.gemini import GeminiProvider

registry = LLMProviderRegistry()
registry.register("openai", OpenAIProvider)
registry.register("openrouter", OpenRouterProvider)
registry.register("ollama", OllamaProvider)
registry.register("groq", GroqProvider)
registry.register("gemini", GeminiProvider)


def create_provider(
    name: str = "openai",
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 16384,
) -> LLMProvider:
    return registry.get_provider(name, model=model, temperature=temperature, max_tokens=max_tokens)


def create_fallback_provider(
    names: list[str] | None = None,
    temperature: float = 0.7,
    max_tokens: int = 16384,
) -> LLMFallbackProvider:
    from codecraft.config import settings

    names = names or settings.llm.fallback_chain
    providers: list[LLMProvider] = []
    for n in names:
        try:
            providers.append(create_provider(n, temperature=temperature, max_tokens=max_tokens))
        except Exception:
            pass
    return LLMFallbackProvider(providers=providers, fallback_chain=names)


__all__ = [
    "LLMProvider",
    "LLMFallbackProvider",
    "LLMMessage",
    "LLMResponse",
    "LLMToolDefinition",
    "LLMProviderRegistry",
    "OpenAIProvider",
    "OpenRouterProvider",
    "OllamaProvider",
    "GroqProvider",
    "GeminiProvider",
    "registry",
    "create_provider",
    "create_fallback_provider",
]

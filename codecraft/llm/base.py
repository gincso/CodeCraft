from __future__ import annotations

import abc
import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Optional

import tiktoken

logger = logging.getLogger(__name__)


def _normalize_tools(tools: Any) -> list[dict[str, Any]]:
    if not tools:
        return []
    result: list[dict[str, Any]] = []
    for t in tools:
        if isinstance(t, dict):
            result.append(t)
        elif hasattr(t, "to_dict"):
            result.append(t.to_dict())
    return result


@dataclass
class LLMMessage:
    role: str
    content: str | list[dict[str, Any]]
    name: Optional[str] = None
    tool_call_id: Optional[str] = None
    tool_calls: Optional[list[dict[str, Any]]] = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.name:
            d["name"] = self.name
        if self.tool_call_id:
            d["tool_call_id"] = self.tool_call_id
        if self.tool_calls:
            d["tool_calls"] = self.tool_calls
        return d


@dataclass
class LLMResponse:
    content: str
    model: str
    usage: dict[str, int] = field(default_factory=dict)
    finish_reason: str = "stop"
    tool_calls: Optional[list[dict[str, Any]]] = None

    @property
    def total_tokens(self) -> int:
        return self.usage.get("total_tokens", 0)


@dataclass
class LLMToolDefinition:
    name: str
    description: str
    parameters: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class LLMProvider(abc.ABC):
    name: str = "base"
    default_model: str = ""

    def __init__(self, model: Optional[str] = None, temperature: float = 0.7, max_tokens: int = 16384):
        self.model = model or self.default_model
        self.temperature = temperature
        self.max_tokens = max_tokens

    @abc.abstractmethod
    async def complete(
        self,
        messages: list[LLMMessage],
        tools: Optional[list[LLMToolDefinition]] = None,
        stream: bool = False,
    ) -> LLMResponse | AsyncIterator[str]:
        ...

    @abc.abstractmethod
    async def list_models(self) -> list[str]:
        ...

    def count_tokens(self, text: str, model: str = "gpt-4o") -> int:
        try:
            enc = tiktoken.encoding_for_model(model)
        except KeyError:
            enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))

    def supports_tools(self) -> bool:
        return True

    def supports_vision(self) -> bool:
        return False

    async def health_check(self) -> bool:
        try:
            models = await self.list_models()
            return len(models) > 0
        except Exception:
            return False


class LLMProviderRegistry:
    def __init__(self):
        self._providers: dict[str, type[LLMProvider]] = {}
        self._instances: dict[str, LLMProvider] = {}

    def register(self, name: str, provider_cls: type[LLMProvider]) -> None:
        self._providers[name] = provider_cls

    def get_provider(self, name: str, **kwargs: Any) -> LLMProvider:
        if name in self._instances:
            return self._instances[name]
        if name not in self._providers:
            raise ValueError(f"Unknown provider: {name}. Available: {list(self._providers)}")
        instance = self._providers[name](**kwargs)
        self._instances[name] = instance
        return instance

    def list_providers(self) -> list[str]:
        return list(self._providers.keys())

    @property
    def providers(self) -> dict[str, type[LLMProvider]]:
        return dict(self._providers)


class LLMFallbackProvider(LLMProvider):
    name = "fallback"

    def __init__(
        self,
        providers: list[LLMProvider],
        fallback_chain: Optional[list[str]] = None,
        **kwargs: Any,
    ):
        super().__init__(**kwargs)
        self._providers = {p.name: p for p in providers}
        self._chain = fallback_chain or list(self._providers.keys())
        self._primary = self._providers.get(self._chain[0]) if self._chain else None

    async def complete(
        self,
        messages: list[LLMMessage],
        tools: Optional[list[LLMToolDefinition]] = None,
        stream: bool = False,
    ) -> LLMResponse | AsyncIterator[str]:
        last_error: Optional[Exception] = None
        for provider_name in self._chain:
            provider = self._providers.get(provider_name)
            if not provider:
                continue
            try:
                logger.info(f"Trying provider: {provider_name}")
                return await provider.complete(messages, tools, stream)
            except Exception as e:
                logger.warning(f"Provider {provider_name} failed: {e}")
                last_error = e
                await asyncio.sleep(1)
        raise RuntimeError(f"All providers failed. Last error: {last_error}")

    async def list_models(self) -> list[str]:
        models: list[str] = []
        for provider in self._providers.values():
            try:
                models.extend(await provider.list_models())
            except Exception:
                pass
        return models

    async def health_check(self) -> bool:
        for provider in self._providers.values():
            if await provider.health_check():
                return True
        return False

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator, Optional

import httpx

from codecraft.llm.base import LLMMessage, LLMProvider, LLMResponse, LLMToolDefinition, _normalize_tools
from codecraft.config import settings

logger = logging.getLogger(__name__)


class GroqProvider(LLMProvider):
    name = "groq"
    default_model = "llama-3.1-70b-versatile"

    def __init__(self, model: Optional[str] = None, temperature: float = 0.7, max_tokens: int = 16384):
        super().__init__(model, temperature, max_tokens)
        self.api_key = settings.llm.groq_api_key or ""
        self.base_url = settings.llm.groq_base_url.rstrip("/")
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=httpx.Timeout(settings.llm.request_timeout),
            )
        return self._client

    async def complete(
        self,
        messages: list[LLMMessage],
        tools: Optional[list[LLMToolDefinition]] = None,
        stream: bool = False,
    ) -> LLMResponse | AsyncIterator[str]:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [m.to_dict() for m in messages],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": stream,
        }
        if tools:
            body["tools"] = _normalize_tools(tools)
            body["tool_choice"] = "auto"

        if stream:
            return self._stream(body)
        return await self._sync_complete(body)

    async def _sync_complete(self, body: dict[str, Any]) -> LLMResponse:
        resp = await self.client.post("/chat/completions", json=body)
        resp.raise_for_status()
        data = resp.json()
        choice = data["choices"][0]
        message = choice["message"]
        return LLMResponse(
            content=message.get("content", "") or "",
            model=data.get("model", self.model),
            usage=data.get("usage", {}),
            finish_reason=choice.get("finish_reason", "stop"),
            tool_calls=message.get("tool_calls"),
        )

    async def _stream(self, body: dict[str, Any]) -> AsyncIterator[str]:
        async def gen():
            async with self.client.stream("POST", "/chat/completions", json=body) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                            delta = chunk["choices"][0].get("delta", {})
                            if "content" in delta and delta["content"]:
                                yield delta["content"]
                        except json.JSONDecodeError:
                            continue
        return gen()

    async def list_models(self) -> list[str]:
        try:
            resp = await self.client.get("/models")
            resp.raise_for_status()
            data = resp.json()
            return [m["id"] for m in data.get("data", [])]
        except Exception:
            return [self.model]

    def supports_tools(self) -> bool:
        return True

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

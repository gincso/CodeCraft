from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator, Optional

import httpx

from codecraft.llm.base import LLMMessage, LLMProvider, LLMResponse, LLMToolDefinition
from codecraft.config import settings

logger = logging.getLogger(__name__)


class OllamaProvider(LLMProvider):
    name = "ollama"
    default_model = "llama3"

    def __init__(self, model: Optional[str] = None, temperature: float = 0.7, max_tokens: int = 16384):
        super().__init__(model, temperature, max_tokens)
        self.base_url = settings.llm.ollama_host.rstrip("/")
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
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
            "stream": stream,
            "options": {
                "temperature": self.temperature,
                "num_predict": self.max_tokens,
            },
        }
        if tools:
            body["tools"] = [t.to_dict() for t in tools]

        if stream:
            return self._stream(body)
        return await self._sync_complete(body)

    async def _sync_complete(self, body: dict[str, Any]) -> LLMResponse:
        resp = await self.client.post("/api/chat", json=body)
        resp.raise_for_status()
        data = resp.json()
        return LLMResponse(
            content=data.get("message", {}).get("content", ""),
            model=data.get("model", self.model),
            usage={
                "prompt_tokens": data.get("prompt_eval_count", 0),
                "completion_tokens": data.get("eval_count", 0),
                "total_tokens": data.get("prompt_eval_count", 0) + data.get("eval_count", 0),
            },
        )

    async def _stream(self, body: dict[str, Any]) -> AsyncIterator[str]:
        async def gen():
            async with self.client.stream("POST", "/api/chat", json=body) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    try:
                        chunk = json.loads(line)
                        content = chunk.get("message", {}).get("content", "")
                        if content:
                            yield content
                    except json.JSONDecodeError:
                        continue
        return gen()

    async def list_models(self) -> list[str]:
        try:
            resp = await self.client.get("/api/tags")
            resp.raise_for_status()
            data = resp.json()
            return [m["name"] for m in data.get("models", [])]
        except Exception:
            return [self.model]

    def supports_tools(self) -> bool:
        return False

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

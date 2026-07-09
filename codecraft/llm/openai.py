from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator, Optional

import httpx

from codecraft.llm.base import LLMMessage, LLMProvider, LLMResponse, LLMToolDefinition, _normalize_tools
from codecraft.config import settings

logger = logging.getLogger(__name__)


class OpenAIProvider(LLMProvider):
    name = "openai"
    default_model = "gpt-4o"

    def __init__(self, model: Optional[str] = None, temperature: float = 0.7, max_tokens: int = 16384):
        super().__init__(model, temperature, max_tokens)
        self.api_key = settings.llm.openai_api_key or ""
        self.admin_key = settings.llm.openai_admin_key or ""
        self.base_url = (settings.llm.openai_base_url or "https://api.openai.com/v1").rstrip("/")
        self._client: Optional[httpx.AsyncClient] = None
        self._current_key: str = self.api_key

    def _get_client(self, key: str) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(settings.llm.request_timeout),
        )

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = self._get_client(self._current_key)
        return self._client

    async def _try_complete(self, body: dict[str, Any], stream: bool) -> tuple[Any, str]:
        last_error = None
        for key in [self.api_key, self.admin_key]:
            if not key or key == self._current_key:
                continue
            self._current_key = key
            if self._client:
                await self._client.aclose()
                self._client = None
            try:
                if stream:
                    return await self._do_stream(body), key
                return await self._do_sync_complete(body), key
            except Exception as e:
                last_error = e
                continue
        raise last_error or RuntimeError("No working OpenAI key")

    async def _do_sync_complete(self, body: dict[str, Any]) -> LLMResponse:
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

    async def _ensure_tools(self, tools: Any) -> list[dict[str, Any]]:
        return _normalize_tools(tools)

    async def complete(
        self,
        messages: list[LLMMessage],
        tools: Optional[list[Any]] = None,
        stream: bool = False,
    ) -> LLMResponse | AsyncIterator[str]:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [m.to_dict() for m in messages],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": stream,
        }
        tool_defs = _normalize_tools(tools)
        if tool_defs:
            body["tools"] = tool_defs
            body["tool_choice"] = "auto"

        try:
            if stream:
                result, _ = await self._try_complete(body, stream=True)
                return result
            result, _ = await self._try_complete(body, stream=False)
            return result
        except Exception:
            pass

        if stream:
            return self._do_stream(body)
        return await self._do_sync_complete(body)

    async def _do_stream(self, body: dict[str, Any]) -> AsyncIterator[str]:
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

    def supports_vision(self) -> bool:
        return self.model in ("gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-4-vision-preview")

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

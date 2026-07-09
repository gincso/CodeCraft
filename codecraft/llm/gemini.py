from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator, Optional

import httpx

from codecraft.llm.base import LLMMessage, LLMProvider, LLMResponse, LLMToolDefinition, _normalize_tools
from codecraft.config import settings

logger = logging.getLogger(__name__)


class GeminiProvider(LLMProvider):
    name = "gemini"
    default_model = "gemini-2.0-flash"

    def __init__(self, model: Optional[str] = None, temperature: float = 0.7, max_tokens: int = 16384):
        super().__init__(model, temperature, max_tokens)
        self.api_key = settings.llm.gemini_api_key or ""
        self._client: Optional[httpx.AsyncClient] = None
        self._base_url = "https://generativelanguage.googleapis.com/v1beta"

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(settings.llm.request_timeout),
            )
        return self._client

    async def complete(
        self,
        messages: list[LLMMessage],
        tools: Optional[list[LLMToolDefinition]] = None,
        stream: bool = False,
    ) -> LLMResponse | AsyncIterator[str]:
        contents = self._convert_messages(messages)
        body: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": self.temperature,
                "maxOutputTokens": self.max_tokens,
            },
        }
        if tools:
            body["tools"] = [{"functionDeclarations": [self._convert_tool(t) for t in tools]}]

        if stream:
            return self._stream(body)
        return await self._sync_complete(body)

    def _convert_messages(self, messages: list[LLMMessage]) -> list[dict[str, Any]]:
        contents: list[dict[str, Any]] = []
        for m in messages:
            if m.role == "system":
                if contents:
                    contents[0]["parts"].insert(0, {"text": f"[System: {m.content}]\n"})
                else:
                    contents.append({"role": "user", "parts": [{"text": f"[System: {m.content}]"}]})
            elif m.role == "user":
                contents.append({"role": "user", "parts": [{"text": m.content if isinstance(m.content, str) else ""}]})
            elif m.role == "assistant":
                parts: list[dict[str, Any]] = []
                if m.content:
                    parts.append({"text": m.content if isinstance(m.content, str) else ""})
                if m.tool_calls:
                    for tc in m.tool_calls:
                        parts.append({
                            "functionCall": {
                                "name": tc["function"]["name"],
                                "args": json.loads(tc["function"]["arguments"]) if isinstance(tc["function"]["arguments"], str) else tc["function"]["arguments"],
                            }
                        })
                contents.append({"role": "model", "parts": parts or [{"text": ""}]})
            elif m.role == "tool":
                contents.append({
                    "role": "function",
                    "parts": [{
                        "functionResponse": {
                            "name": m.name or "unknown",
                            "response": {"output": m.content},
                        }
                    }]
                })
        return contents

    def _convert_tool(self, tool: LLMToolDefinition) -> dict[str, Any]:
        return {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        }

    async def _sync_complete(self, body: dict[str, Any]) -> LLMResponse:
        url = f"{self._base_url}/models/{self.model}:generateContent"
        params = {"key": self.api_key} if self.api_key else {}
        resp = await self.client.post(url, json=body, params=params)
        resp.raise_for_status()
        data = resp.json()

        candidates = data.get("candidates", [])
        if not candidates:
            return LLMResponse(content="", model=self.model, usage={})

        candidate = candidates[0]
        content = candidate.get("content", {})
        parts = content.get("parts", [])

        text_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        for part in parts:
            if "text" in part:
                text_parts.append(part["text"])
            if "functionCall" in part:
                tool_calls.append({
                    "id": f"call_{len(tool_calls)}",
                    "type": "function",
                    "function": {
                        "name": part["functionCall"]["name"],
                        "arguments": json.dumps(part["functionCall"].get("args", {})),
                    },
                })

        usage_data = data.get("usageMetadata", {})
        return LLMResponse(
            content="\n".join(text_parts),
            model=self.model,
            usage={
                "prompt_tokens": usage_data.get("promptTokenCount", 0),
                "completion_tokens": usage_data.get("candidatesTokenCount", 0),
                "total_tokens": usage_data.get("totalTokenCount", 0),
            },
            finish_reason=candidate.get("finishReason", "STOP"),
            tool_calls=tool_calls if tool_calls else None,
        )

    async def _stream(self, body: dict[str, Any]) -> AsyncIterator[str]:
        url = f"{self._base_url}/models/{self.model}:streamGenerateContent"
        params = {"key": self.api_key, "alt": "sse"} if self.api_key else {"alt": "sse"}
        body["generationConfig"] = body.get("generationConfig", {})
        body["generationConfig"]["stream"] = True

        async def gen():
            async with self.client.stream("POST", url, json=body, params=params) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        try:
                            chunk = json.loads(line[6:])
                            candidates = chunk.get("candidates", [])
                            for c in candidates:
                                parts = c.get("content", {}).get("parts", [])
                                for part in parts:
                                    if "text" in part:
                                        yield part["text"]
                        except json.JSONDecodeError:
                            continue
        return gen()

    async def list_models(self) -> list[str]:
        try:
            url = f"{self._base_url}/models"
            params = {"key": self.api_key} if self.api_key else {}
            resp = await self.client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            return [m["name"].split("/")[-1] for m in data.get("models", []) if "generateContent" in m.get("supportedGenerationMethods", [])]
        except Exception:
            return [self.model]

    def supports_tools(self) -> bool:
        return True

    def supports_vision(self) -> bool:
        return "vision" in self.model.lower()

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

from __future__ import annotations

import abc
import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Callable, Optional

from codecraft.llm.base import (
    LLMFallbackProvider,
    LLMMessage,
    LLMProvider,
    LLMResponse,
    LLMToolDefinition,
)
from codecraft.tools.base import BaseTool, ToolRegistry, ToolResult
from codecraft.config import settings

logger = logging.getLogger(__name__)


@dataclass
class AgentContext:
    run_id: str
    project_id: str
    project_name: str
    project_description: str
    workdir: str
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseAgent(abc.ABC):
    name: str = "base"
    description: str = "Base agent"
    system_prompt: str = "You are a helpful AI agent."
    default_model: str = "gpt-4o"

    def __init__(
        self,
        provider: Optional[LLMProvider] = None,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_turns: int = 30,
    ):
        self.model = model or getattr(self, "default_model", "gpt-4o")
        self.temperature = temperature
        self.max_turns = max_turns
        self._provider = provider
        self._tools = ToolRegistry()
        self._messages: list[LLMMessage] = []
        self._turn_count = 0
        self._context: Optional[AgentContext] = None
        self._handlers: list[Callable[[str, dict[str, Any]], None]] = []
        self._memory = None
        self._manager: Any = None
        self._approval_handler: Optional[Callable] = None

    @property
    def provider(self) -> LLMProvider:
        if self._provider is None:
            from codecraft.llm.openai import OpenAIProvider
            self._provider = OpenAIProvider(model=self.model, temperature=self.temperature)
        return self._provider

    @provider.setter
    def provider(self, p: LLMProvider) -> None:
        self._provider = p

    def set_context(self, ctx: AgentContext) -> None:
        self._context = ctx
        if ctx.workdir:
            for tool in self._tools._tools.values():
                tool.workdir = ctx.workdir

    @property
    def memory(self):
        if self._memory is None:
            from codecraft.memory import get_memory
            self._memory = get_memory()
        return self._memory

    def enable_memory(self) -> None:
        _ = self.memory

    def on_event(self, handler: Callable[[str, dict[str, Any]], None]) -> None:
        self._handlers.append(handler)

    def _emit(self, event: str, data: dict[str, Any]) -> None:
        for handler in self._handlers:
            try:
                handler(event, data)
            except Exception:
                pass

    def register_tool(self, tool: BaseTool) -> None:
        if self._approval_handler:
            tool.set_approval_handler(self._approval_handler)
        self._tools.register(tool)

    def register_tools(self, tools: list[BaseTool]) -> None:
        for tool in tools:
            self.register_tool(tool)

    @property
    def manager(self) -> Any:
        return self._manager

    async def delegate_to(self, agent_name: str, task: str) -> str:
        if not self._manager or not hasattr(self._manager, "delegate"):
            raise RuntimeError("No manager configured for agent delegation")
        _, result = await self._manager.delegate(agent_name, task)
        return result

    async def request_approval(self, tool_name: str, reason: str) -> bool:
        if not self._manager or not hasattr(self._manager, "_handle_approval"):
            return True
        from codecraft.tools.base import BaseTool
        class DummyTool(BaseTool):
            name = tool_name
            risk = ToolRisk.WRITE
            description = reason
            async def execute(self, **kw): return ToolResult(True, "")
        return await self._manager._handle_approval(DummyTool(), {"reason": reason})

    async def run(self, input_text: str, stream: bool = False) -> str | AsyncIterator[str]:
        if not self._context:
            raise RuntimeError("Agent context not set. Call set_context() first.")

        self._turn_count = 0
        self._messages = []

        self._add_system_message()

        memory_ctx = ""
        if self._memory and self._context:
            try:
                mem_query = f"{self.name} task: {self._context.project_name} {input_text[:200]}"
                memory_ctx = self._memory.get_context_window(self.name, mem_query)
                if memory_ctx and len(memory_ctx) > 10:
                    self._messages.append(LLMMessage(role="system", content=memory_ctx))
                    self._emit("memory_recall", {"agent": self.name, "memories": len(memory_ctx)})
            except Exception as e:
                logger.warning(f"Memory recall skipped: {e}")

        self._messages.append(LLMMessage(role="user", content=input_text))

        if stream:
            return self._run_stream()
        return await self._run_sync()

    async def _run_sync(self) -> str:
        while self._turn_count < self.max_turns:
            self._turn_count += 1

            response = await self.provider.complete(
                messages=self._messages,
                tools=self._tools.to_definitions() if self._tools.list_tools() else None,
            )
            if not isinstance(response, LLMResponse):
                raise TypeError("Expected LLMResponse for non-streaming")

            self._emit("agent_think", {
                "agent": self.name,
                "content": response.content,
                "turn": self._turn_count,
            })

            if response.tool_calls:
                for tc in response.tool_calls:
                    fn = tc.get("function", {})
                    tool_name = fn.get("name", "")
                    try:
                        tool_args = json.loads(fn.get("arguments", "{}"))
                    except json.JSONDecodeError:
                        tool_args = {}

                    self._emit("tool_call", {
                        "agent": self.name,
                        "tool": tool_name,
                        "args": tool_args,
                    })

                    result = await self._tools.execute_tool(tool_name, **tool_args)

                    self._emit("tool_result", {
                        "agent": self.name,
                        "tool": tool_name,
                        "success": result.success,
                        "output": result.output[:1000],
                    })

                    self._messages.append(LLMMessage(
                        role="assistant",
                        content=None,
                        tool_calls=[tc],
                    ))
                    self._messages.append(LLMMessage(
                        role="tool",
                        content=result.to_message(),
                        tool_call_id=tc.get("id", ""),
                    ))
            else:
                final_content = response.content or ""
                self._emit("agent_done", {
                    "agent": self.name,
                    "content": final_content,
                    "turns": self._turn_count,
                })
                return final_content

        return "Max turns reached without completion."

    async def _run_stream(self) -> AsyncIterator[str]:
        final_content = ""
        while self._turn_count < self.max_turns:
            self._turn_count += 1

            response = await self.provider.complete(
                messages=self._messages,
                tools=self._tools.to_definitions() if self._tools.list_tools() else None,
            )

            if isinstance(response, AsyncIterator):
                collected = ""
                async for chunk in response:
                    collected += chunk
                    yield chunk
                final_content = collected
            elif isinstance(response, LLMResponse):
                if response.tool_calls:
                    for tc in response.tool_calls:
                        fn = tc.get("function", {})
                        tool_name = fn.get("name", "")
                        try:
                            tool_args = json.loads(fn.get("arguments", "{}"))
                        except json.JSONDecodeError:
                            tool_args = {}

                        result = await self._tools.execute_tool(tool_name, **tool_args)
                        self._messages.append(LLMMessage(
                            role="assistant",
                            content=None,
                            tool_calls=[tc],
                        ))
                        self._messages.append(LLMMessage(
                            role="tool",
                            content=result.to_message(),
                            tool_call_id=tc.get("id", ""),
                        ))
                    continue
                final_content = response.content or ""
                yield final_content

        if not final_content:
            yield "\n\n[Max turns reached]"

    def _add_system_message(self) -> None:
        prompt = self.system_prompt
        if self._context:
            project_info = (
                f"\nYou are working on project: {self._context.project_name}\n"
                f"Project description: {self._context.project_description}\n"
                f"Working directory: {self._context.workdir}\n"
                f"Your role: {self.name} - {self.description}\n"
            )
            prompt += project_info
        self._messages.append(LLMMessage(role="system", content=prompt))

    def add_message(self, role: str, content: str) -> None:
        self._messages.append(LLMMessage(role=role, content=content))

    @property
    def messages(self) -> list[LLMMessage]:
        return list(self._messages)

    @property
    def context(self) -> Optional[AgentContext]:
        return self._context

    @property
    def tool_names(self) -> list[str]:
        return self._tools.list_tools()

    async def close(self) -> None:
        if hasattr(self.provider, "close"):
            await self.provider.close()

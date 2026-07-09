from __future__ import annotations

import abc
import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

from codecraft.config import settings

logger = logging.getLogger(__name__)


class ToolRisk(str, Enum):
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    NETWORK = "network"


@dataclass
class ToolResult:
    success: bool
    output: str
    error: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_message(self) -> str:
        if self.success:
            return self.output
        return f"Error: {self.error or 'Unknown error'}"


class BaseTool(abc.ABC):
    name: str = ""
    description: str = ""
    risk: ToolRisk = ToolRisk.READ
    requires_approval: bool = False

    def __init__(self, workdir: Optional[str] = None):
        self.workdir = workdir or str(settings.projects_dir)
        self._approval_handler: Optional[Callable[[BaseTool, dict[str, Any]], bool]] = None

    @abc.abstractmethod
    async def execute(self, **kwargs: Any) -> ToolResult:
        ...

    def to_definition(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.get_parameters_schema(),
            },
        }

    def get_parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "required": [],
        }

    def set_approval_handler(self, handler: Callable[[BaseTool, dict[str, Any]], bool]) -> None:
        self._approval_handler = handler

    async def safe_execute(self, **kwargs: Any) -> ToolResult:
        if self.requires_approval and self._approval_handler:
            approved = self._approval_handler(self, kwargs)
            if not approved:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Tool '{self.name}' execution was not approved by user.",
                )
        try:
            return await self.execute(**kwargs)
        except Exception as e:
            logger.exception(f"Tool {self.name} failed: {e}")
            return ToolResult(success=False, output="", error=str(e))


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, BaseTool] = {}
        self._approval_handler: Optional[Callable[[BaseTool, dict[str, Any]], bool]] = None

    def register(self, tool: BaseTool) -> None:
        for t in [tool]:
            if hasattr(t, "name") and t.name:
                self._tools[t.name] = t
                logger.debug(f"Registered tool: {t.name}")

    def register_many(self, tools: list[BaseTool]) -> None:
        for tool in tools:
            self.register(tool)

    def get(self, name: str) -> Optional[BaseTool]:
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        return list(self._tools.keys())

    def to_definitions(self) -> list[dict[str, Any]]:
        return [tool.to_definition() for tool in self._tools.values()]

    def set_approval_handler(self, handler: Callable[[BaseTool, dict[str, Any]], bool]) -> None:
        self._approval_handler = handler
        for tool in self._tools.values():
            tool.set_approval_handler(handler)

    async def execute_tool(self, name: str, **kwargs: Any) -> ToolResult:
        tool = self._tools.get(name)
        if not tool:
            return ToolResult(success=False, output="", error=f"Unknown tool: {name}")
        if settings.require_tool_approval and tool.risk in (ToolRisk.WRITE, ToolRisk.EXECUTE):
            if self._approval_handler and not self._approval_handler(tool, kwargs):
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Tool '{name}' requires approval.",
                )
        return await tool.safe_execute(**kwargs)

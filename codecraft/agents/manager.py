from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Optional

from codecraft.agents.base import BaseAgent, AgentContext
from codecraft.tools.base import BaseTool, ToolRegistry, ToolRisk, ToolResult
from codecraft.llm.base import LLMMessage, LLMResponse
from codecraft.llm.models import resolve_model_for_agent

logger = logging.getLogger(__name__)


class ManagerAgent(BaseAgent):
    name = "manager"
    description = "Orchestration manager - approves tool usage, delegates tasks, coordinates agents"

    system_prompt = """You are the **Manager Agent** in CodeCraft. You coordinate the agent team, approve sensitive operations, and delegate tasks.

## Core Rules
- Approve tool usage when it aligns with the project goal
- Reject dangerous or irrelevant operations
- Delegate subtasks to the most appropriate agent
- Track which agent is doing what
- Never approve: system-destroying commands, reading secrets unnecessarily, network scans on third parties

## Response Format
For delegation requests, respond with:
- AGENT: <agent_name> — which agent should handle this
- TASK: <description> — what they should do

For tool approval:
- APPROVE — if the tool usage is safe and relevant
- REJECT: <reason> — if not"""

    default_model = "gpt-4o-mini"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._agent_pool: dict[str, BaseAgent] = {}
        self._delegation_history: list[dict[str, Any]] = []
        self._shared_tools = ToolRegistry()
        self._pending_approvals: dict[str, asyncio.Future] = {}

    def register_agent(self, agent: BaseAgent) -> None:
        self._agent_pool[agent.name] = agent
        tools = agent._tools if hasattr(agent, "_tools") else None
        if tools:
            for name in tools.list_tools():
                tool = tools.get(name)
                if tool and name not in self._shared_tools.list_tools():
                    self._shared_tools.register(tool)

        agent._manager = self
        agent._approval_handler = self._handle_approval
        logger.info(f"Manager: registered agent '{agent.name}'")

    async def _handle_approval(self, tool: BaseTool, kwargs: dict[str, Any]) -> bool:
        if tool.risk in (ToolRisk.READ, ToolRisk.NETWORK):
            return True

        approval_id = f"{tool.name}_{id(kwargs)}"
        fut: asyncio.Future = asyncio.Future()
        self._pending_approvals[approval_id] = fut

        self._emit("approval_requested", {
            "tool": tool.name,
            "risk": tool.risk.value,
            "args": str(kwargs)[:200],
        })

        try:
            result = await asyncio.wait_for(fut, timeout=30)
            return result
        except asyncio.TimeoutError:
            self._emit("approval_timeout", {"tool": tool.name})
            return False

    def approve(self, tool_name: str, kwargs_hash: str, approved: bool) -> None:
        approval_id = f"{tool_name}_{kwargs_hash}"
        if approval_id in self._pending_approvals:
            self._pending_approvals[approval_id].set_result(approved)
            del self._pending_approvals[approval_id]

    async def delegate(
        self,
        to_agent: str,
        task: str,
        context: Optional[dict[str, Any]] = None,
    ) -> tuple[str, str]:
        agent = self._agent_pool.get(to_agent)
        if not agent:
            raise ValueError(f"Agent not found: {to_agent}. Available: {list(self._agent_pool)}")

        try:
            agent.enable_memory()
        
            for name in self._shared_tools.list_tools():
                try:
                    if name not in agent.tool_names:
                        agent.register_tool(self._shared_tools.get(name))
                except Exception:
                    pass

            result = await agent.run(task)

            self._delegation_history.append({
                "from": self.name,
                "to": to_agent,
                "task": task[:500],
                "result_length": len(result) if result else 0,
            })

            return to_agent, result
        except Exception as e:
            logger.error(f"Delegation to {to_agent} failed: {e}")
            raise

    async def create_agent_tool(
        self,
        name: str,
        description: str,
        agent_name: str,
        input_transform: Optional[Callable] = None,
    ) -> None:
        class DelegatedTool(BaseTool):
            name = name
            description = description
            risk = ToolRisk.EXECUTE
            requires_approval = True

            def __init__(self, manager=None, target_agent=None, transform=None, **kw):
                super().__init__(**kw)
                self._manager = manager
                self._target = target_agent
                self._transform = transform

            async def execute(self, **kwargs):
                task = self._transform(kwargs) if self._transform else str(kwargs)
                agent_name, result = await self._manager.delegate(self._target, task)
                return ToolResult(success=True, output=result, metadata={"agent": agent_name})

        tool = DelegatedTool(manager=self, target_agent=agent_name, transform=input_transform)
        self._shared_tools.register(tool)

    def get_agent_status(self) -> dict[str, dict[str, Any]]:
        status = {}
        for name, agent in self._agent_pool.items():
            status[name] = {
                "name": name,
                "tools": agent.tool_names,
                "has_context": agent.context is not None,
            }
        return status

    def list_pending_approvals(self) -> list[dict[str, Any]]:
        return [{"id": k, "pending": not v.done()} for k, v in self._pending_approvals.items()]

    async def broadcast_context(self, memory_type: str, content: str) -> None:
        for agent in self._agent_pool.values():
            try:
                agent.memory.remember(
                    agent=agent.name,
                    content=content,
                    memory_type=memory_type,
                    metadata={"broadcast": True},
                )
            except Exception:
                pass

    async def close(self) -> None:
        for agent in self._agent_pool.values():
            try:
                await agent.close()
            except Exception:
                pass
        await super().close()

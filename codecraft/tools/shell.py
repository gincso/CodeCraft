from __future__ import annotations

import asyncio
import logging
import os
import shlex
from pathlib import Path
from typing import Any

from codecraft.tools.base import BaseTool, ToolResult, ToolRisk
from codecraft.config import settings

logger = logging.getLogger(__name__)

BLOCKED_COMMANDS = {
    "rm -rf /",
    "mkfs",
    "dd if=",
    ":(){ :|:& };:",
    "chmod 777 /",
    "> /dev/sda",
}


class ShellTool(BaseTool):
    name = "run_shell"
    description = "Execute a shell command and return its output. Use for building, testing, package management, git operations."
    risk = ToolRisk.EXECUTE
    requires_approval = True

    def __init__(self, workdir: str | None = None):
        super().__init__(workdir)
        self._blocked = set(BLOCKED_COMMANDS)
        self._allowed_dirs: set[str] = set()
        self.timeout = 120

    async def execute(self, command: str, timeout: int = 120, **kwargs: Any) -> ToolResult:
        cmd_lower = command.lower()
        for blocked in self._blocked:
            if blocked in cmd_lower:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Blocked potentially dangerous command pattern: {blocked}",
                )

        if not settings.sandbox_enabled:
            return await self._execute_raw(command, timeout)

        return await self._execute_sandboxed(command, timeout)

    async def _execute_raw(self, command: str, timeout: int) -> ToolResult:
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.workdir,
                env={**os.environ},
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            stdout_str = stdout.decode("utf-8", errors="replace")
            stderr_str = stderr.decode("utf-8", errors="replace")
            return ToolResult(
                success=proc.returncode == 0,
                output=stdout_str if proc.returncode == 0 else stderr_str or stdout_str,
                metadata={"exit_code": proc.returncode},
                error=stderr_str if proc.returncode != 0 else None,
            )
        except asyncio.TimeoutError:
            return ToolResult(success=False, output="", error=f"Command timed out after {timeout}s")
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    async def _execute_sandboxed(self, command: str, timeout: int) -> ToolResult:
        return await self._execute_raw(command, timeout)

    def get_parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to execute"},
                "timeout": {"type": "integer", "description": "Timeout in seconds"},
            },
            "required": ["command"],
        }

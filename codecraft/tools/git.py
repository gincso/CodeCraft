from __future__ import annotations

import asyncio
import logging
from typing import Any

from codecraft.tools.base import BaseTool, ToolResult, ToolRisk

logger = logging.getLogger(__name__)


class GitTool(BaseTool):
    name = "git"
    description = "Execute git operations: init, add, commit, clone, status, diff, log, branch, checkout, push, pull."
    risk = ToolRisk.WRITE

    async def execute(self, operation: str, args: str = "", **kwargs: Any) -> ToolResult:
        valid_ops = {
            "init", "add", "commit", "clone", "status", "diff", "log",
            "branch", "checkout", "push", "pull", "remote", "config",
        }
        if operation not in valid_ops:
            return ToolResult(
                success=False,
                output="",
                error=f"Invalid git operation: {operation}. Valid: {sorted(valid_ops)}",
            )

        cmd = f"git {operation} {args}"

        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.workdir,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
            stdout_str = stdout.decode("utf-8", errors="replace")
            stderr_str = stderr.decode("utf-8", errors="replace")

            output = stdout_str + stderr_str if stderr_str else stdout_str
            return ToolResult(
                success=proc.returncode == 0,
                output=output.strip() or "(no output)",
                metadata={"exit_code": proc.returncode, "operation": operation},
                error=stderr_str if proc.returncode != 0 else None,
            )
        except asyncio.TimeoutError:
            return ToolResult(success=False, output="", error="Git operation timed out")
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    def get_parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": [
                        "init", "add", "commit", "clone", "status", "diff",
                        "log", "branch", "checkout", "push", "pull", "remote", "config",
                    ],
                    "description": "Git operation to perform",
                },
                "args": {
                    "type": "string",
                    "description": "Arguments for the git operation (e.g., '-m \"message\"' for commit)",
                },
            },
            "required": ["operation"],
        }

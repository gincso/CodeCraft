from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

from codecraft.tools.base import BaseTool, ToolResult, ToolRisk

logger = logging.getLogger(__name__)

SUPPORTED_LANGUAGES = {
    "python": {"ext": ".py", "cmd": ["python3"], "timeout": 30},
    "javascript": {"ext": ".js", "cmd": ["node"], "timeout": 30},
    "bash": {"ext": ".sh", "cmd": ["bash"], "timeout": 30},
}


class CodeRunnerTool(BaseTool):
    name = "run_code"
    description = "Execute code in a sandboxed environment. Supports Python, JavaScript, and Bash."
    risk = ToolRisk.EXECUTE
    requires_approval = True

    async def execute(
        self,
        code: str,
        language: str = "python",
        timeout: int = 30,
        **kwargs: Any,
    ) -> ToolResult:
        if language not in SUPPORTED_LANGUAGES:
            return ToolResult(
                success=False,
                output="",
                error=f"Unsupported language: {language}. Supported: {list(SUPPORTED_LANGUAGES)}",
            )

        lang_config = SUPPORTED_LANGUAGES[language]
        actual_timeout = min(timeout, lang_config["timeout"])

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                filepath = Path(tmpdir) / f"code{lang_config['ext']}"
                filepath.write_text(code)

                cmd = lang_config["cmd"] + [str(filepath)]
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=tmpdir,
                    env={**os.environ, "PYTHONUNBUFFERED": "1"},
                )
                try:
                    stdout, stderr = await asyncio.wait_for(
                        proc.communicate(), timeout=actual_timeout
                    )
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.wait()
                    return ToolResult(
                        success=False,
                        output="",
                        error=f"Code execution timed out after {actual_timeout}s",
                    )

                stdout_str = stdout.decode("utf-8", errors="replace")[:5000]
                stderr_str = stderr.decode("utf-8", errors="replace")[:5000]

                output = stdout_str
                if stderr_str:
                    output += f"\n[stderr]\n{stderr_str}"

                return ToolResult(
                    success=proc.returncode == 0,
                    output=output.strip() or "(no output)",
                    metadata={
                        "exit_code": proc.returncode,
                        "language": language,
                        "stdout_length": len(stdout_str),
                        "stderr_length": len(stderr_str),
                    },
                    error=stderr_str if proc.returncode != 0 else None,
                )
        except Exception as e:
            logger.exception(f"Code execution failed: {e}")
            return ToolResult(success=False, output="", error=str(e))

    def get_parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Source code to execute"},
                "language": {
                    "type": "string",
                    "enum": list(SUPPORTED_LANGUAGES.keys()),
                    "description": "Programming language",
                },
                "timeout": {"type": "integer", "description": "Timeout in seconds"},
            },
            "required": ["code", "language"],
        }

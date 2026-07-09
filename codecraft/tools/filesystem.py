from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from codecraft.tools.base import BaseTool, ToolResult, ToolRisk


class ReadFileTool(BaseTool):
    name = "read_file"
    description = "Read the contents of a file at a given path."
    risk = ToolRisk.READ

    async def execute(self, path: str, offset: int = 0, limit: int = 2000, **kwargs: Any) -> ToolResult:
        resolved = self._resolve_path(path)
        if not resolved.exists():
            return ToolResult(success=False, output="", error=f"File not found: {path}")
        if resolved.is_dir():
            return ToolResult(success=False, output="", error=f"Path is a directory: {path}")
        try:
            content = resolved.read_text()
            lines = content.split("\n")
            sliced = lines[offset : offset + limit]
            return ToolResult(
                success=True,
                output="\n".join(sliced),
                metadata={
                    "total_lines": len(lines),
                    "offset": offset,
                    "limit": limit,
                    "size": len(content),
                },
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    def _resolve_path(self, path: str) -> Path:
        p = Path(path)
        if not p.is_absolute():
            p = Path(self.workdir) / p
        return p.resolve()

    def get_parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to the file to read"},
                "offset": {"type": "integer", "description": "Line number to start reading from (0-indexed)"},
                "limit": {"type": "integer", "description": "Maximum number of lines to read"},
            },
            "required": ["path"],
        }


class WriteFileTool(BaseTool):
    name = "write_file"
    description = "Write content to a file, creating it or overwriting it."
    risk = ToolRisk.WRITE
    requires_approval = True

    async def execute(self, path: str, content: str, **kwargs: Any) -> ToolResult:
        resolved = self._resolve_path(path)
        try:
            resolved.parent.mkdir(parents=True, exist_ok=True)
            resolved.write_text(content)
            return ToolResult(
                success=True,
                output=f"File written: {resolved}",
                metadata={"path": str(resolved), "size": len(content)},
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    def _resolve_path(self, path: str) -> Path:
        p = Path(path)
        if not p.is_absolute():
            p = Path(self.workdir) / p
        return p.resolve()

    def get_parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to write the file to"},
                "content": {"type": "string", "description": "Content to write to the file"},
            },
            "required": ["path", "content"],
        }


class ListDirectoryTool(BaseTool):
    name = "list_directory"
    description = "List contents of a directory."
    risk = ToolRisk.READ

    async def execute(self, path: str = ".", **kwargs: Any) -> ToolResult:
        resolved = self._resolve_path(path)
        if not resolved.exists():
            return ToolResult(success=False, output="", error=f"Directory not found: {path}")
        if not resolved.is_dir():
            return ToolResult(success=False, output="", error=f"Not a directory: {path}")
        try:
            entries = []
            for entry in sorted(resolved.iterdir()):
                suffix = "/" if entry.is_dir() else ""
                entries.append(f"{entry.name}{suffix}")
            return ToolResult(
                success=True,
                output="\n".join(entries),
                metadata={"path": str(resolved), "count": len(entries)},
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    def _resolve_path(self, path: str) -> Path:
        p = Path(path)
        if not p.is_absolute():
            p = Path(self.workdir) / p
        return p.resolve()

    def get_parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory path to list"},
            },
            "required": ["path"],
        }


class SearchFilesTool(BaseTool):
    name = "search_files"
    description = "Search for files matching a glob pattern."
    risk = ToolRisk.READ

    async def execute(self, pattern: str, path: str = ".", **kwargs: Any) -> ToolResult:
        import glob as glob_module

        resolved = self._resolve_path(path)
        if not resolved.exists():
            return ToolResult(success=False, output="", error=f"Path not found: {path}")
        try:
            search_pattern = str(resolved / pattern)
            matches = glob_module.glob(search_pattern, recursive=True)
            matches.sort()
            return ToolResult(
                success=True,
                output="\n".join(matches),
                metadata={"pattern": pattern, "count": len(matches)},
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    def _resolve_path(self, path: str) -> Path:
        p = Path(path)
        if not p.is_absolute():
            p = Path(self.workdir) / p
        return p.resolve()

    def get_parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Glob pattern (e.g. **/*.py)"},
                "path": {"type": "string", "description": "Base directory to search in"},
            },
            "required": ["pattern"],
        }


class GrepTool(BaseTool):
    name = "grep"
    description = "Search file contents using regex patterns."
    risk = ToolRisk.READ

    async def execute(self, pattern: str, path: str = ".", include: str = "*", **kwargs: Any) -> ToolResult:
        import re
        from pathlib import Path as P

        resolved = self._resolve_path(path)
        if not resolved.exists():
            return ToolResult(success=False, output="", error=f"Path not found: {path}")
        try:
            results = []
            for f in resolved.rglob(include):
                if f.is_file():
                    try:
                        content = f.read_text()
                        for i, line in enumerate(content.split("\n"), 1):
                            if re.search(pattern, line):
                                results.append(f"{f}:{i}: {line.strip()[:200]}")
                    except Exception:
                        continue
            results.sort()
            return ToolResult(
                success=True,
                output="\n".join(results[:500]),
                metadata={"pattern": pattern, "match_count": len(results)},
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    def _resolve_path(self, path: str) -> Path:
        p = Path(path)
        if not p.is_absolute():
            p = Path(self.workdir) / p
        return p.resolve()

    def get_parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Regex pattern to search for"},
                "path": {"type": "string", "description": "Base directory to search in"},
                "include": {"type": "string", "description": "File pattern to include (glob)"},
            },
            "required": ["pattern"],
        }

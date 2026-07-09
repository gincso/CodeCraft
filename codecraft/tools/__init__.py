"""Tool system for agent capabilities."""

from codecraft.tools.base import BaseTool, ToolRegistry, ToolResult, ToolRisk
from codecraft.tools.filesystem import ReadFileTool, WriteFileTool, ListDirectoryTool, SearchFilesTool, GrepTool
from codecraft.tools.shell import ShellTool
from codecraft.tools.web_search import WebSearchTool, WebFetchTool
from codecraft.tools.code_runner import CodeRunnerTool
from codecraft.tools.git import GitTool
from codecraft.tools.github_search import GitHubSearchTool, GitHubRepoInspectTool
from codecraft.tools.package_search import PackageSearchTool
from codecraft.tools.discovery import ToolDiscovery


ALL_TOOLS: dict[str, type[BaseTool]] = {
    "read_file": ReadFileTool,
    "write_file": WriteFileTool,
    "list_directory": ListDirectoryTool,
    "search_files": SearchFilesTool,
    "grep": GrepTool,
    "run_shell": ShellTool,
    "web_search": WebSearchTool,
    "web_fetch": WebFetchTool,
    "run_code": CodeRunnerTool,
    "git": GitTool,
    "github_search": GitHubSearchTool,
    "github_inspect": GitHubRepoInspectTool,
    "package_search": PackageSearchTool,
    "tool_discovery": ToolDiscovery,
}


def get_tool_class(name: str) -> type[BaseTool] | None:
    return ALL_TOOLS.get(name)


def create_default_toolkit(workdir: str) -> ToolRegistry:
    registry = ToolRegistry()
    for cls in ALL_TOOLS.values():
        registry.register(cls(workdir=workdir))
    return registry


__all__ = [
    "BaseTool", "ToolRegistry", "ToolResult", "ToolRisk",
    "ReadFileTool", "WriteFileTool", "ListDirectoryTool", "SearchFilesTool", "GrepTool",
    "ShellTool", "WebSearchTool", "WebFetchTool", "CodeRunnerTool", "GitTool",
    "GitHubSearchTool", "GitHubRepoInspectTool", "PackageSearchTool", "ToolDiscovery",
    "ALL_TOOLS", "get_tool_class", "create_default_toolkit",
]

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional

import httpx

from codecraft.tools.base import BaseTool, ToolResult, ToolRisk

logger = logging.getLogger(__name__)


class GitHubSearchTool(BaseTool):
    name = "github_search"
    description = "Search GitHub for repositories, code, issues, and topics. Use to find existing tools, libraries, plugins, or reference implementations."
    risk = ToolRisk.NETWORK

    def __init__(self, workdir: str | None = None):
        super().__init__(workdir)
        self._client: Optional[httpx.AsyncClient] = None
        self._token: Optional[str] = self._load_token()

    @staticmethod
    def _load_token() -> Optional[str]:
        try:
            from codecraft.config import settings
            return settings.deploy.github_token
        except Exception:
            return None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            headers = {
                "User-Agent": "CodeCraft/1.0",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
            if self._token:
                headers["Authorization"] = f"Bearer {self._token}"
            self._client = httpx.AsyncClient(
                base_url="https://api.github.com",
                headers=headers,
                timeout=httpx.Timeout(30),
            )
        return self._client

    async def execute(
        self,
        query: str,
        search_type: str = "repositories",
        max_results: int = 10,
        language: str = "",
        sort: str = "stars",
        **kwargs: Any,
    ) -> ToolResult:
        if search_type not in ("repositories", "code", "topics", "issues"):
            return ToolResult(
                success=False, output="",
                error=f"Invalid search_type: {search_type}. Use: repositories, code, topics, issues",
            )

        params: dict[str, Any] = {
            "q": query,
            "per_page": min(max_results, 30),
            "sort": sort,
            "order": "desc",
        }
        if language and search_type == "repositories":
            params["q"] += f" language:{language}"

        endpoint = f"/search/{search_type}"

        try:
            resp = await self.client.get(endpoint, params=params)

            if resp.status_code == 403 and "rate limit" in resp.text.lower():
                return ToolResult(
                    success=False, output="",
                    error="GitHub API rate limit reached. Try again in a minute or configure a token.",
                )

            resp.raise_for_status()
            data = resp.json()

            items = data.get("items", [])
            results = []

            if search_type == "repositories":
                for item in items[:max_results]:
                    results.append(
                        f"★ {item['full_name']} ({item.get('stargazers_count', 0)} ⭐)\n"
                        f"  {item.get('description', 'No description')[:200]}\n"
                        f"  {item.get('html_url', '')}\n"
                        f"  Language: {item.get('language', 'N/A')} | "
                        f"Updated: {item.get('updated_at', '')[:10]} | "
                        f"Topics: {', '.join(item.get('topics', [])[:5])}"
                    )
            elif search_type == "code":
                for item in items[:max_results]:
                    repo = item.get("repository", {}).get("full_name", "")
                    path = item.get("path", "")
                    results.append(
                        f"  {repo}/{path}\n"
                        f"  {item.get('html_url', '')}"
                    )
            elif search_type == "topics":
                for item in items[:max_results]:
                    results.append(
                        f"  {item.get('name', '')}: {item.get('display_name', '')}\n"
                        f"  {item.get('short_description', '')[:200]}" if isinstance(item, dict) else str(item)
                    )
            else:
                for item in items[:max_results]:
                    results.append(
                        f"  #{item.get('number', '')}: {item.get('title', '')}\n"
                        f"  {item.get('html_url', '')}"
                    )

            total = data.get("total_count", 0)
            return ToolResult(
                success=True,
                output="\n\n".join(results) if results else f"No results for: {query}",
                metadata={
                    "query": query,
                    "type": search_type,
                    "total_results": total,
                    "returned": len(results),
                },
            )
        except httpx.HTTPStatusError as e:
            return ToolResult(success=False, output="", error=f"GitHub API error: {e.response.status_code}")
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    def get_parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query. Use GitHub search syntax: e.g. 'topic:tool', 'stars:>100', 'language:python'",
                },
                "search_type": {
                    "type": "string",
                    "enum": ["repositories", "code", "topics", "issues"],
                    "description": "Type of search to perform",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum results to return (1-30)",
                },
                "language": {
                    "type": "string",
                    "description": "Filter by programming language (e.g. python, javascript)",
                },
                "sort": {
                    "type": "string",
                    "enum": ["stars", "updated", "forks"],
                    "description": "Sort results by",
                },
            },
            "required": ["query"],
        }


class GitHubRepoInspectTool(BaseTool):
    name = "github_inspect"
    description = "Inspect a specific GitHub repository: README, file tree, recent commits, releases."
    risk = ToolRisk.NETWORK

    def __init__(self, workdir: str | None = None):
        super().__init__(workdir)
        self._client: Optional[httpx.AsyncClient] = None
        self._token: Optional[str] = GitHubSearchTool._load_token()

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            headers = {
                "User-Agent": "CodeCraft/1.0",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
            if self._token:
                headers["Authorization"] = f"Bearer {self._token}"
            self._client = httpx.AsyncClient(
                base_url="https://api.github.com",
                headers=headers,
                timeout=httpx.Timeout(30),
            )
        return self._client

    async def execute(
        self,
        repo: str,
        action: str = "readme",
        path: str = "",
        **kwargs: Any,
    ) -> ToolResult:
        valid_actions = ("readme", "tree", "commits", "releases", "file")
        if action not in valid_actions:
            return ToolResult(success=False, output="", error=f"Invalid action: {action}")

        try:
            if action == "readme":
                return await self._get_readme(repo)
            elif action == "tree":
                return await self._get_tree(repo, path)
            elif action == "commits":
                return await self._get_commits(repo)
            elif action == "releases":
                return await self._get_releases(repo)
            elif action == "file":
                return await self._get_file(repo, path)
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    async def _get_readme(self, repo: str) -> ToolResult:
        resp = await self.client.get(f"/repos/{repo}/readme")
        resp.raise_for_status()
        data = resp.json()
        content = data.get("content", "")
        import base64
        try:
            decoded = base64.b64decode(content).decode("utf-8", errors="replace")
            return ToolResult(
                success=True,
                output=decoded[:5000],
                metadata={"repo": repo, "size": len(decoded)},
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    async def _get_tree(self, repo: str, path: str = "") -> ToolResult:
        branch_resp = await self.client.get(f"/repos/{repo}")
        branch_resp.raise_for_status()
        default_branch = branch_resp.json().get("default_branch", "main")

        url = f"/repos/{repo}/git/trees/{default_branch}"
        if path:
            url += f"?recursive=1"

        resp = await self.client.get(url)
        resp.raise_for_status()
        data = resp.json()

        items = data.get("tree", [])
        if path:
            prefix = path.rstrip("/") + "/"
            items = [i for i in items if i.get("path", "").startswith(prefix)]

        lines = []
        for item in items[:50]:
            item_type = "📁" if item.get("type") == "tree" else "📄"
            lines.append(f"  {item_type} {item.get('path', '')}")

        return ToolResult(
            success=True,
            output=f"Repository: {repo}\n" + "\n".join(lines),
            metadata={"repo": repo, "item_count": len(items)},
        )

    async def _get_commits(self, repo: str) -> ToolResult:
        resp = await self.client.get(f"/repos/{repo}/commits", params={"per_page": 5})
        resp.raise_for_status()
        data = resp.json()

        lines = []
        for commit in data[:5]:
            msg = commit.get("commit", {}).get("message", "").split("\n")[0][:100]
            date = commit.get("commit", {}).get("author", {}).get("date", "")[:10]
            lines.append(f"  {date} {msg}")

        return ToolResult(success=True, output="\n".join(lines))

    async def _get_releases(self, repo: str) -> ToolResult:
        resp = await self.client.get(f"/repos/{repo}/releases", params={"per_page": 5})
        resp.raise_for_status()
        data = resp.json()

        lines = []
        for rel in data[:5]:
            lines.append(f"  {rel.get('tag_name', '?')}: {rel.get('name', '')[:100]}")

        return ToolResult(success=True, output="\n".join(lines) or "No releases")

    async def _get_file(self, repo: str, path: str) -> ToolResult:
        resp = await self.client.get(f"/repos/{repo}/contents/{path}")
        resp.raise_for_status()
        data = resp.json()
        content = data.get("content", "")
        import base64
        try:
            decoded = base64.b64decode(content).decode("utf-8", errors="replace")
            return ToolResult(
                success=True,
                output=decoded[:5000],
                metadata={"repo": repo, "path": path, "size": len(decoded)},
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    def get_parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "repo": {
                    "type": "string",
                    "description": "Repository in owner/name format (e.g. 'facebook/react')",
                },
                "action": {
                    "type": "string",
                    "enum": ["readme", "tree", "commits", "releases", "file"],
                    "description": "What to inspect",
                },
                "path": {
                    "type": "string",
                    "description": "File path for 'file' action or directory path for 'tree'",
                },
            },
            "required": ["repo"],
        }

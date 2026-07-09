from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional

import httpx

from codecraft.tools.base import BaseTool, ToolResult, ToolRisk

logger = logging.getLogger(__name__)


class PackageSearchTool(BaseTool):
    name = "package_search"
    description = "Search package registries (PyPI, npm, crates.io) for libraries and tools. Find existing packages before creating something from scratch."
    risk = ToolRisk.NETWORK

    def __init__(self, workdir: str | None = None):
        super().__init__(workdir)
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(20),
                headers={"User-Agent": "CodeCraft/1.0"},
            )
        return self._client

    async def execute(
        self,
        query: str,
        registry: str = "pypi",
        max_results: int = 10,
        **kwargs: Any,
    ) -> ToolResult:
        if registry == "pypi":
            return await self._search_pypi(query, max_results)
        elif registry == "npm":
            return await self._search_npm(query, max_results)
        elif registry == "crates":
            return await self._search_crates(query, max_results)
        else:
            return ToolResult(
                success=False, output="",
                error=f"Unknown registry: {registry}. Use: pypi, npm, crates",
            )

    async def _search_pypi(self, query: str, max_results: int) -> ToolResult:
        try:
            resp = await self.client.get(
                "https://pypi.org/search/",
                params={"q": query},
                headers={"Accept": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()
            items = data.get("results", data.get("hits", []))[:max_results]

            results = []
            for item in items:
                if isinstance(item, dict):
                    name = item.get("name", item.get("package_name", "?"))
                    version = item.get("version", "?")
                    desc = item.get("summary", item.get("description", ""))[:200]
                    results.append(f"[PyPI] {name} v{version}\n  {desc}\n  pip install {name}")

            if not results:
                resp2 = await self.client.get(
                    f"https://pypi.org/pypi/{query}/json",
                )
                if resp2.status_code == 200:
                    data2 = resp2.json()
                    info = data2.get("info", {})
                    results.append(
                        f"[PyPI] {info.get('name', query)} v{info.get('version', '?')}\n"
                        f"  {info.get('summary', '')[:200]}\n"
                        f"  pip install {info.get('name', query)}"
                    )

            return ToolResult(
                success=True,
                output="\n\n".join(results) if results else f"No PyPI results for: {query}",
                metadata={"registry": "pypi", "query": query, "count": len(results)},
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    async def _search_npm(self, query: str, max_results: int) -> ToolResult:
        try:
            resp = await self.client.get(
                "https://registry.npmjs.org/-/v1/search",
                params={"text": query, "size": max_results},
            )
            resp.raise_for_status()
            data = resp.json()
            items = data.get("objects", [])[:max_results]

            results = []
            for item in items:
                pkg = item.get("package", {})
                name = pkg.get("name", "?")
                version = pkg.get("version", "?")
                desc = pkg.get("description", "")[:200]
                results.append(f"[npm] {name} v{version}\n  {desc}\n  npm install {name}")

            return ToolResult(
                success=True,
                output="\n\n".join(results) if results else f"No npm results for: {query}",
                metadata={"registry": "npm", "query": query, "count": len(results)},
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    async def _search_crates(self, query: str, max_results: int) -> ToolResult:
        try:
            resp = await self.client.get(
                "https://crates.io/api/v1/crates",
                params={"q": query, "per_page": max_results},
            )
            resp.raise_for_status()
            data = resp.json()
            items = data.get("crates", [])[:max_results]

            results = []
            for item in items:
                name = item.get("name", "?")
                version = item.get("max_stable_version", item.get("newest_version", "?"))
                desc = item.get("description", "")[:200]
                results.append(f"[crates.io] {name} v{version}\n  {desc}\n  cargo add {name}")

            return ToolResult(
                success=True,
                output="\n\n".join(results) if results else f"No crates.io results for: {query}",
                metadata={"registry": "crates.io", "query": query, "count": len(results)},
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    def get_parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Package name or keyword to search"},
                "registry": {
                    "type": "string",
                    "enum": ["pypi", "npm", "crates"],
                    "description": "Package registry to search",
                },
                "max_results": {"type": "integer", "description": "Max results (1-20)"},
            },
            "required": ["query"],
        }

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

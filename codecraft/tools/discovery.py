from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional

import httpx

from codecraft.tools.base import BaseTool, ToolResult, ToolRisk, ToolRegistry
from codecraft.config import settings

logger = logging.getLogger(__name__)


class ToolDiscovery(BaseTool):
    name = "tool_discovery"
    description = "Discover existing tools/libraries/plugins from GitHub, PyPI, npm, crates.io. If nothing found, auto-create a custom tool. Use this when you need functionality that's not available."
    risk = ToolRisk.NETWORK

    def __init__(self, workdir: str | None = None):
        super().__init__(workdir)
        self._client: Optional[httpx.AsyncClient] = None
        self._token: Optional[str] = self._load_token()
        self._created_tools: list[dict[str, Any]] = []

    @staticmethod
    def _load_token() -> Optional[str]:
        try:
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
                timeout=httpx.Timeout(30),
                headers=headers,
            )
        return self._client

    async def execute(
        self,
        need: str,
        language: str = "python",
        auto_install: bool = False,
        **kwargs: Any,
    ) -> ToolResult:
        """Full discovery pipeline: search → evaluate → install or create."""
        findings: list[dict[str, Any]] = []
        all_results: list[str] = []

        github_items, gh_total = await self._search_github(need, language)
        if github_items:
            all_results.append(f"## GitHub Repositories ({gh_total} total)\n\n" + "\n\n".join(github_items[:5]))
            findings.extend(self._parse_items(github_items, "github"))

        pypi_items = await self._search_pypi(need)
        if pypi_items:
            all_results.append(f"## PyPI Packages\n\n" + "\n\n".join(pypi_items[:5]))
            findings.extend(self._parse_items(pypi_items, "pypi"))

        npm_items = await self._search_npm(need)
        if npm_items:
            all_results.append(f"## npm Packages\n\n" + "\n\n".join(npm_items[:5]))
            findings.extend(self._parse_items(npm_items, "npm"))

        if not findings:
            all_results.append(
                f"## No existing solutions found for: {need}\n\n"
                f"### Creating custom solution\n"
                f"A custom tool will be auto-generated to handle this need."
            )
            custom_tool = await self._create_custom_tool(need, language)
            if custom_tool:
                all_results.append(f"\n### Custom Tool Created\n```python\n{custom_tool}\n```")

        if auto_install and findings:
            best = findings[0]
            install_result = await self._auto_install(best)
            all_results.append(f"\n## Auto-Install\n{install_result}")

        return ToolResult(
            success=True,
            output="\n\n".join(all_results),
            metadata={
                "need": need,
                "github_count": len(github_items),
                "pypi_count": len(pypi_items),
                "npm_count": len(npm_items),
                "created_tool": bool(not findings),
                "installed": auto_install and bool(findings),
            },
        )

    async def _search_github(self, query: str, language: str) -> tuple[list[str], int]:
        try:
            params = {
                "q": f"{query} {language}",
                "per_page": 10,
                "sort": "stars",
                "order": "desc",
            }
            resp = await self.client.get(
                "https://api.github.com/search/repositories", params=params
            )
            if resp.status_code != 200:
                return [], 0

            data = resp.json()
            items = data.get("items", [])
            results = []
            for item in items[:5]:
                results.append(
                    f"★ {item['full_name']} ({item.get('stargazers_count', 0)} ⭐)\n"
                    f"  {item.get('description', 'No description')[:200]}\n"
                    f"  {item.get('html_url', '')}\n"
                    f"  Topic: {', '.join(item.get('topics', [])[:5])}"
                )
            return results, data.get("total_count", 0)
        except Exception:
            return [], 0

    async def _search_pypi(self, query: str) -> list[str]:
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(15)) as c:
                resp = await c.get(
                    f"https://pypi.org/pypi/{query}/json",
                    headers={"User-Agent": "CodeCraft/1.0"},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    info = data.get("info", {})
                    return [
                        f"[PyPI] {info.get('name', query)} v{info.get('version', '?')}\n"
                        f"  {info.get('summary', '')[:200]}\n"
                        f"  pip install {info.get('name', query)}"
                    ]
        except Exception:
            pass
        return []

    async def _search_npm(self, query: str) -> list[str]:
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(15)) as c:
                resp = await c.get(
                    "https://registry.npmjs.org/-/v1/search",
                    params={"text": query, "size": 3},
                    headers={"User-Agent": "CodeCraft/1.0"},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    results = []
                    for item in data.get("objects", [])[:3]:
                        pkg = item.get("package", {})
                        results.append(
                            f"[npm] {pkg.get('name', '?')} v{pkg.get('version', '?')}\n"
                            f"  {pkg.get('description', '')[:200]}\n"
                            f"  npm install {pkg.get('name', '?')}"
                        )
                    return results
        except Exception:
            pass
        return []

    def _parse_items(self, items: list[str], source: str) -> list[dict[str, Any]]:
        parsed = []
        for item in items:
            source_name = ""
            install_cmd = ""
            if source == "pypi":
                for line in item.split("\n"):
                    if line.startswith("[PyPI]"):
                        source_name = line.split("] ")[-1].split(" v")[0].strip()
                    if "pip install" in line:
                        install_cmd = line.strip()
            elif source == "npm":
                for line in item.split("\n"):
                    if line.startswith("[npm]"):
                        source_name = line.split("] ")[-1].split(" v")[0].strip()
                    if "npm install" in line:
                        install_cmd = line.strip()
            if source_name:
                parsed.append({
                    "source": source,
                    "name": source_name,
                    "install": install_cmd,
                    "raw": item,
                })
        return parsed

    async def _auto_install(self, finding: dict[str, Any]) -> str:
        install_cmd = finding.get("install", "")
        if not install_cmd:
            return "No install command available"

        try:
            proc = await asyncio.create_subprocess_shell(
                install_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.workdir,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
            if proc.returncode == 0:
                return f"✓ Installed: {install_cmd}\n{stdout.decode()[:500]}"
            return f"✗ Install failed: {stderr.decode()[:500]}"
        except Exception as e:
            return f"✗ Install error: {e}"

    async def _create_custom_tool(self, need: str, language: str) -> str:
        """Generate Python code for a custom tool that fulfills the need."""
        if language.lower() == "python":
            tool_code = f'''"""
Auto-generated tool for: {need}
Created by CodeCraft ToolDiscovery
"""
import subprocess
import json
from pathlib import Path


def run_{need.replace(" ", "_").replace("-", "_").lower()[:30]}(*args, **kwargs):
    """Auto-generated handler for: {need}"""
    # TODO: Implement the specific logic for this tool
    # This is a scaffold - the calling agent should customize it
    return {{"status": "ok", "message": "Auto-created tool for: {need}"}}


if __name__ == "__main__":
    import sys
    result = run_{need.replace(" ", "_").replace("-", "_").lower()[:30]}(*sys.argv[1:])
    print(json.dumps(result))
'''
        else:
            tool_code = f'// Auto-generated tool for: {need}\n// Created by CodeCraft ToolDiscovery\n\nconsole.log("Tool for: {need}");'

        tool_path = Path(self.workdir) / f"tool_{need.replace(' ', '_').replace('-', '_').lower()[:30]}.py"
        tool_path.write_text(tool_code)
        self._created_tools.append({"need": need, "path": str(tool_path), "code": tool_code})

        return tool_code

    def get_created_tools(self) -> list[dict[str, Any]]:
        return list(self._created_tools)

    def get_parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "need": {
                    "type": "string",
                    "description": "Describe what tool/plugin/function you need (e.g. 'PDF generation', 'image compression', 'OAuth2 flow')",
                },
                "language": {
                    "type": "string",
                    "description": "Preferred programming language (python, javascript, rust)",
                },
                "auto_install": {
                    "type": "boolean",
                    "description": "Automatically install the best match if found",
                },
            },
            "required": ["need"],
        }

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

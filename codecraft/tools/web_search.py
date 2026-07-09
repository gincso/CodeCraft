from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional
from urllib.parse import quote_plus

import httpx

from codecraft.tools.base import BaseTool, ToolResult, ToolRisk

logger = logging.getLogger(__name__)


class WebSearchTool(BaseTool):
    name = "web_search"
    description = "Search the web for information. Returns top results with titles, URLs, and snippets."
    risk = ToolRisk.NETWORK

    def __init__(self, workdir: str | None = None):
        super().__init__(workdir)
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(30),
                headers={
                    "User-Agent": "CodeCraft/1.0 (AI Agent Research Tool)",
                },
            )
        return self._client

    async def execute(self, query: str, num_results: int = 5, **kwargs: Any) -> ToolResult:
        try:
            results = await self._duckduckgo_search(query, num_results)
            if not results:
                results = await self._google_search(query, num_results)
            if not results:
                results = await self._brave_search(query, num_results)

            if not results:
                return ToolResult(
                    success=False,
                    output="",
                    error="No search results found. Search engines may be unavailable.",
                )

            formatted = [f"{r['title']}\n  {r['url']}\n  {r['snippet']}" for r in results]
            return ToolResult(
                success=True,
                output="\n\n".join(formatted),
                metadata={"query": query, "result_count": len(results)},
            )
        except Exception as e:
            logger.exception(f"Web search failed: {e}")
            return ToolResult(success=False, output="", error=str(e))

    async def _duckduckgo_search(self, query: str, num: int) -> list[dict[str, str]]:
        try:
            resp = await self.client.get(
                "https://lite.duckduckgo.com/lite/",
                params={"q": query},
                follow_redirects=True,
            )
            if resp.status_code != 200:
                return []

            results: list[dict[str, str]] = []
            text = resp.text
            import re

            link_pattern = re.compile(
                r'<a[^>]*href="([^"]*uddg=([^"&]*)[^"]*)"[^>]*class="result-link"[^>]*>(.*?)</a>',
                re.DOTALL,
            )
            snippet_pattern = re.compile(
                r'<td[^>]*class="result-snippet"[^>]*>(.*?)</td>', re.DOTALL
            )

            links = link_pattern.findall(text)
            snippets = snippet_pattern.findall(text)

            for i, (full_url, encoded_url, title) in enumerate(links[:num]):
                clean_title = re.sub(r"<[^>]+>", "", title).strip()
                clean_url = quote_plus(encoded_url, safe="")
                try:
                    clean_url = httpx.URL(encoded_url).host or clean_url
                except Exception:
                    pass
                snippet = ""
                if i < len(snippets):
                    snippet = re.sub(r"<[^>]+>", "", snippets[i]).strip()
                results.append({"title": clean_title or query, "url": clean_url, "snippet": snippet[:300]})
            return results
        except Exception:
            return []

    async def _google_search(self, query: str, num: int) -> list[dict[str, str]]:
        try:
            resp = await self.client.get(
                "https://www.google.com/search",
                params={"q": query, "num": str(num)},
                headers={
                    "Accept": "text/html",
                    "User-Agent": "Mozilla/5.0 (compatible; CodeCraft/1.0)",
                },
            )
            if resp.status_code != 200:
                return []

            import re
            text = resp.text
            results: list[dict[str, str]] = []

            result_blocks = re.findall(r'<div class="g">(.*?)</div>\s*<div class="g">', text, re.DOTALL)
            if not result_blocks:
                result_blocks = re.findall(r'<div class="g">(.*?)</div>$', text, re.DOTALL)

            for block in result_blocks[:num]:
                url_match = re.search(r'href="(https?://[^"]+)"', block)
                title_match = re.search(r'<h3[^>]*>(.*?)</h3>', block, re.DOTALL)
                snippet_match = re.search(
                    r'<span class="[^"]*st[^"]*"[^>]*>(.*?)</span>', block, re.DOTALL
                )
                if title_match:
                    title = re.sub(r"<[^>]+>", "", title_match.group(1)).strip()
                    url = url_match.group(1) if url_match else ""
                    snippet = (
                        re.sub(r"<[^>]+>", "", snippet_match.group(1)).strip()
                        if snippet_match
                        else ""
                    )
                    results.append({"title": title, "url": url, "snippet": snippet[:300]})
            return results
        except Exception:
            return []

    async def _brave_search(self, query: str, num: int) -> list[dict[str, str]]:
        return []

    def get_parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "num_results": {"type": "integer", "description": "Number of results to return"},
            },
            "required": ["query"],
        }

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None


class WebFetchTool(BaseTool):
    name = "web_fetch"
    description = "Fetch and extract content from a URL as text or markdown."
    risk = ToolRisk.NETWORK

    def __init__(self, workdir: str | None = None):
        super().__init__(workdir)
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(30),
                headers={"User-Agent": "CodeCraft/1.0"},
                follow_redirects=True,
            )
        return self._client

    async def execute(self, url: str, format: str = "text", **kwargs: Any) -> ToolResult:
        try:
            resp = await self.client.get(url)
            resp.raise_for_status()
            text = resp.text

            if format == "markdown":
                text = self._html_to_markdown(text)
            else:
                text = self._strip_html(text)
                text = text[:10000]

            return ToolResult(
                success=True,
                output=text[:10000],
                metadata={"url": url, "status_code": resp.status_code, "content_type": resp.headers.get("content-type", "")},
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    @staticmethod
    def _strip_html(html: str) -> str:
        import re
        text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    @staticmethod
    def _html_to_markdown(html: str) -> str:
        try:
            import re
            text = re.sub(r"<h1[^>]*>(.*?)</h1>", r"# \1\n", html, flags=re.DOTALL)
            text = re.sub(r"<h2[^>]*>(.*?)</h2>", r"## \1\n", text, flags=re.DOTALL)
            text = re.sub(r"<h3[^>]*>(.*?)</h3>", r"### \1\n", text, flags=re.DOTALL)
            text = re.sub(r"<p[^>]*>(.*?)</p>", r"\1\n\n", text, flags=re.DOTALL)
            text = re.sub(r"<li[^>]*>(.*?)</li>", r"- \1\n", text, flags=re.DOTALL)
            text = re.sub(r"<strong[^>]*>(.*?)</strong>", r"**\1**", text, flags=re.DOTALL)
            text = re.sub(r"<b[^>]*>(.*?)</b>", r"**\1**", text, flags=re.DOTALL)
            text = re.sub(r"<em[^>]*>(.*?)</em>", r"*\1*", text, flags=re.DOTALL)
            text = re.sub(r"<a[^>]*href=\"([^\"]*)\"[^>]*>(.*?)</a>", r"[\2](\1)", text, flags=re.DOTALL)
            text = re.sub(r"<br\s*/?>", "\n", text)
            text = re.sub(r"<[^>]+>", "", text)
            text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
            return text.strip()[:10000]
        except Exception:
            return WebFetchTool._strip_html(html)[:10000]

    def get_parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to fetch"},
                "format": {"type": "string", "enum": ["text", "markdown"], "description": "Output format"},
            },
            "required": ["url"],
        }

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

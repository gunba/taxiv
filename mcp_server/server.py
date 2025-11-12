"""
MCP server for Taxiv semantic search and provision detail exploration.
Exposes LLM tools via FastMCP (SSE transport).

All tool outputs default to **markdown**. Pass `format="json"` for raw payloads.
"""

from __future__ import annotations

import asyncio
import atexit
import json
import os
from typing import Any, Dict, List, Optional

from urllib.parse import quote

import httpx
from fastmcp import FastMCP

from mcp_server.mcp_formatter import (
        format_provision_detail_md,
        format_search_results_md,
        mmd_escape,
)

BACKEND_BASE_URL = os.environ.get("BACKEND_BASE_URL", "http://backend:8000")
REQUEST_TIMEOUT = float(os.environ.get("MCP_HTTP_TIMEOUT", "30"))

INSTRUCTIONS = """
You are connected to the Taxiv MCP server.

**Tools**
- `capabilities()`: list supported acts and the default scope (currently ITAA1997).
- `semantic_search(query, k=10, offset=0)`: run unified search and receive provision headers plus a ~120-character content snippet. Pagination metadata (offset/limit/next_offset) is returned for deep dives.
- `provision_detail(internal_id, include_breadcrumbs=False, include_children=False, include_definitions=False, include_references=True, fields=None, format='markdown'|'json')`: fetch a single provision. Lean view omits expensive expansions unless toggled. The backend echoes `etag`, `last_modified`, `size_bytes`, and normalized parses for flexible tokens like "s 6-5".
- `batch_provisions(ids, include_breadcrumbs=False, include_children=False, include_definitions=False, include_references=True, fields=None, format='json')`: hydrate multiple provisions in one call with the same expansion flags as `provision_detail`.

**Workflow**
1. Start with a targeted `semantic_search`. Prefer explicit identifiers (e.g., "s 6-5 ordinary income"), adjust `offset` to paginate through longer result sets, and keep `k` focused (10–25).
2. Use `provision_detail` or `batch_provisions` to expand interesting IDs. Request only the fields you need to keep responses small.
3. Call `capabilities` to confirm the active Acts when planning broader queries.
4. Pass `format="json"` whenever you need structured data for follow-up reasoning; markdown summaries are produced by default.
"""
class Backend:
	def __init__(self, base_url: str, timeout: float = 30):
		self.base_url = base_url.rstrip("/")
		self.client = httpx.AsyncClient(timeout=timeout)

	async def close(self):
		await self.client.aclose()

        async def unified_search(
                self,
                query: str,
                k: int = 10,
                offset: int = 0,
                act_id: Optional[str] = None,
        ) -> Dict[str, Any]:
                url = f"{self.base_url}/api/search/unified"
                payload: Dict[str, Any] = {"query": query, "k": k, "offset": offset}
                if act_id:
                        payload["act_id"] = act_id
                r = await self.client.post(url, json=payload)
                r.raise_for_status()
                return r.json()

        async def get_detail(
                self,
                internal_id: str,
                *,
                include_breadcrumbs: bool = False,
                include_children: bool = False,
                include_definitions: bool = False,
                include_references: bool = True,
                fields: Optional[List[str]] = None,
        ) -> Dict[str, Any]:
                safe_id = quote(internal_id, safe="")
                url = f"{self.base_url}/api/provisions/detail/{safe_id}"
                params: Dict[str, Any] = {
                        "format": "json",
                        "include_breadcrumbs": include_breadcrumbs,
                        "include_children": include_children,
                        "include_definitions": include_definitions,
                        "include_references": include_references,
                }
                if fields:
                        params["fields"] = fields
                r = await self.client.get(url, params=params)
                r.raise_for_status()
                return r.json()

        async def batch_details(
                self,
                *,
                ids: List[str],
                include_breadcrumbs: bool = False,
                include_children: bool = False,
                include_definitions: bool = False,
                include_references: bool = True,
                fields: Optional[List[str]] = None,
        ) -> Dict[str, Any]:
                url = f"{self.base_url}/api/batch_provisions"
                payload: Dict[str, Any] = {
                        "ids": ids,
                        "include_breadcrumbs": include_breadcrumbs,
                        "include_children": include_children,
                        "include_definitions": include_definitions,
                        "include_references": include_references,
                }
                if fields:
                        payload["fields"] = fields
                r = await self.client.post(url, json=payload)
                r.raise_for_status()
                return r.json()

        async def get_capabilities(self) -> Dict[str, Any]:
                url = f"{self.base_url}/capabilities"
                r = await self.client.get(url)
                r.raise_for_status()
                return r.json()
def create_server() -> FastMCP:
	mcp = FastMCP(name="Taxiv MCP", instructions=INSTRUCTIONS)
	be = Backend(BACKEND_BASE_URL, timeout=REQUEST_TIMEOUT)

	if hasattr(mcp, "on_shutdown"):
		@mcp.on_shutdown
		async def _shutdown():
			await be.close()
	else:
		def _sync_shutdown():
			if getattr(be.client, "is_closed", False):
				return
			try:
				asyncio.run(be.close())
			except RuntimeError:
				loop = asyncio.new_event_loop()
				try:
					loop.run_until_complete(be.close())
				finally:
					loop.close()

		atexit.register(_sync_shutdown)

	@mcp.tool()
	async def help() -> str:
		"""
		Show best-practice guidance for using this MCP server.
		"""
		return INSTRUCTIONS.strip()

        @mcp.tool()
        async def semantic_search(
                query: str,
                k: int = 10,
                offset: int = 0,
                format: str = "markdown",
                act_id: Optional[str] = None,
        ) -> str:
                """
                Run semantic/relatedness search. Returns provision headers only so you can drill down safely.
                """
                if not query or not query.strip():
                        return "_Empty query supplied._"

                payload = await be.unified_search(
                        query=query,
                        k=min(max(int(k), 1), 100),
                        offset=max(int(offset), 0),
                        act_id=act_id,
                )
		if format.lower() == "json":
			return "```json\n" + json.dumps(payload, indent=2) + "\n```"
		return format_search_results_md(payload)

        @mcp.tool()
        async def provision_detail(
                internal_id: str,
                format: str = "markdown",
                include_breadcrumbs: bool = False,
                include_children: bool = False,
                include_definitions: bool = False,
                include_references: bool = True,
                fields: Optional[str] = None,
        ) -> str:
                """
                Fetch a provision (content + hierarchy + references + definitions).
                """
                if not internal_id or not internal_id.strip():
                        return "_No internal_id supplied._"
                field_values: Optional[List[str]] = None
                if fields:
                        parsed_fields = [segment.strip() for segment in fields.split(',') if segment.strip()]
                        if parsed_fields:
                                field_values = parsed_fields
                try:
                        detail = await be.get_detail(
                                internal_id=internal_id.strip(),
                                include_breadcrumbs=include_breadcrumbs,
                                include_children=include_children,
                                include_definitions=include_definitions,
                                include_references=include_references,
                                fields=field_values,
                        )
                except httpx.HTTPStatusError as exc:
                        if exc.response.status_code == 404:
                                return f"_Provision `{internal_id}` not found._"
                        raise

                if format.lower() == "json":
                        return "```json\n" + json.dumps(detail, indent=2) + "\n```"
                return format_provision_detail_md(detail)

        @mcp.tool()
        async def batch_provisions(
                ids: List[str],
                include_breadcrumbs: bool = False,
                include_children: bool = False,
                include_definitions: bool = False,
                include_references: bool = True,
                fields: Optional[str] = None,
                format: str = "json",
        ) -> str:
                """
                Fetch multiple provisions in a single backend round trip.
                """
                if not ids:
                        return "_No ids supplied._"
                field_values: Optional[List[str]] = None
                if fields:
                        parsed_fields = [segment.strip() for segment in fields.split(',') if segment.strip()]
                        if parsed_fields:
                                field_values = parsed_fields
                payload = await be.batch_details(
                        ids=ids,
                        include_breadcrumbs=include_breadcrumbs,
                        include_children=include_children,
                        include_definitions=include_definitions,
                        include_references=include_references,
                        fields=field_values,
                )
                if format.lower() == "json":
                        return "```json\n" + json.dumps(payload, indent=2) + "\n```"
                lines = ["### Batch provisions"]
                for item in payload.get("results", []):
                        requested = item.get("requested_id", "(unknown)")
                        internal_id = item.get("internal_id", "(missing)")
                        title = item.get("title") or item.get("ref_id") or internal_id
                        if "error" in item:
                                lines.append(f"- `{requested}` — ❌ {item['error']}")
                        else:
                                lines.append(f"- `{requested}` → `{internal_id}` — {mmd_escape(title)}")
                return "\n".join(lines)

        @mcp.tool()
        async def capabilities(format: str = "json") -> str:
                """
                List the supported Acts and defaults for this MCP deployment.
                """
                data = await be.get_capabilities()
                if format.lower() == "json":
                        return "```json\n" + json.dumps(data, indent=2) + "\n```"
                lines = ["### Capabilities"]
                acts = data.get("acts", []) or []
                lines.append(f"- default_act: `{data.get('default_act')}`")
                if acts:
                        lines.append(f"- acts: `{', '.join(acts)}`")
                else:
                        lines.append("- acts: `(none reported)`")
                return "\n".join(lines)

        return mcp


def main():
	server = create_server()
	host = os.environ.get("MCP_HOST", "0.0.0.0")
	port = int(os.environ.get("MCP_PORT", "8765"))
	# SSE transport is the default recommended mode for ChatGPT / connectors.
	server.run(transport="sse", host=host, port=port)


if __name__ == "__main__":
	main()

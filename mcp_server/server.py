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
from typing import Any, Dict

import httpx
from fastmcp import FastMCP

from backend.services.mcp_formatter import format_provision_detail_md, format_search_results_md

BACKEND_BASE_URL = os.environ.get("BACKEND_BASE_URL", "http://backend:8000")
REQUEST_TIMEOUT = float(os.environ.get("MCP_HTTP_TIMEOUT", "30"))

INSTRUCTIONS = """
You are connected to the Taxiv MCP server.

**Tools**
- `semantic_search(query, k=25)`: run unified semantic search and receive provision headers plus a ~120-char content snippet (or `No content`). Use this to shortlist nodes.
- `provision_detail(internal_id)`: fetch a single provision with markdown content, breadcrumbs, children, references, and every definition it uses (each bundled with its own references).

**Workflow**
1. Start with a targeted `semantic_search`. Prefer explicit identifiers (e.g., "s 6-5 active asset") and keep `k` small (10–25).
2. Drill into interesting IDs via `provision_detail` to pull the full context plus safe navigation metadata.
3. Pass `format="json"` whenever you need structured data for follow-up reasoning; markdown summaries are produced by default.
"""
class Backend:
	def __init__(self, base_url: str, timeout: float = 30):
		self.base_url = base_url.rstrip("/")
		self.client = httpx.AsyncClient(timeout=timeout)

	async def close(self):
		await self.client.aclose()

	async def unified_search(self, query: str, k: int = 25) -> Dict[str, Any]:
		url = f"{self.base_url}/api/search/unified"
		payload = {"query": query, "k": k}
		r = await self.client.post(url, json=payload)
		r.raise_for_status()
		return r.json()

	async def get_detail(self, internal_id: str) -> Dict[str, Any]:
		url = f"{self.base_url}/api/provisions/detail/{internal_id}"
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
	async def semantic_search(query: str, k: int = 25, format: str = "markdown") -> str:
		"""
		Run semantic/relatedness search. Returns provision headers only so you can drill down safely.
		"""
		if not query or not query.strip():
			return "_Empty query supplied._"

		payload = await be.unified_search(
			query=query,
			k=min(max(int(k), 1), 100),
		)
		if format.lower() == "json":
			return "```json\n" + json.dumps(payload, indent=2) + "\n```"
		return format_search_results_md(payload)

	@mcp.tool()
	async def provision_detail(internal_id: str, format: str = "markdown") -> str:
		"""
		Fetch a provision (content + hierarchy + references + definitions).
		"""
		if not internal_id or not internal_id.strip():
			return "_No internal_id supplied._"
		try:
			detail = await be.get_detail(internal_id=internal_id.strip())
		except httpx.HTTPStatusError as exc:
			if exc.response.status_code == 404:
				return f"_Provision `{internal_id}` not found._"
			raise

		if format.lower() == "json":
			return "```json\n" + json.dumps(detail, indent=2) + "\n```"
		return format_provision_detail_md(detail)

	return mcp


def main():
	server = create_server()
	host = os.environ.get("MCP_HOST", "0.0.0.0")
	port = int(os.environ.get("MCP_PORT", "8765"))
	# SSE transport is the default recommended mode for ChatGPT / connectors.
	server.run(transport="sse", host=host, port=port)


if __name__ == "__main__":
	main()

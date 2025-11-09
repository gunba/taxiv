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
import textwrap
from typing import Any, Dict, List

import httpx
from fastmcp import FastMCP

BACKEND_BASE_URL = os.environ.get("BACKEND_BASE_URL", "http://backend:8000")
REQUEST_TIMEOUT = float(os.environ.get("MCP_HTTP_TIMEOUT", "30"))

INSTRUCTIONS = """
You are connected to the Taxiv MCP server.

**Tools**
- `semantic_search(query, k=25)`: run unified semantic search and receive only provision headers (internal_id, ref_id, title, URS score). Use this to shortlist nodes.
- `provision_detail(internal_id)`: fetch a single provision with markdown content, breadcrumbs, children, references, and every definition it uses (each bundled with its own references).

**Workflow**
1. Start with a targeted `semantic_search`. Prefer explicit identifiers (e.g., "s 6-5 active asset") and keep `k` small (10–25).
2. Drill into interesting IDs via `provision_detail` to pull the full context plus safe navigation metadata.
3. Pass `format="json"` whenever you need structured data for follow-up reasoning; markdown summaries are produced by default.
"""


def mmd_escape(text: str) -> str:
	"""Light escape for markdown text in inline contexts."""
	return text.replace("<", "&lt;").replace(">", "&gt;").strip()


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


def format_search_results_md(payload: Dict[str, Any]) -> str:
	qi = payload.get("query_interpretation", {})
	results = payload.get("results", [])
	dbg = payload.get("debug", {}) or {}

	parts: List[str] = []
	# Query interpretation
	parts.append("### Query interpretation")
	lines = []
	provs = qi.get("provisions", [])
	defs = qi.get("definitions", [])
	kws = qi.get("keywords", "")
	if provs:
		lines.append(f"- provisions: `{', '.join(provs)}`")
	if defs:
		lines.append(f"- definitions: `{', '.join(defs)}`")
	if kws:
		lines.append(f"- keywords: `{mmd_escape(kws)}`")
	if not lines:
		lines.append("- *(no structured seeds; likely free-text)*")
	parts.append("\n".join(lines))

	# Results
	parts.append("\n### Top results")
	if not results:
		parts.append("> No results.")
	else:
		for i, item in enumerate(results, start=1):
			title = mmd_escape(item.get("title", ""))
			ref_id = item.get("ref_id", "")
			iid = item.get("id", "")
			typ = item.get("type", "")
			urs = item.get("score_urs", 0)
			label = title or ref_id or iid or "(untitled)"
			meta_bits = [
				f"`{ref_id}`" if ref_id else None,
				f"*{typ}*" if typ else None,
				f"URS **{urs}**",
			]
			meta = " — ".join(bit for bit in meta_bits if bit)
			parts.append(f"**{i}. {label}**  \n{meta}  \n`internal_id: {iid}`")
	# Debug
	parts.append("\n### Debug")
	parts.append(f"- mass_captured: `{dbg.get('mass_captured', 0)}`")
	parts.append(f"- num_seeds: `{dbg.get('num_seeds', 0)}`")

	# Hints
	parts.append(textwrap.dedent("""
	---
	**Next steps**
	- Call `provision_detail` with an `internal_id` from above to expand the node safely.
	""").strip())

	return "\n".join(parts).strip()


def _format_reference_lines(references: List[Dict[str, Any]]) -> List[str]:
	lines: List[str] = []
	for ref in references:
		title = mmd_escape(ref.get("target_title") or ref.get("target_ref_id") or "Referenced provision")
		ref_id = ref.get("target_ref_id", "")
		iid = ref.get("target_internal_id")
		lines.append(f"- **{title}**")
		meta = []
		if ref_id:
			meta.append(f"`{ref_id}`")
		if iid:
			meta.append(f"`internal_id: {iid}`")
		if meta:
			lines.append(f"  {', '.join(meta)}")
		snippet = ref.get("snippet")
		if snippet:
			lines.append(f"  \n  > {mmd_escape(snippet)}")
	return lines


def format_provision_detail_md(detail: Dict[str, Any]) -> str:
	parts: List[str] = []
	title = mmd_escape(detail.get("title", ""))
	ref_id = detail.get("ref_id", "")
	internal_id = detail.get("internal_id", "")
	header = title or ref_id or internal_id or "Provision detail"
	parts.append(f"## {header}")
	meta_bits = []
	if ref_id:
		meta_bits.append(f"`{ref_id}`")
	if internal_id:
		meta_bits.append(f"`internal_id: {internal_id}`")
	if detail.get("type"):
		meta_bits.append(f"*{detail['type']}*")
	if meta_bits:
		parts.append(" ".join(meta_bits))

	breadcrumbs = detail.get("breadcrumbs") or []
	if breadcrumbs:
		breadcrumb_line = " ⟶ ".join(mmd_escape(b.get("title", "")) for b in breadcrumbs)
		parts.append("\n### Breadcrumbs")
		parts.append(breadcrumb_line)

	children = detail.get("children") or []
	if children:
		child_lines = []
		for child in children:
			label = mmd_escape(child.get("title", "") or child.get("ref_id", ""))
			child_lines.append(f"- **{label}**  \n  `{child.get('ref_id', '')}` — `internal_id: {child.get('internal_id', '')}`")
		parts.append("\n### Children")
		parts.append("\n".join(child_lines))

	content = detail.get("content_md")
	if content:
		parts.append("\n### Content")
		parts.append(content.strip())

	references = detail.get("references_to") or []
	if references:
		parts.append("\n### References")
		parts.append("\n".join(_format_reference_lines(references)))

	referenced_by = detail.get("referenced_by") or []
	if referenced_by:
		lines = []
		for item in referenced_by:
			title_rb = mmd_escape(item.get("source_title", ""))
			lines.append(f"- **{title_rb}**  \n  `{item.get('source_ref_id', '')}` — `internal_id: {item.get('source_internal_id', '')}`")
		parts.append("\n### Referenced by")
		parts.append("\n".join(lines))

	definitions = detail.get("definitions_with_references") or []
	if definitions:
		lines = []
		for definition in definitions:
			label = mmd_escape(definition.get("title", "") or "Definition")
			ref = definition.get("ref_id") or ""
			ref_label = f" `{ref}`" if ref else ""
			lines.append(f"- **{label}**{ref_label}")
			terms = definition.get("term_texts") or []
			if terms:
				term_tokens = [f"`{mmd_escape(term)}`" for term in terms]
				lines.append(f"  Terms: {', '.join(term_tokens)}")
			def_content = definition.get("content_md")
			if def_content:
				content_block = mmd_escape(def_content).replace("\n", "\n  > ")
				lines.append(f"  > {content_block}")
			ref_lines = _format_reference_lines(definition.get("references_to") or [])
			if ref_lines:
				lines.append("  References:")
				lines.extend([f"  {line}" for line in ref_lines])
		parts.append("\n### Definitions")
		parts.append("\n".join(lines))

	return "\n".join(part for part in parts if part).strip()


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

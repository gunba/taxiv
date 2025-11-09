from __future__ import annotations

import textwrap
from typing import Any, Dict, List, Mapping, Sequence


def _to_dict(model: Any) -> Dict[str, Any]:
	if isinstance(model, dict):
		return model
	if hasattr(model, "model_dump"):
		return model.model_dump()
	if hasattr(model, "dict"):
		return model.dict()
	if hasattr(model, "__dict__"):
		return dict(model.__dict__)
	raise TypeError("Unsupported detail payload for formatting")


def mmd_escape(text: str | None) -> str:
	if not text:
		return ""
	return text.replace("<", "&lt;").replace(">", "&gt;").strip()


def _format_reference_lines(references: Sequence[Mapping[str, Any]] | None) -> List[str]:
	lines: List[str] = []
	if not references:
		return lines
	for ref in references:
		if not ref.get("target_internal_id"):
			# Skip references we cannot dereference safely.
			continue
		title = mmd_escape(ref.get("target_title") or ref.get("target_ref_id") or "Referenced provision")
		ref_id = ref.get("target_ref_id") or ""
		lines.append(f"- **{title}**")
		if ref_id:
			lines.append(f"  `{ref_id}`")
	return lines


def _definition_content_snippet(content_md: str | None) -> str:
	if not content_md:
		return ""
	block = content_md.strip().split("\n\n", 1)[0]
	return mmd_escape(block)


def format_search_results_md(payload: Mapping[str, Any]) -> str:
	data = _to_dict(payload)
	qi = data.get("query_interpretation", {}) or {}
	results = data.get("results", []) or []
	dbg = data.get("debug", {}) or {}

	parts: List[str] = []
	parts.append("### Query interpretation")
	lines: List[str] = []
	provs = qi.get("provisions") or []
	defs = qi.get("definitions") or []
	kws = qi.get("keywords") or ""
	if provs:
		lines.append(f"- provisions: `{', '.join(provs)}`")
	if defs:
		lines.append(f"- definitions: `{', '.join(defs)}`")
	if kws:
		lines.append(f"- keywords: `{mmd_escape(kws)}`")
	if not lines:
		lines.append("- *(no structured seeds; likely free-text)*")
	parts.append("\n".join(lines))

	parts.append("\n### Top results")
	if not results:
		parts.append("> No results.")
	else:
		for idx, item in enumerate(results, start=1):
			title = mmd_escape(item.get("title"))
			ref_id = item.get("ref_id") or ""
			iid = item.get("id") or ""
			typ = item.get("type") or ""
			urs = item.get("score_urs") or 0
			snippet = mmd_escape(item.get("content_snippet"))
			label = title or ref_id or iid or "(untitled)"
			meta_bits = [
				f"`{ref_id}`" if ref_id else None,
				f"*{typ}*" if typ else None,
				f"URS **{urs}**",
			]
			meta = " — ".join(bit for bit in meta_bits if bit)
			entry_lines = [f"**{idx}. {label}**"]
			if meta:
				entry_lines.append(meta)
			entry_lines.append(f"`internal_id: {iid}`")
			if snippet:
				entry_lines.append(f"> {snippet}")
			parts.append("  \n".join(entry_lines))

	parts.append("\n### Debug")
	parts.append(f"- mass_captured: `{dbg.get('mass_captured', 0)}`")
	parts.append(f"- num_seeds: `{dbg.get('num_seeds', 0)}`")

	parts.append(textwrap.dedent(
		"""
		---
		**Next steps**
		- Call `provision_detail` with an `internal_id` from above to expand the node safely.
		"""
	).strip())

	return "\n".join(parts).strip()


def format_provision_detail_md(detail: Any) -> str:
	data = _to_dict(detail)
	parts: List[str] = []
	title = mmd_escape(data.get("title"))
	ref_id = data.get("ref_id") or ""
	internal_id = data.get("internal_id") or ""
	header = title or ref_id or internal_id or "Provision detail"
	parts.append(f"## {header}")
	meta_bits: List[str] = []
	if ref_id:
		meta_bits.append(f"`{ref_id}`")
	typ = data.get("type")
	if typ:
		meta_bits.append(f"*{typ}*")
	if meta_bits:
		parts.append(" ".join(meta_bits))

	breadcrumbs = data.get("breadcrumbs") or []
	if breadcrumbs:
		breadcrumb_line = " ⟶ ".join(mmd_escape(b.get("title")) for b in breadcrumbs)
		parts.append("\n### Breadcrumbs")
		parts.append(breadcrumb_line)

	children = data.get("children") or []
	if children:
		child_lines = []
		for child in children:
			label = mmd_escape(child.get("title") or child.get("ref_id"))
			child_lines.append(
				f"- **{label}**  \n  `{child.get('ref_id', '')}` — `internal_id: {child.get('internal_id', '')}`"
			)
		parts.append("\n### Children")
		parts.append("\n".join(child_lines))

	content = data.get("content_md")
	if content:
		parts.append("\n### Content")
		parts.append(content.strip())

	references = data.get("references_to") or []
	filtered_refs = _format_reference_lines(references)
	if filtered_refs:
		parts.append("\n### References")
		parts.append("\n".join(filtered_refs))

	definitions = data.get("definitions_with_references") or []
	if definitions:
		lines = []
		for definition in definitions:
			label = mmd_escape(definition.get("title") or "Definition")
			ref = definition.get("ref_id") or ""
			ref_label = f" `{ref}`" if ref else ""
			lines.append(f"- \"{label}\"{ref_label}")
			content_block = _definition_content_snippet(definition.get("content_md"))
			if content_block:
				snippet = content_block.replace("\n", "\n    ")
				lines.append(f"    {snippet}")
			ref_lines = _format_reference_lines(definition.get("references_to"))
			if ref_lines:
				lines.extend([f"    {line}" for line in ref_lines])
			lines.append("")
		parts.append("\n### Definitions")
		parts.append("\n".join(lines))

	return "\n".join(part for part in parts if part).strip()

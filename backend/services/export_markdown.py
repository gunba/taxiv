"""Utilities for exporting provision subtrees into Markdown."""

from __future__ import annotations

import re
from collections import deque
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from sqlalchemy.orm import Session
from sqlalchemy_utils import Ltree

from backend import crud
from backend.models import legislation as models
from backend.schemas import ProvisionDetail

IMAGE_PATTERN = re.compile(r"!\[(?P<alt>[^\]]*)\]\([^\)]+\)")


def canonical_node_heading(detail: ProvisionDetail) -> str:
	"""Generate a canonical heading for a provision node."""
	title = detail.title.strip()
	if title:
		return title
	ref = detail.ref_id.strip() if detail.ref_id else ""
	return ref


def normalize_markdown_content(content: Optional[str]) -> str:
	"""Replace embedded images with their alt text and trim extraneous whitespace."""
	if not content:
		return ""

	def _replace(match: re.Match[str]) -> str:
		alt_text = match.group("alt").strip()
		return alt_text or "Image"

	return IMAGE_PATTERN.sub(_replace, content).strip()


def _unique_by_internal_id(details: Iterable[ProvisionDetail]) -> List[ProvisionDetail]:
	seen: Set[str] = set()
	ordered: List[ProvisionDetail] = []
	for detail in details:
		if detail.internal_id in seen:
			continue
		seen.add(detail.internal_id)
		ordered.append(detail)
	return ordered


def _collect_subtree_details(
		db: Session,
		root_internal_id: str,
		include_descendants: bool,
) -> List[ProvisionDetail]:
	root = db.get(models.Provision, root_internal_id)
	if not root:
		return []

	if not include_descendants:
		detail = crud.get_provision_detail(db, root_internal_id)
		return [detail] if detail else []

	if not root.hierarchy_path_ltree:
		return []

	path = Ltree(str(root.hierarchy_path_ltree))
	rows = (
		db.query(models.Provision.internal_id)
		.filter(models.Provision.hierarchy_path_ltree.op('<@')(path))
		.order_by(models.Provision.hierarchy_path_ltree, models.Provision.sibling_order)
		.all()
	)

	details: List[ProvisionDetail] = []
	for row in rows:
		detail = crud.get_provision_detail(db, row.internal_id)
		if detail:
			details.append(detail)
	return details


def _gather_referenced_ids(
		details: Sequence[ProvisionDetail],
		exclude_ids: Set[str],
) -> List[str]:
	seen: Set[str] = set()
	ordered: List[str] = []
	for detail in details:
		for ref in detail.references_to:
			if not ref.target_internal_id or ref.target_internal_id in exclude_ids:
				continue
			if ref.target_internal_id in seen:
				continue
			seen.add(ref.target_internal_id)
			ordered.append(ref.target_internal_id)
	return ordered


def _collect_definitions(
		db: Session,
		seed_details: Sequence[ProvisionDetail],
		exclude_ids: Set[str],
) -> List[ProvisionDetail]:
	queue: deque[str] = deque()
	seen: Set[str] = set()
	for detail in seed_details:
		for usage in detail.defined_terms_used:
			if not usage.definition_internal_id or usage.definition_internal_id in exclude_ids:
				continue
			if usage.definition_internal_id in seen:
				continue
			seen.add(usage.definition_internal_id)
			queue.append(usage.definition_internal_id)

	definitions: List[ProvisionDetail] = []
	while queue:
		definition_id = queue.popleft()
		if definition_id in exclude_ids:
			continue
		detail = crud.get_provision_detail(db, definition_id)
		if not detail:
			continue
		definitions.append(detail)
		exclude_ids.add(detail.internal_id)
		for usage in detail.defined_terms_used:
			if not usage.definition_internal_id or usage.definition_internal_id in exclude_ids:
				continue
			if usage.definition_internal_id in seen:
				continue
			seen.add(usage.definition_internal_id)
			queue.append(usage.definition_internal_id)
	return definitions


def _collect_unresolved_references(
		details: Sequence[ProvisionDetail],
) -> List[Tuple[str, str, str]]:
	seen: Set[Tuple[str, str, str]] = set()
	ordered: List[Tuple[str, str, str]] = []
	for detail in details:
		source_label = detail.ref_id
		for ref in detail.references_to:
			if ref.target_internal_id:
				continue
			snippet = ref.snippet or ""
			key = (ref.target_ref_id, snippet, source_label)
			if key in seen:
				continue
			seen.add(key)
			ordered.append(key)
	return ordered


def _render_detail_block(detail: ProvisionDetail) -> str:
	heading = f"### {canonical_node_heading(detail)}"
	content = normalize_markdown_content(detail.content_md)
	if content:
		return f"{heading}\n\n{content}"
	return heading


def _render_definition_block(
		detail: ProvisionDetail,
		referenced_details: Sequence[ProvisionDetail],
) -> str:
	block = _render_detail_block(detail)
	if not referenced_details:
		return block
	referenced_blocks = [_render_detail_block(ref_detail) for ref_detail in referenced_details]
	code_body = "\n\n".join(referenced_blocks)
	return f"{block}\n\n```\n{code_body}\n```"


def export_markdown_for_provision(
		db: Session,
		provision_internal_id: str,
		include_descendants: bool,
) -> str:
	"""Assemble Markdown export for a provision and related data."""
	copied_details = _collect_subtree_details(db, provision_internal_id, include_descendants)
	if not copied_details:
		raise ValueError(f"Provision {provision_internal_id} not found")

	copied_details = _unique_by_internal_id(copied_details)
	copied_details.sort(key=lambda d: (d.hierarchy_path_ltree, d.sibling_order or 0))
	copied_ids = {detail.internal_id for detail in copied_details}

	referenced_ids = _gather_referenced_ids(copied_details, copied_ids)
	referenced_details: List[ProvisionDetail] = []
	for ref_id in referenced_ids:
		detail = crud.get_provision_detail(db, ref_id)
		if not detail:
			continue
		referenced_details.append(detail)

	referenced_details = _unique_by_internal_id(referenced_details)
	referenced_details.sort(key=lambda d: (d.hierarchy_path_ltree, d.sibling_order or 0))
	all_seed_details: List[ProvisionDetail] = list(copied_details) + list(referenced_details)
	all_seen_ids: Set[str] = set(copied_ids)
	all_seen_ids.update(detail.internal_id for detail in referenced_details)

	definition_details = _collect_definitions(db, all_seed_details, all_seen_ids)
	definition_details = _unique_by_internal_id(definition_details)
	definition_details.sort(key=lambda d: (d.hierarchy_path_ltree, d.sibling_order or 0))
	definition_ids = {detail.internal_id for detail in definition_details}
	all_seen_ids.update(definition_ids)
	definition_reference_map: Dict[str, List[ProvisionDetail]] = {}
	for definition in definition_details:
		referenced_ids_for_definition = _gather_referenced_ids([definition], all_seen_ids)
		if not referenced_ids_for_definition:
			continue
		referenced_details_for_definition: List[ProvisionDetail] = []
		for ref_id in referenced_ids_for_definition:
			detail = crud.get_provision_detail(db, ref_id)
			if not detail:
				continue
			referenced_details_for_definition.append(detail)
			all_seen_ids.add(detail.internal_id)
		referenced_details_for_definition = _unique_by_internal_id(
			referenced_details_for_definition
		)
		if referenced_details_for_definition:
			definition_reference_map[definition.internal_id] = referenced_details_for_definition

	unresolved_refs = _collect_unresolved_references(
		list(copied_details) + list(referenced_details) + list(definition_details)
	)

	sections: List[str] = []
	if copied_details:
		sections.append("## Copied nodes")
		sections.extend(_render_detail_block(detail) for detail in copied_details)

	if referenced_details:
		sections.append("## Referenced nodes")
		sections.extend(_render_detail_block(detail) for detail in referenced_details)

	if definition_details:
		sections.append("## Definitions used")
		sections.extend(
			_render_definition_block(
					detail,
					definition_reference_map.get(detail.internal_id, []),
			)
			for detail in definition_details
		)

	if unresolved_refs:
		sections.append("## Unresolved external references")
		for target_ref_id, snippet, source_ref_id in unresolved_refs:
			snippet_part = f" — {snippet}" if snippet else ""
			sections.append(f"- {target_ref_id} (from {source_ref_id}){snippet_part}")

	return "\n\n".join(sections).strip()

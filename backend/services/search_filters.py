from __future__ import annotations

from typing import Set

from backend.act_metadata import ActMetadata, get_act_metadata, get_default_act_id


def _ref_to_internal(ref_id: str) -> str:
	return ref_id.replace(":", "_").replace("/", "_")


def _exclusions_for_act(act_id: str | None) -> tuple[Set[str], Set[str]]:
	act_meta: ActMetadata | None = get_act_metadata(act_id or get_default_act_id())
	if not act_meta:
		return set(), set()
	ref_ids = set(act_meta.exclusions.ref_ids)
	internal_ids = {_ref_to_internal(ref_id) for ref_id in ref_ids}
	return ref_ids, internal_ids


def is_excluded_provision(
	*,
	act_id: str | None = None,
	provision_id: str | None = None,
	ref_id: str | None = None,
) -> bool:
	ref_exclusions, internal_exclusions = _exclusions_for_act(act_id)
	if ref_id and ref_id in ref_exclusions:
		return True
	if provision_id and provision_id in internal_exclusions:
		return True
	return False

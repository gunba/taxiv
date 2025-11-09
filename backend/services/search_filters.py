from __future__ import annotations

from typing import Set

# Centralized Act + exclusion helpers so backend and ingestion share rules.
ACT_ID = "ITAA1997"

# Exclude definition section as it is useless (definitions are already extracted and associated with entries.)
EXCLUDED_REF_IDS: Set[str] = {
	f"{ACT_ID}:Section:995-1",
}


def _ref_to_internal(ref_id: str) -> str:
	return ref_id.replace(":", "_").replace("/", "_")


EXCLUDED_INTERNAL_IDS: Set[str] = {_ref_to_internal(ref_id) for ref_id in EXCLUDED_REF_IDS}


def is_excluded_provision(*, provision_id: str | None = None, ref_id: str | None = None) -> bool:
	if ref_id and ref_id in EXCLUDED_REF_IDS:
		return True
	if provision_id and provision_id in EXCLUDED_INTERNAL_IDS:
		return True
	return False

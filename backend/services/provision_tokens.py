from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Set

from backend.act_metadata import get_act_metadata, get_default_act_id, list_acts


SECTION_PREFIX_RE = re.compile(
    r"^(?:s|sec|section)\.?\s*([0-9]+[0-9A-Za-z]*(?:[.\-][0-9A-Za-z]+)*)",
    re.IGNORECASE,
)
SECTION_WITH_GAP_RE = re.compile(r"^([0-9]+[0-9A-Za-z]*)\s+([0-9A-Za-z]+)")
BARE_SECTION_RE = re.compile(r"^([0-9]+[0-9A-Za-z]*(?:[.\-][0-9A-Za-z]+)*)")
ACT_PREFIX_RE = re.compile(r"^(?P<act>[A-Z][A-Z0-9]{2,}):\s*(?P<body>.+)$")


@dataclass(frozen=True)
class ParsedProvisionToken:
    act: str
    section: str
    terms: List[str]


def _allowed_act_ids() -> Set[str]:
	return {act.id for act in list_acts()}


def _normalize_section(raw: str) -> Optional[str]:
    value = raw.strip()
    if not value:
        return None
    value = value.replace("\u2013", "-")
    value = value.replace("\u2014", "-")
    value = value.replace(".", "-")
    value = value.replace(" ", "-")
    value = re.sub(r"-+", "-", value)
    value = value.strip("-")
    if not value:
        return None
    return value.upper()


def parse_flexible_token(
	text: str,
	*,
	default_act: Optional[str] = None,
) -> Optional[ParsedProvisionToken]:
    if not text:
        return None
    original = text.strip()
    if not original:
        return None
    working_text = original
    resolved_act = default_act or get_default_act_id()
    match = ACT_PREFIX_RE.match(original)
    if match:
        candidate_act = match.group("act")
        remaining = match.group("body")
        allowed = _allowed_act_ids()
        if candidate_act in allowed:
            resolved_act = candidate_act
            working_text = remaining.strip()
    match = SECTION_PREFIX_RE.match(working_text)
    section_part = ""
    rest = working_text
    if match:
        section_part = match.group(1) or ""
        rest = working_text[match.end():].strip()
    else:
        gap = SECTION_WITH_GAP_RE.match(working_text)
        if not gap:
            bare = BARE_SECTION_RE.match(working_text)
            if not bare:
                return None
            section_part = bare.group(1)
            rest = working_text[bare.end():].strip()
        else:
            section_part = f"{gap.group(1)}-{gap.group(2)}"
            rest = working_text[gap.end():].strip()
    normalized = _normalize_section(section_part)
    if not normalized:
        return None
    term_parts = [segment.strip() for segment in re.split(r"[;,]", rest) if segment.strip()]
    # Final validation: ensure the resolved act still exists
    act_meta = get_act_metadata(resolved_act)
    if not act_meta:
        resolved_act = get_default_act_id()
    return ParsedProvisionToken(act=resolved_act, section=normalized, terms=term_parts)

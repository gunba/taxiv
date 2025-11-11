from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional


SECTION_PREFIX_RE = re.compile(
    r"^(?:s|sec|section)\.?\s*([0-9]+[0-9A-Za-z]*(?:[.\-][0-9A-Za-z]+)*)",
    re.IGNORECASE,
)
SECTION_WITH_GAP_RE = re.compile(r"^([0-9]+[0-9A-Za-z]*)\s+([0-9A-Za-z]+)")
BARE_SECTION_RE = re.compile(r"^([0-9]+[0-9A-Za-z]*(?:[.\-][0-9A-Za-z]+)*)")


@dataclass(frozen=True)
class ParsedProvisionToken:
    act: str
    section: str
    terms: List[str]


ALLOWED_ACT = "ITAA1997"


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


def parse_flexible_token(text: str) -> Optional[ParsedProvisionToken]:
    if not text:
        return None
    original = text.strip()
    if not original:
        return None
    match = SECTION_PREFIX_RE.match(original)
    section_part = ""
    rest = original
    if match:
        section_part = match.group(1) or ""
        rest = original[match.end():].strip()
    else:
        gap = SECTION_WITH_GAP_RE.match(original)
        if not gap:
            bare = BARE_SECTION_RE.match(original)
            if not bare:
                return None
            section_part = bare.group(1)
            rest = original[bare.end():].strip()
        else:
            section_part = f"{gap.group(1)}-{gap.group(2)}"
            rest = original[gap.end():].strip()
    normalized = _normalize_section(section_part)
    if not normalized:
        return None
    term_parts = [segment.strip() for segment in re.split(r"[;,]", rest) if segment.strip()]
    return ParsedProvisionToken(act=ALLOWED_ACT, section=normalized, terms=term_parts)

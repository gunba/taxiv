from __future__ import annotations

import re
import math
from collections import defaultdict
from typing import Dict, List, Tuple

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from backend.models.legislation import (
    BaselinePagerank,
    Provision,
)
from backend.services.relatedness_engine import get_or_compute_and_cache

# -----------------------
# Query parsing patterns
# -----------------------

# section-like identifiers: 10-5, 83A-10, 94J, 159GK, 118-510, etc.
RE_SECTION = re.compile(r"\b(?:s|sect|section)\s*([0-9]+[A-Z]*-[0-9A-Z]+|[0-9]+[A-Z]*)\b", re.IGNORECASE)
RE_DIV = re.compile(r"\bdiv(?:ision)?\s*([0-9]+[A-Z]?)\b", re.IGNORECASE)
RE_SUBDIV = re.compile(r"\bsubdiv(?:ision)?\s*([0-9]+-[A-Z])\b", re.IGNORECASE)
RE_PART = re.compile(r"\bpart\s*([IVXLCDM]+|[0-9A-Z\-]+)\b", re.IGNORECASE)

# explicit ref-id like ITAA1997:Section:417-140 or TAA1953:Schedule:1:Section:12-5
RE_REFID = re.compile(r"\b([A-Z]{3,}[0-9]{4}:(?:Act|Section|Division|Subdivision|Part|Schedule(?::[A-Z0-9]+)?):[^\s,;]+)\b")

ACT_ID = "ITAA1997"  # default act for bare IDs

# URS mapping controls
LOGISTIC_A = 0.75
LOGISTIC_B = 0.0
MIN_SCORE = 5
MAX_SCORE = 99

SNIPPET_LIMIT = 120


def _normalize_text(text: str) -> str:
    # minimal, general normalization
    t = text.replace("—", "-").replace("–", "-")
    t = t.replace("’", "'").replace("“", '"').replace("”", '"')
    t = t.replace("&", " and ")
    t = re.sub(r"\s+", " ", t).strip()
    return t


def build_snippet(content_md: str | None, limit: int = SNIPPET_LIMIT) -> str:
    if not content_md:
        return "No content"
    plain = re.sub(r"[#*_`>\[\]\"]", "", content_md)
    plain = re.sub(r"\s+", " ", plain).strip()
    if not plain:
        return "No content"
    if len(plain) <= limit:
        return plain
    return plain[:limit].rstrip(",.;: ") + "…"


def _lookup_ref_by_kind(db: Session, kind: str, ident: str) -> str | None:
    ref_id = f"{ACT_ID}:{kind}:{ident.upper()}"
    row = db.query(Provision.internal_id).filter(
        Provision.act_id == ACT_ID,
        Provision.ref_id == ref_id,
    ).first()
    return row[0] if row else None


def _lookup_any_kind(db: Session, ident: str) -> str | None:
    # Try the common structural kinds
    for kind in ("Section", "Subdivision", "Division", "Part"):
        pid = _lookup_ref_by_kind(db, kind, ident)
        if pid:
            return pid
    return None


def _lookup_ref_id_exact(db: Session, ref_id: str) -> str | None:
    row = db.query(Provision.internal_id).filter(
        Provision.ref_id == ref_id
    ).first()
    return row[0] if row else None


def parse_query(db: Session, query: str) -> dict:
    text = _normalize_text(query)
    provision_ids: List[str] = []
    definition_ids: List[str] = []

    # 1) explicit ref-ids
    for m in RE_REFID.finditer(text):
        candidate = m.group(1)
        pid = _lookup_ref_id_exact(db, candidate)
        if pid:
            provision_ids.append(pid)
            text = text.replace(candidate, " ")

    # 2) bare structural identifiers
    for match in RE_SECTION.finditer(text):
        pid = _lookup_any_kind(db, match.group(1))
        if pid:
            provision_ids.append(pid)
            text = text.replace(match.group(0), " ")

    for match in RE_SUBDIV.finditer(text):
        pid = _lookup_ref_by_kind(db, "Subdivision", match.group(1))
        if pid:
            provision_ids.append(pid)
            text = text.replace(match.group(0), " ")

    for match in RE_DIV.finditer(text):
        pid = _lookup_ref_by_kind(db, "Division", match.group(1))
        if pid:
            provision_ids.append(pid)
            text = text.replace(match.group(0), " ")

    for match in RE_PART.finditer(text):
        pid = _lookup_ref_by_kind(db, "Part", match.group(1))
        if pid:
            provision_ids.append(pid)
            text = text.replace(match.group(0), " ")

    # 3) definitions by exact or loose match
    # tokens from remaining text; short tokens are ignored
    tokens = [tok for tok in re.split(r"[\s,;/+]+", text) if len(tok) >= 3]
    found_defs: set[str] = set()

    # exact-insensitive title matches
    for tok in tokens:
        row = db.query(Provision.internal_id).filter(
            Provision.act_id == ACT_ID,
            Provision.type == "Definition",
            func.lower(Provision.title) == func.lower(tok),
        ).first()
        if row:
            found_defs.add(row[0])

    # loose ILIKE on title for longer tokens, helpful for hyphens and ampersands
    for tok in tokens:
        pattern = f"%{tok}%"
        rows = db.query(Provision.internal_id).filter(
            Provision.act_id == ACT_ID,
            Provision.type == "Definition",
            or_(
                Provision.title.ilike(pattern),
                func.replace(Provision.title, '&', 'and').ilike(
                    func.replace(pattern, '&', 'and')
                ),
            ),
        ).limit(10).all()
        for r in rows:
            found_defs.add(r[0])

    definition_ids = list(found_defs)

    # Remove recognized objects from keywords for FTS
    keywords = re.sub(r"\s+", " ", text).strip()

    return {
        "provisions": list(dict.fromkeys(provision_ids)),
        "definitions": definition_ids,
        "keywords": keywords,
    }


def _fts_candidates(db: Session, keywords: str, limit: int = 10) -> List[str]:
    """
    Return up to `limit` provision internal_ids by free text.
    Try websearch_to_tsquery first; fall back to plainto_tsquery; then ILIKE on title.
    """
    if not keywords:
        return []

    concat_text = func.concat(Provision.title, ' ', func.coalesce(Provision.content_md, ''))

    # Pass 1: websearch_to_tsquery (handles quotes, punctuation, AND/OR)
    try:
        ts_query = func.websearch_to_tsquery('english', keywords)
        rows = db.query(Provision.internal_id).filter(
            Provision.act_id == ACT_ID,
            func.to_tsvector('english', concat_text).op('@@')(ts_query),
        ).limit(limit).all()
        ids = [row[0] for row in rows]
        if ids:
            return ids
    except Exception:
        pass

    # Pass 2: plainto_tsquery fallback
    try:
        ts_query = func.plainto_tsquery('english', keywords)
        rows = db.query(Provision.internal_id).filter(
            Provision.act_id == ACT_ID,
            func.to_tsvector('english', concat_text).op('@@')(ts_query),
        ).limit(limit).all()
        ids = [row[0] for row in rows]
        if ids:
            return ids
    except Exception:
        pass

    # Pass 3: ILIKE fallback on title (broad)
    pattern = f"%{keywords}%"
    rows = db.query(Provision.internal_id).filter(
        Provision.act_id == ACT_ID,
        Provision.title.ilike(pattern),
    ).limit(limit).all()
    return [row[0] for row in rows]


def urs_from_components(*, log2_lift: float, mass: float, top_mass: float, captured_mass: float) -> int:
    # logistic mapping for mutual information-like lift
    base = 100.0 / (1.0 + math.exp(-LOGISTIC_A * (log2_lift - LOGISTIC_B)))
    # confidence from node mass relative to top candidate
    rel = mass / max(top_mass, 1e-12)
    conf = math.sqrt(max(0.0, min(1.0, rel)))
    # global coverage factor to down-weight fragile seeds
    coverage = max(0.5, min(1.0, math.sqrt(max(0.0, min(1.0, captured_mass)))))
    score = base * conf * coverage
    score = max(MIN_SCORE, min(MAX_SCORE, score))
    return int(round(score))


def unified_search(db: Session, query: str, k: int = 25) -> dict:
    interpretation = parse_query(db, query)
    seed_weights: Dict[str, float] = {}

    for pid in interpretation["provisions"]:
        seed_weights[pid] = seed_weights.get(pid, 0.0) + 1.0

    for did in interpretation["definitions"]:
        seed_weights[did] = seed_weights.get(did, 0.0) + 1.2

    # Free-text pseudo seeds if none detected
    if not seed_weights and interpretation["keywords"]:
        pseudo_ids = _fts_candidates(db, interpretation["keywords"], limit=10)
        for pid in pseudo_ids:
            seed_weights[pid] = seed_weights.get(pid, 0.0) + 0.3

    # Normalize seed weights
    total_weight = sum(seed_weights.values()) or 1.0
    for key in list(seed_weights.keys()):
        seed_weights[key] = seed_weights[key] / total_weight

    # Gather relatedness scores via fingerprints
    related_scores = defaultdict(float)
    captured_mass = 0.0
    for seed_id, weight in seed_weights.items():
        neighbors, captured = get_or_compute_and_cache(db, seed_id)
        captured_mass += weight * captured
        for neighbor_id, mass in neighbors:
            related_scores[neighbor_id] += weight * mass

    # Ensure seeds appear in the candidate pool with a healthy mass
    if seed_weights:
        max_mass = max(related_scores.values()) if related_scores else 0.0
        seed_boost = max(max_mass * 1.25, 0.1)
        for seed_id, weight in seed_weights.items():
            related_scores[seed_id] = max(related_scores.get(seed_id, 0.0), seed_boost * weight)

    if not related_scores:
        # No graph signal at all; return seeds (if any) as results with neutral score.
        results: List[dict] = []
        for seed_id in seed_weights.keys():
            row = db.query(Provision.internal_id, Provision.ref_id, Provision.title, Provision.type, Provision.content_md)\
                    .filter(Provision.internal_id == seed_id).first()
            if not row:
                continue
            results.append({
                "id": row.internal_id,
                "ref_id": row.ref_id,
                "title": row.title,
                "type": row.type,
                "score_urs": 75,
                "content_snippet": build_snippet(getattr(row, "content_md", None)),
            })
        return {
            "query_interpretation": {
                **interpretation,
                "pseudo_seeds": list(seed_weights.keys()) if not interpretation["provisions"] and not interpretation["definitions"] else [],
            },
            "results": results,
            "debug": {
                "mass_captured": 0.0,
                "num_seeds": len(seed_weights),
                "note": "Graph produced no neighbors; returning seeds only.",
            },
        }

    # Normalize relatedness masses
    total_mass = sum(related_scores.values()) or 1.0
    normalized = {prov: mass / total_mass for prov, mass in related_scores.items()}

    # Baseline
    candidate_ids = list(normalized.keys())
    pi_rows = db.query(BaselinePagerank.provision_id, BaselinePagerank.pi).filter(
        BaselinePagerank.provision_id.in_(candidate_ids)
    ).all()
    baseline = {pid: float(value) for pid, value in pi_rows}
    for candidate in candidate_ids:
        baseline.setdefault(candidate, 1e-12)

    # Metadata for output
    provisions = db.query(
        Provision.internal_id,
        Provision.ref_id,
        Provision.title,
        Provision.type,
        Provision.content_md,
    ).filter(Provision.internal_id.in_(candidate_ids)).all()
    meta = {row.internal_id: row for row in provisions}

    # Scoring
    top_mass = max(normalized.values()) if normalized else 1.0
    scored: List[Tuple[str, int]] = []
    for prov_id in candidate_ids:
        lift = normalized[prov_id] / max(baseline.get(prov_id, 1e-12), 1e-12)
        log2_lift = math.log2(lift)
        score = urs_from_components(
            log2_lift=log2_lift,
            mass=normalized[prov_id],
            top_mass=top_mass,
            captured_mass=captured_mass,
        )
        scored.append((prov_id, score))

    scored.sort(key=lambda item: item[1], reverse=True)
    top_results = scored[:k]

    results: List[dict] = []
    for prov_id, score in top_results:
        row = meta.get(prov_id)
        if not row:
            continue
        results.append({
            "id": row.internal_id,
            "ref_id": row.ref_id,
            "title": row.title,
            "type": row.type,
            "score_urs": score,
            "content_snippet": build_snippet(getattr(row, "content_md", None)),
        })

    return {
        "query_interpretation": {
            **interpretation,
            "pseudo_seeds": [] if interpretation["provisions"] or interpretation["definitions"] else (
                list(seed_weights.keys()) if seed_weights else []
            ),
        },
        "results": results,
        "debug": {
            "mass_captured": round(float(captured_mass), 4),
            "num_seeds": len(seed_weights),
        },
    }

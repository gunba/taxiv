from __future__ import annotations

import re
from collections import defaultdict
from typing import Dict, List, Tuple

import math
from cachetools import TTLCache
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from backend.models.legislation import (
	BaselinePagerank,
	Provision,
)
from backend.services.relatedness_engine import (
	compute_fingerprint_multi,
	get_cached_fingerprints,
	get_graph_version,
	get_or_compute_and_cache,
)
from backend.services.search_filters import (
	ACT_ID,
	EXCLUDED_INTERNAL_IDS,
	is_excluded_provision,
)

# -------------------------------------------------------------------
# Robust query handling
# -------------------------------------------------------------------

RE_SECTION = re.compile(r"\b(?:s|sect|section)\s*([0-9]+[A-Z]*-[0-9A-Z]+|[0-9]+[A-Z]*)\b", re.IGNORECASE)
RE_DIV = re.compile(r"\bdiv(?:ision)?\s*([0-9]+[A-Z]?)\b", re.IGNORECASE)
RE_SUBDIV = re.compile(r"\bsubdiv(?:ision)?\s*([0-9]+-[A-Z])\b", re.IGNORECASE)
RE_PART = re.compile(r"\bpart\s*([IVXLCDM]+|[0-9A-Z\-]+)\b", re.IGNORECASE)
RE_REFID = re.compile(r"\b([A-Z][A-Z0-9]{1,10}):\s*(Act|Schedule(?::\s*\d+)?|Part|Division|Subdivision|Section|Definition)\s*:\s*([A-Za-z0-9_\-:.]+)\b", re.IGNORECASE)
RE_LOCALID = re.compile(r"\b([0-9]+[A-Z]*-[0-9A-Z]+)\b", re.IGNORECASE)

SNIPPET_LIMIT = 120

# Lexical candidate size
LEX_TOP = 200
SEED_TOP = 12
SEED_MULTI_THRESHOLD = 3
SEARCH_CACHE_TTL_SECONDS = 600
_SEARCH_CACHE = TTLCache(maxsize=2000, ttl=SEARCH_CACHE_TTL_SECONDS)

# Blend weights
W_GRAPH = 0.65
W_LEX = 0.35


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


def _normalize_query(text: str) -> str:
	# General, act-agnostic normalization. Avoid custom synonym lists.
	# - unify ampersand to "and"
	# - collapse whitespace
	# - keep hyphens (needed for section ids)
	normalized = text.replace("&", " and ")
	normalized = re.sub(r"[\/]+", " ", normalized)
	normalized = re.sub(r"\s+", " ", normalized).strip()
	return normalized


def _lookup_ref(db: Session, kind: str, ident: str) -> str | None:
	ref_id = f"{ACT_ID}:{kind}:{ident.upper()}"
	row = db.query(Provision.internal_id).filter(
		Provision.act_id == ACT_ID,
		Provision.ref_id == ref_id,
	).first()
	return row[0] if row else None


def _lookup_by_ref_id_literal(db: Session, ref_id_literal: str) -> str | None:
	ref_id = ref_id_literal.strip()
	row = db.query(Provision.internal_id).filter(
		Provision.act_id == ACT_ID,
		Provision.ref_id == ref_id,
	).first()
	return row[0] if row else None


def _lookup_by_local_id(db: Session, ident: str) -> str | None:
	row = db.query(Provision.internal_id).filter(
		Provision.act_id == ACT_ID,
		func.upper(Provision.local_id) == ident.upper(),
	).first()
	return row[0] if row else None


def parse_query(db: Session, query: str) -> dict:
	text_q = query.strip()
	norm = _normalize_query(text_q)

	provision_ids: List[str] = []
	definition_ids: List[str] = []
	keywords = norm

	# Explicit full ref_id
	for match in RE_REFID.finditer(text_q):
		ref_id_lit = f"{match.group(1).upper()}:{match.group(2)}:{match.group(3)}"
		pid = _lookup_by_ref_id_literal(db, ref_id_lit)
		if pid:
			provision_ids.append(pid)
			keywords = keywords.replace(match.group(0), " ")

	# Section/Subdiv/Div/Part shorthands
	for match in RE_SECTION.finditer(text_q):
		pid = _lookup_ref(db, "Section", match.group(1))
		if pid:
			provision_ids.append(pid)
			keywords = keywords.replace(match.group(0), " ")

	for match in RE_SUBDIV.finditer(text_q):
		pid = _lookup_ref(db, "Subdivision", match.group(1))
		if pid:
			provision_ids.append(pid)
			keywords = keywords.replace(match.group(0), " ")

	for match in RE_DIV.finditer(text_q):
		pid = _lookup_ref(db, "Division", match.group(1))
		if pid:
			provision_ids.append(pid)
			keywords = keywords.replace(match.group(0), " ")

	for match in RE_PART.finditer(text_q):
		pid = _lookup_ref(db, "Part", match.group(1))
		if pid:
			provision_ids.append(pid)
			keywords = keywords.replace(match.group(0), " ")

	# Bare local ids like 417-140
	for match in RE_LOCALID.finditer(text_q):
		pid = _lookup_by_local_id(db, match.group(1))
		if pid:
			provision_ids.append(pid)
			keywords = keywords.replace(match.group(0), " ")

	# Definitions: exact title match if present
	raw_terms = [token.strip() for token in re.split(r"[+,;&]", keywords) if token.strip()]
	term_ids = set()
	for token in raw_terms:
		row = db.query(Provision.internal_id).filter(
			Provision.act_id == ACT_ID,
			Provision.type == "Definition",
			func.lower(Provision.title) == func.lower(token),
		).first()
		if row:
			term_ids.add(row[0])
			keywords = keywords.replace(token, " ")

	definition_ids = list(term_ids)
	keywords = re.sub(r"\s+", " ", keywords).strip()

	return {
		"provisions": list(dict.fromkeys(provision_ids)),
		"definitions": definition_ids,
		"keywords": keywords,
	}


def _lexical_candidates(db: Session, original: str, normalized: str, limit: int = LEX_TOP) -> Dict[str, float]:
	"""
	Hybrid lexical retrieval using:
	- websearch_to_tsquery over english + simple configurations
	- pg_trgm similarity on title and content
	Returns internal_id -> score (non-negative)
	"""
	# Build tsquerys once
	params = {
		"act": ACT_ID,
		"q_norm": normalized,
		"q_raw": original,
		"limit": limit,
	}
	# GREATEST across english/simple ranks and trigram similarity against both raw and normalized
	sql = text(
		"""
		WITH base AS (
		  SELECT
		    p.internal_id,
		    p.type,
		    coalesce(p.title, '') AS title,
		    coalesce(p.content_md, '') AS content_md,
		    to_tsvector('english', coalesce(p.title,'') || ' ' || coalesce(p.content_md,'')) AS tsv_en,
		    to_tsvector('simple',  coalesce(p.title,'') || ' ' || coalesce(p.content_md,'')) AS tsv_simple
		  FROM provisions p
		  WHERE p.act_id = :act
		),
		q AS (
		  SELECT
		    websearch_to_tsquery('english', :q_norm) AS q_en,
		    websearch_to_tsquery('simple', :q_norm) AS q_simple
		)
		SELECT
		  b.internal_id,
		  b.type,
		  GREATEST(ts_rank_cd(b.tsv_en, q.q_en), ts_rank_cd(b.tsv_simple, q.q_simple)) AS ts_score,
		  GREATEST(
		    similarity(lower(b.title),      lower(:q_norm)),
		    similarity(lower(b.content_md), lower(:q_norm)),
		    similarity(lower(b.title),      lower(:q_raw)),
		    similarity(lower(b.content_md), lower(:q_raw))
		  ) AS tri_score
		FROM base b, q
		WHERE (b.tsv_en @@ q.q_en) OR (b.tsv_simple @@ q.q_simple)
		ORDER BY (
		     GREATEST(ts_rank_cd(b.tsv_en, q.q_en), ts_rank_cd(b.tsv_simple, q.q_simple)) * 0.7
		   + GREATEST(
		       similarity(lower(b.title),      lower(:q_norm)),
		       similarity(lower(b.content_md), lower(:q_norm)),
		       similarity(lower(b.title),      lower(:q_raw)),
		       similarity(lower(b.content_md), lower(:q_raw))
		     ) * 0.3
		) DESC
		LIMIT :limit
		"""
	)
	rows = db.execute(sql, params).fetchall()
	results: Dict[str, float] = {}
	for iid, typ, ts, tri in rows:
		if iid is None or is_excluded_provision(provision_id=iid):
			continue
		score = max(0.0, float(ts or 0.0) * 0.7 + float(tri or 0.0) * 0.3)
		# definitions are candidates but slightly downweighted later at ranking time
		results[iid] = score
	return results


def _minmax_scale(values: List[float]) -> Dict[int, float]:
	if not values:
		return {}
	vmin = min(values)
	vmax = max(values)
	if vmax <= vmin:
		# all equal
		return {i: 50.0 for i in range(len(values))}
	out = {}
	for i, v in enumerate(values):
		out[i] = 100.0 * (v - vmin) / (vmax - vmin)
	return out


def _score_to_urs(scores: List[float]) -> List[int]:
	scaled = _minmax_scale(scores)
	return [int(round(scaled.get(i, 0.0))) for i in range(len(scores))]


def unified_search(db: Session, query: str, k: int = 25) -> dict:
	orig = query or ""
	norm = _normalize_query(orig)
	interpretation = parse_query(db, orig)
	graph_version = get_graph_version(db)
	cache_key = (orig.strip(), k, graph_version)
	cached = _SEARCH_CACHE.get(cache_key)
	if cached:
		return cached

	# Exact seeds
	seed_weights: Dict[str, float] = {}
	for pid in interpretation["provisions"]:
		if is_excluded_provision(provision_id=pid):
			continue
		seed_weights[pid] = seed_weights.get(pid, 0.0) + 1.0
	for did in interpretation["definitions"]:
		if is_excluded_provision(provision_id=did):
			continue
		seed_weights[did] = seed_weights.get(did, 0.0) + 1.0

	# Lexical candidates
	lex_candidates = _lexical_candidates(db, original=orig, normalized=norm, limit=LEX_TOP)
	lex_candidates = {
		iid: score for iid, score in lex_candidates.items() if not is_excluded_provision(provision_id=iid)
	}

	# If no explicit seeds, derive from lexical
	if not seed_weights and lex_candidates:
		top_seed_candidates = list(lex_candidates.items())[:SEED_TOP]
		vals = [score for _, score in top_seed_candidates]
		m_scaled = _minmax_scale(vals)  # 0..100
		total = sum(m_scaled.values()) or 1.0
		for idx, (iid, _score) in enumerate(top_seed_candidates):
			weight = m_scaled.get(idx, 0.0) / total
			if weight > 0:
				seed_weights[iid] = seed_weights.get(iid, 0.0) + weight

	# If still no seeds, return lexical top as results (fallback)
	if not seed_weights and not lex_candidates:
		payload = {
			"query_interpretation": interpretation,
			"results": [],
			"debug": {
				"mass_captured": 0.0,
				"num_seeds": 0,
				"note": "No lexical or exact seeds",
			},
		}
		_SEARCH_CACHE[cache_key] = payload
		return payload

	# Relatedness aggregation
	related_scores = defaultdict(float)
	captured_mass = 0.0
	cached_map, missing_seeds = get_cached_fingerprints(db, set(seed_weights.keys()), graph_version)
	for seed_id, (neighbors, captured) in cached_map.items():
		weight = seed_weights.get(seed_id, 0.0)
		if weight <= 0:
			continue
		captured_mass += weight * captured
		for neighbor_id, mass in neighbors:
			if is_excluded_provision(provision_id=neighbor_id):
				continue
			related_scores[neighbor_id] += weight * mass
		related_scores[seed_id] += weight * 0.05

	unresolved_seeds = [seed for seed in seed_weights.keys() if seed in missing_seeds]
	if unresolved_seeds:
		if len(unresolved_seeds) > SEED_MULTI_THRESHOLD:
			missing_weights = {seed: seed_weights[seed] for seed in unresolved_seeds}
			multi_neighbors, multi_captured = compute_fingerprint_multi(db, missing_weights)
			total_missing_weight = sum(missing_weights.values()) or 1.0
			captured_mass += total_missing_weight * multi_captured
			for neighbor_id, mass in multi_neighbors:
				if is_excluded_provision(provision_id=neighbor_id):
					continue
				related_scores[neighbor_id] += total_missing_weight * mass
			for seed_id in unresolved_seeds:
				weight = seed_weights.get(seed_id, 0.0)
				if weight > 0:
					related_scores[seed_id] += weight * 0.05
		else:
			for seed_id in unresolved_seeds:
				neighbors, captured = get_or_compute_and_cache(db, seed_id)
				weight = seed_weights.get(seed_id, 0.0)
				if weight <= 0:
					continue
				captured_mass += weight * captured
				for neighbor_id, mass in neighbors:
					if is_excluded_provision(provision_id=neighbor_id):
						continue
					related_scores[neighbor_id] += weight * mass
				related_scores[seed_id] += weight * 0.05

	if not related_scores:
		# fall back to lexical if graph has no edges around seeds
		if lex_candidates:
			cands = list(lex_candidates.items())[:k]
			meta_rows = db.query(
				Provision.internal_id, Provision.ref_id, Provision.title, Provision.type, Provision.content_md
			).filter(Provision.internal_id.in_([c[0] for c in cands])).all()
			meta = {row.internal_id: row for row in meta_rows}
			results = []
			for iid, _sc in cands:
				row = meta.get(iid)
				if not row:
					continue
				if is_excluded_provision(provision_id=row.internal_id):
					continue
				results.append({
					"id": row.internal_id,
					"ref_id": row.ref_id,
					"title": row.title,
					"type": row.type,
					"score_urs": 100 if not results else 80,  # simple fallback
					"content_snippet": build_snippet(getattr(row, "content_md", None)),
				})
			payload = {
				"query_interpretation": interpretation,
				"results": results,
				"debug": {
					"mass_captured": 0.0,
					"num_seeds": len(seed_weights),
					"note": "Fallback lexical only",
				},
			}
			_SEARCH_CACHE[cache_key] = payload
			return payload

	# Normalize relatedness masses
	total_mass = sum(related_scores.values()) or 1.0
	graph_norm = {prov: mass / total_mass for prov, mass in related_scores.items()}

	# Baseline
	candidate_ids = list(graph_norm.keys())
	pi_rows = db.query(BaselinePagerank.provision_id, BaselinePagerank.pi).filter(
		BaselinePagerank.provision_id.in_(candidate_ids)
	).all()
	baseline = {pid: float(value) for pid, value in pi_rows}
	for candidate in candidate_ids:
		baseline.setdefault(candidate, 1e-12)

	# Fetch meta
	provisions = db.query(
		Provision.internal_id,
		Provision.ref_id,
		Provision.title,
		Provision.type,
		Provision.content_md,
	).filter(Provision.internal_id.in_(candidate_ids)).all()
	meta = {row.internal_id: row for row in provisions}

	# Compose final scores with lexical boost and definition penalty
	final_scores: List[Tuple[str, float, float, float]] = []  # (iid, score, graph_part, lex_part)
	# Prepare lexical norm over same candidate set
	lex_seen = []
	for iid in candidate_ids:
		lex_seen.append(lex_candidates.get(iid, 0.0))
	lex_norm_map = _minmax_scale(lex_seen)

	for idx, prov_id in enumerate(candidate_ids):
		row = meta.get(prov_id)
		if not row:
			continue
		graph_mass = graph_norm.get(prov_id, 0.0)
		lift = graph_mass / max(baseline.get(prov_id, 1e-12), 1e-12)
		graph_score = math.log2(max(lift, 1e-12))  # can be negative for below-baseline
		# Normalize graph scores over this result set
		# We'll collect and scale after loop; store components
		lex_component = lex_norm_map.get(idx, 0.0) / 100.0  # 0..1
		final_scores.append((prov_id, graph_score, graph_score, lex_component))

	# Scale graph scores to 0..100
	graph_vals = [fs[1] for fs in final_scores]
	graph_scaled_map = _minmax_scale(graph_vals)

	composite: List[Tuple[str, float]] = []
	for i, (prov_id, _raw, graph_raw, lex_comp) in enumerate(final_scores):
		graph_part = (graph_scaled_map.get(i, 0.0)) / 100.0  # 0..1
		score = W_GRAPH * graph_part + W_LEX * (lex_comp)
		typ = meta[prov_id].type or ""
		composite.append((prov_id, score))

	# Rank and map to URS 0..100 relative to set
	composite.sort(key=lambda x: x[1], reverse=True)
	scores_only = [s for _, s in composite]
	urs_vals = _score_to_urs(scores_only)

	top_results = []
	for (prov_id, _), urs in zip(composite[:k], urs_vals[:k]):
		row = meta.get(prov_id)
		if not row:
			continue
		top_results.append({
			"id": row.internal_id,
			"ref_id": row.ref_id,
			"title": row.title,
			"type": row.type,
			"score_urs": urs,
			"content_snippet": build_snippet(getattr(row, "content_md", None)),
		})

	payload = {
		"query_interpretation": {
			"provisions": interpretation["provisions"],
			"definitions": interpretation["definitions"],
			"keywords": interpretation["keywords"],
			"pseudo_seeds": [] if (interpretation["provisions"] or interpretation["definitions"]) else list(lex_candidates.keys())[:10],
		},
		"results": top_results,
		"debug": {
			"mass_captured": round(float(captured_mass), 4),
			"num_seeds": len(seed_weights),
		},
	}
	_SEARCH_CACHE[cache_key] = payload
	return payload

from __future__ import annotations

import math
import re
from collections import defaultdict
from typing import Dict, List, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.models.legislation import (
	BaselinePagerank,
	DefinedTermUsage,
	Provision,
	Reference,
	RelatednessFingerprint,
)

RE_SECTION = re.compile(r"\b(?:s|sect|section)\s*([0-9]+[A-Z]*-[0-9A-Z]+|[0-9]+[A-Z]*)\b", re.IGNORECASE)
RE_DIV = re.compile(r"\bdiv(?:ision)?\s*([0-9]+[A-Z]?)\b", re.IGNORECASE)
RE_SUBDIV = re.compile(r"\bsubdiv(?:ision)?\s*([0-9]+-[A-Z])\b", re.IGNORECASE)
RE_PART = re.compile(r"\bpart\s*([IVXLCDM]+|[0-9A-Z\-]+)\b", re.IGNORECASE)

ACT_ID = "ITAA1997"
W_LOG2 = 6.0


def parse_query(db: Session, query: str) -> dict:
	text = query.strip()
	provision_ids: List[str] = []
	definition_ids: List[str] = []
	keywords = text

	def lookup_ref(kind: str, ident: str) -> str | None:
		ref_id = f"{ACT_ID}:{kind}:{ident.upper()}"
		row = db.query(Provision.internal_id).filter(
			Provision.act_id == ACT_ID,
			Provision.ref_id == ref_id,
		).first()
		return row[0] if row else None

	for match in RE_SECTION.finditer(text):
		pid = lookup_ref("Section", match.group(1))
		if pid:
			provision_ids.append(pid)
			keywords = keywords.replace(match.group(0), " ")

	for match in RE_SUBDIV.finditer(text):
		pid = lookup_ref("Subdivision", match.group(1))
		if pid:
			provision_ids.append(pid)
			keywords = keywords.replace(match.group(0), " ")

	for match in RE_DIV.finditer(text):
		pid = lookup_ref("Division", match.group(1))
		if pid:
			provision_ids.append(pid)
			keywords = keywords.replace(match.group(0), " ")

	for match in RE_PART.finditer(text):
		pid = lookup_ref("Part", match.group(1))
		if pid:
			provision_ids.append(pid)
			keywords = keywords.replace(match.group(0), " ")

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
		"provisions": provision_ids,
		"definitions": definition_ids,
		"keywords": keywords,
	}


def load_fingerprint(db: Session, provision_id: str) -> Tuple[List[Tuple[str, float]], float]:
	row = db.query(RelatednessFingerprint).filter(
		RelatednessFingerprint.source_kind == "provision",
		RelatednessFingerprint.source_id == provision_id,
	).first()
	if not row:
		return [], 0.0
	neighbors: List[Tuple[str, float]] = []
	for neighbor in row.neighbors or []:
		prov_id = neighbor.get("prov_id")
		if not prov_id:
			continue
		mass = float(neighbor.get("ppr_mass", 0.0))
		neighbors.append((prov_id, mass))
	return neighbors, float(row.captured_mass_provisions or 0.0)


def urs_from_log2(log2_lift: float) -> int:
	score = ((log2_lift + W_LOG2) / (2.0 * W_LOG2)) * 100.0
	return int(min(max(score, 0.0), 100.0))


def unified_search(db: Session, query: str, k: int = 25, include_explanations: bool = True) -> dict:
	interpretation = parse_query(db, query)
	seed_weights: Dict[str, float] = {}

	for pid in interpretation["provisions"]:
		seed_weights[pid] = seed_weights.get(pid, 0.0) + 1.0

	for did in interpretation["definitions"]:
		seed_weights[did] = seed_weights.get(did, 0.0) + 1.2

	pseudo_seeds: List[str] = []
	if not seed_weights and interpretation["keywords"]:
		ts_query = func.plainto_tsquery('english', interpretation["keywords"])
		concat_text = func.concat(Provision.title, ' ', func.coalesce(Provision.content_md, ''))
		rows = db.query(Provision.internal_id).filter(
			Provision.act_id == ACT_ID,
			func.to_tsvector('english', concat_text).op('@@')(ts_query),
		).limit(10).all()
		pseudo_seeds = [row[0] for row in rows]
		for pid in pseudo_seeds:
			seed_weights[pid] = seed_weights.get(pid, 0.0) + 0.3

	total_weight = sum(seed_weights.values()) or 1.0
	for key in list(seed_weights.keys()):
		seed_weights[key] = seed_weights[key] / total_weight

	related_scores = defaultdict(float)
	captured_mass = 0.0
	for seed_id, weight in seed_weights.items():
		neighbors, captured = load_fingerprint(db, seed_id)
		captured_mass += weight * captured
		for neighbor_id, mass in neighbors:
			related_scores[neighbor_id] += weight * mass

	if not related_scores:
		return {
			"query_interpretation": interpretation,
			"results": [],
			"debug": {
				"mass_captured": 0.0,
				"num_seeds": len(seed_weights),
				"note": "No neighbors for seeds",
			},
		}

	total_mass = sum(related_scores.values()) or 1.0
	normalized = {prov: mass / total_mass for prov, mass in related_scores.items()}

	candidate_ids = list(normalized.keys())
	pi_rows = db.query(BaselinePagerank.provision_id, BaselinePagerank.pi).filter(
		BaselinePagerank.provision_id.in_(candidate_ids)
	).all()
	baseline = {pid: float(value) for pid, value in pi_rows}
	for candidate in candidate_ids:
		baseline.setdefault(candidate, 1e-12)

	provisions = db.query(
		Provision.internal_id,
		Provision.ref_id,
		Provision.title,
		Provision.type,
		Provision.pagerank,
		Provision.in_degree,
		Provision.out_degree,
		Provision.content_md,
	).filter(Provision.internal_id.in_(candidate_ids)).all()
	meta = {row.internal_id: row for row in provisions}

	scored: List[Tuple[str, int]] = []
	for prov_id in candidate_ids:
		lift = normalized[prov_id] / max(baseline.get(prov_id, 1e-12), 1e-12)
		score = urs_from_log2(math.log2(lift))
		scored.append((prov_id, score))

	scored.sort(key=lambda item: item[1], reverse=True)
	top_results = scored[:k]

	definition_titles: List[str] = []
	if interpretation["definitions"]:
		title_rows = db.query(Provision.title).filter(
			Provision.internal_id.in_(interpretation["definitions"])
		).all()
		definition_titles = [row[0] for row in title_rows if row and row[0]]

	seed_provisions = list(seed_weights.keys())
	results: List[dict] = []
	for prov_id, score in top_results:
		row = meta.get(prov_id)
		if not row:
			continue

		why: List[dict] = []
		if include_explanations:
			incoming = db.query(Reference).filter(
				Reference.target_internal_id == prov_id,
				Reference.source_internal_id.in_(seed_provisions),
			).limit(1).all()
			outgoing = db.query(Reference).filter(
				Reference.source_internal_id == prov_id,
				Reference.target_internal_id.in_(seed_provisions),
			).limit(1).all()
			if incoming:
				why.append({
					"type": "citation",
					"detail": f"cited by seed {incoming[0].source_internal_id}",
					"weight": 0.34,
				})
			elif outgoing:
				why.append({
					"type": "citation",
					"detail": "it cites a seed",
					"weight": 0.28,
				})

			if definition_titles:
				lower_titles = [title.lower() for title in definition_titles]
				term_hit = db.query(DefinedTermUsage).filter(
					DefinedTermUsage.source_internal_id == prov_id,
					func.lower(DefinedTermUsage.term_text).in_(lower_titles),
				).first()
				if term_hit:
					why.append({
						"type": "term",
						"detail": f"uses '{term_hit.term_text}'",
						"weight": 0.22,
					})

			if not why and interpretation["provisions"]:
				parent_rows = db.query(Provision.parent_internal_id).filter(
					Provision.internal_id.in_([prov_id] + interpretation["provisions"])
				).all()
				parents = [value[0] for value in parent_rows if value and value[0]]
				if parents and len(set(parents)) <= 1:
					why.append({
						"type": "hierarchy",
						"detail": "shares parent with a seed",
						"weight": 0.15,
					})

			if not why:
				why.append({
					"type": "graph",
					"detail": "multi-hop proximity",
					"weight": 0.12,
				})
		else:
			why = []

		snippet = None
		if row.content_md and (interpretation["keywords"] or definition_titles):
			phrase = interpretation["keywords"] or (definition_titles[0] if definition_titles else "")
			if phrase:
				term = phrase.split()[0]
				content_lower = row.content_md.lower()
				idx = content_lower.find(term.lower())
				if idx >= 0:
					start = max(0, idx - 60)
					end = min(len(row.content_md), idx + 120)
					snippet = row.content_md[start:end].replace('
', ' ').strip()

		results.append({
			"id": prov_id,
			"ref_id": row.ref_id,
			"title": row.title,
			"type": row.type,
			"score_urs": score,
			"why": why,
			"snippet": snippet,
			"metrics": {
				"pagerank": row.pagerank,
				"in_degree": row.in_degree,
				"out_degree": row.out_degree,
			},
		})

	return {
		"query_interpretation": {
			"provisions": interpretation["provisions"],
			"definitions": interpretation["definitions"],
			"keywords": interpretation["keywords"],
			"pseudo_seeds": pseudo_seeds if not seed_weights and interpretation["keywords"] else [],
		},
		"results": results,
		"debug": {
			"mass_captured": round(float(captured_mass), 4),
			"num_seeds": len(seed_weights),
		},
	}

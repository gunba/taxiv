# ingest/core/relatedness_indexer.py
from __future__ import annotations

import logging
import os
import time
from collections import defaultdict, deque
from typing import Dict, List, Tuple, Set

import math

# Optional deps for semantic view
try:
	import numpy as np
except ImportError:
	np = None

from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.semantic import Embedding
from backend.services.search_filters import is_excluded_provision
from ingest.core.embedding_backend import (
	EmbeddingBackendUnavailable,
	get_embedding_backend,
)
from ingest.core.progress import progress_bar, progress_enabled

# Types
ProvisionId = str
logger = logging.getLogger(__name__)
FINGERPRINT_TOP_K = 200
FINGERPRINT_EPS = 1e-6


class RelatednessIndexerConfig:
	# Graph mixing (existing views)
	gamma: float = 0.50  # continue-walk prob; teleport = 1-gamma
	alpha_citation: float = 0.45
	alpha_hierarchy: float = 0.20
	alpha_term: float = 0.20
	act_id: str = os.getenv("RELATEDNESS_ACT_ID", "ITAA1997")

	# Embedding/runtime controls
	embedding_model_name: str = os.getenv(
		"RELATEDNESS_EMBED_MODEL",
		"Qwen/Qwen3-Embedding-0.6B"
	)
	embedding_device: str | None = os.getenv("RELATEDNESS_EMBED_DEVICE")
	embedding_batch_size: int = int(os.getenv("RELATEDNESS_EMBED_BATCH", "64"))
	embedding_max_length: int = int(os.getenv("RELATEDNESS_EMBED_MAX_LENGTH", "8192"))
	embedding_instruction: str | None = os.getenv("RELATEDNESS_EMBED_INSTRUCT")

	# Chunked embedding (averaging)
	chunk_chars: int = int(os.getenv("RELATEDNESS_EMBED_CHUNK_CHARS", "2200"))
	chunk_overlap: int = int(os.getenv("RELATEDNESS_EMBED_CHUNK_OVERLAP", "350"))

	# Hierarchy weights
	w_parent_child: float = 1.0
	w_adjacent_sibling: float = 0.8

	# IDF clamps for term co-usage
	idf_min: float = 0.2
	idf_max: float = 2.0


def _row_normalize(adj: Dict[ProvisionId, Dict[ProvisionId, float]]) -> Dict[
	ProvisionId, List[Tuple[ProvisionId, float]]]:
	out = {}
	for u, nbrs in adj.items():
		s = sum(v for v in nbrs.values())
		if s <= 0:
			out[u] = [(u, 1.0)]
		else:
			out[u] = [(v, w / s) for v, w in nbrs.items()]
	return out


def _approx_ppr_push(
	adj_norm: Dict[ProvisionId, List[Tuple[ProvisionId, float]]],
	seeds: Dict[ProvisionId, float],
	gamma: float,
	eps: float,
	top_k: int,
) -> Tuple[List[Tuple[ProvisionId, float]], float]:
	alpha = 1.0 - gamma
	ppr = defaultdict(float)
	residual = defaultdict(float, **seeds)
	queue = deque(seed for seed in seeds.keys())

	while queue:
		node = queue.popleft()
		value = residual[node]
		if value < eps:
			continue
		ppr[node] += alpha * value
		push_mass = gamma * value
		residual[node] = 0.0
		neighbors = adj_norm.get(node, [(node, 1.0)])
		for nbr, prob in neighbors:
			increment = push_mass * prob
			if increment < eps:
				continue
			prev = residual[nbr]
			residual[nbr] = prev + increment
			if prev < eps <= residual[nbr]:
				queue.append(nbr)

	items = sorted(ppr.items(), key=lambda kv: kv[1], reverse=True)[:top_k]
	captured = sum(weight for _, weight in items)
	return items, captured


def _power_iteration_pagerank(
		adj_norm: Dict[ProvisionId, List[Tuple[ProvisionId, float]]],
		gamma: float,
		nodes: List[ProvisionId],
		iters: int = 50
) -> Dict[ProvisionId, float]:
	N = len(nodes)
	idx = {n: i for i, n in enumerate(nodes)}
	r = [1.0 / N] * N  # uniform start
	teleport_mass = (1.0 - gamma) / N
	iter_progress = progress_bar(range(iters), desc="Power iteration", unit="iter", leave=False)
	for _ in iter_progress:
		new_r = [teleport_mass] * N
		for u, nbrs in adj_norm.items():
			pu = r[idx[u]]
			if not nbrs:
				new_r[idx[u]] += gamma * pu
			else:
				for v, p in nbrs:
					new_r[idx[v]] += gamma * pu * p
		r = new_r
	if hasattr(iter_progress, "close"):
		iter_progress.close()
	z = sum(r) or 1.0
	r = [x / z for x in r]
	return {n: r[idx[n]] for n in nodes}


# ----------------- Embedding helpers -----------------

def _prep_text_for_embedding(p: dict) -> str:
	# No 4k clamp; we embed by chunks downstream.
	title = (p.get("title") or "").strip()
	body = (p.get("content_md") or "").strip()
	return f"{title}\n{body}".strip()


def _split_into_chunks(text: str, *, chunk_chars: int, overlap: int) -> List[str]:
	if not text:
		return []
	text = text.strip()
	if chunk_chars <= 0:
		return [text]

	chunks: List[str] = []
	start = 0
	n = len(text)
	step = max(1, chunk_chars - max(0, overlap))
	while start < n:
		end = min(n, start + chunk_chars)
		if end < n:
			# try to break at nearest whitespace to avoid cutting tokens hard
			ws = text.rfind(" ", start + int(0.6 * chunk_chars), end)
			if ws > start:
				end = ws
		chunks.append(text[start:end].strip())
		if end == n:
			break
		start = max(end - overlap, end - 1)  # ensure progress
	return [c for c in chunks if c]


# ----------------- end embedding helpers -----------------


def upsert_provision_embeddings(
		provisions_payload: List[dict],
		model_name: str = "Qwen/Qwen3-Embedding-0.6B",
		batch_size: int = 64,
):
	"""Compute embeddings for provisions with **chunked averaging**, then upsert into pgvector."""
	if np is None:
		logger.warning("NumPy missing. Skipping embeddings upsert.")
		return

	cfg = RelatednessIndexerConfig()
	provision_ids = [p["internal_id"] for p in provisions_payload]
	full_texts = [_prep_text_for_embedding(p) for p in provisions_payload]

	# Build chunk corpus
	all_chunks: List[str] = []
	chunk_map: Dict[int, List[int]] = {}  # prov_index -> list of chunk indices in all_chunks
	for i, text in enumerate(full_texts):
		chunks = _split_into_chunks(text, chunk_chars=cfg.chunk_chars, overlap=cfg.chunk_overlap)
		if not chunks:
			chunks = [""]
		chunk_map[i] = list(range(len(all_chunks), len(all_chunks) + len(chunks)))
		all_chunks.extend(chunks)

	logger.info(
		"Encoding %d provisions as %d chunks with %s on Qwen backend (avg %.1f chunks/provision)",
		len(provision_ids), len(all_chunks), model_name, (len(all_chunks) / max(1, len(provision_ids)))
	)
	try:
		backend = get_embedding_backend(
			model_name,
			device=cfg.embedding_device,
			max_length=cfg.embedding_max_length,
		)
	except EmbeddingBackendUnavailable as exc:
		logger.warning("Embedding backend unavailable: %s. Skipping embeddings upsert.", exc)
		return

	# Encode all chunks in a single pass
	chunk_vectors = backend.encode(
		all_chunks,
		batch_size=batch_size,
		instruction=cfg.embedding_instruction,
	)

	# Average per-provision
	prov_vectors = []
	for i in range(len(provision_ids)):
		idxs = chunk_map[i]
		if not idxs:
			# extremely unlikely; fall back to zero vector
			vec = np.zeros((chunk_vectors.shape[1],), dtype=np.float32)
		else:
			vecs = np.vstack([chunk_vectors[j] for j in idxs])
			vec = np.mean(vecs, axis=0)
			n = np.linalg.norm(vec) or 1.0
			vec = (vec / n).astype(np.float32)
		prov_vectors.append(vec)

	db_gen = get_db()
	try:
		db: Session = next(db_gen)
	except StopIteration:
		logger.error("Unable to establish database session for embedding upsert.")
		return

	try:
		if provision_ids:
			deleted = db.query(Embedding).filter(
				Embedding.entity_kind == "provision",
				Embedding.model == model_name,
				Embedding.entity_id.in_(provision_ids),
			).delete(synchronize_session=False)
			logger.info("Removed %d existing embeddings for refresh.", deleted)

		for pid, vec in zip(provision_ids, prov_vectors):
			db.merge(Embedding(
				entity_kind="provision",
				entity_id=pid,
				model=model_name,
				dim=len(vec),
				vector=np.asarray(vec, dtype=np.float32),
				l2_norm=1.0,
			))
		db.commit()
		logger.info("Provision embeddings upsert complete.")
	except Exception as exc:
		db.rollback()
		logger.error("Failed to upsert embeddings: %s", exc)
		raise
	finally:
		try:
			next(db_gen)
		except StopIteration:
			pass


def build_relatedness_index(
		provisions_payload: List[dict],
		references_payload: List[dict],
		defined_terms_usage_payload: List[dict],
		cfg: RelatednessIndexerConfig = RelatednessIndexerConfig()
):
	"""
	Returns:
		baseline_pi: Dict[prov_id -> float]
		fingerprints: Dict[source_id -> Tuple[List[Dict], float]]
	"""
	# 1) Collect provision ids & basic maps
	prov_ids: List[ProvisionId] = [p["internal_id"] for p in provisions_payload]
	prov_set: Set[ProvisionId] = set(prov_ids)
	parent_of: Dict[ProvisionId, ProvisionId | None] = {p["internal_id"]: p.get("parent_internal_id") for p in
														provisions_payload}
	siblings_by_parent: Dict[ProvisionId | None, List[Tuple[int, ProvisionId]]] = defaultdict(list)
	for p in provisions_payload:
		siblings_by_parent[p.get("parent_internal_id")].append((p.get("sibling_order", 0), p["internal_id"]))
	for k in siblings_by_parent:
		siblings_by_parent[k].sort(key=lambda x: (x[0] is None, x[0], x[1]))

	# 2) Build per-view adjacencies (raw weights)
	A_cit = defaultdict(lambda: defaultdict(float))  # directed
	pbar_refs = progress_bar(
		references_payload,
		desc="Indexing citation edges",
		unit="ref",
		total=len(references_payload),
		leave=False
	)
	for r in pbar_refs:
		u = r["source_internal_id"]
		v = r.get("target_internal_id")
		if not v or u == v or (u not in prov_set) or (v not in prov_set):
			continue
		A_cit[u][v] += 1.0
	if hasattr(pbar_refs, "close"):
		pbar_refs.close()

	A_h = defaultdict(lambda: defaultdict(float))  # undirected (add both directions)
	for v, p in parent_of.items():
		if p and p in prov_set and v in prov_set:
			A_h[v][p] += cfg.w_parent_child
			A_h[p][v] += cfg.w_parent_child
	for parent, ordered in siblings_by_parent.items():
		ids_sib = [vid for _, vid in ordered]
		for i in range(len(ids_sib) - 1):
			a, b = ids_sib[i], ids_sib[i + 1]
			A_h[a][b] += cfg.w_adjacent_sibling
			A_h[b][a] += cfg.w_adjacent_sibling

	# Term co-usage (P-P, symmetric) with IDF
	term_map = defaultdict(set)  # term_text -> set(provision_id)
	pbar_terms_usage = progress_bar(
		defined_terms_usage_payload,
		desc="Collecting term usages",
		unit="term",
		total=len(defined_terms_usage_payload),
		leave=False
	)
	for t in pbar_terms_usage:
		u = t["source_internal_id"]
		if u in prov_set:
			term_map[t["term_text"].strip().lower()].add(u)
	if hasattr(pbar_terms_usage, "close"):
		pbar_terms_usage.close()

	A_t = defaultdict(lambda: defaultdict(float))
	for term, plist_set in term_map.items():
		plist = list(plist_set)
		df = max(1, len(plist))
		idf = 1.0 / math.log(1.0 + df)
		idf = max(cfg.idf_min, min(cfg.idf_max, idf))
		for i in range(len(plist)):
			ui = plist[i]
			for j in range(i + 1, len(plist)):
				vj = plist[j]
				A_t[ui][vj] += idf
				A_t[vj][ui] += idf

	# 3) Aggregate & row-normalize
	A_raw = defaultdict(lambda: defaultdict(float))
	for u in prov_ids:
		for v, w in A_cit[u].items(): A_raw[u][v] += cfg.alpha_citation * w
		for v, w in A_h[u].items():   A_raw[u][v] += cfg.alpha_hierarchy * w
		for v, w in A_t[u].items():   A_raw[u][v] += cfg.alpha_term * w
		if not A_raw[u]:
			A_raw[u][u] += 1.0

	A_norm = _row_normalize(A_raw)

	# 4) Baseline PageRank-like vector (π) over provisions
	logger.info(
		"Starting baseline PageRank over %d provisions (gamma=%.2f)",
		len(prov_ids),
		cfg.gamma,
	)
	baseline_start = time.perf_counter()
	baseline_pi = _power_iteration_pagerank(A_norm, cfg.gamma, prov_ids, iters=50)
	logger.info(
		"Completed baseline PageRank in %.2f seconds.",
		time.perf_counter() - baseline_start,
	)

	logger.info("Computing fingerprints for %d provisions...", len(prov_ids))
	fingerprint_start = time.perf_counter()
	fingerprints: Dict[ProvisionId, Tuple[List[Dict], float]] = {}
	pbar_fingerprints = progress_bar(
		prov_ids,
		desc="Fingerprints",
		unit="node",
		total=len(prov_ids),
		leave=False,
	)
	for prov_id in pbar_fingerprints:
		if is_excluded_provision(act_id=cfg.act_id, provision_id=prov_id):
			continue
		items, captured = _approx_ppr_push(
			A_norm,
			{prov_id: 1.0},
			gamma=cfg.gamma,
			eps=FINGERPRINT_EPS,
			top_k=FINGERPRINT_TOP_K,
		)
		filtered = [
			{"prov_id": neighbor_id, "ppr_mass": float(mass)}
			for neighbor_id, mass in items
			if neighbor_id != prov_id and not is_excluded_provision(act_id=cfg.act_id, provision_id=neighbor_id)
		][:FINGERPRINT_TOP_K]
		fingerprints[prov_id] = (filtered, float(captured))
	if hasattr(pbar_fingerprints, "close"):
		pbar_fingerprints.close()
	logger.info(
		"Fingerprint precompute complete (%d cached) in %.2f seconds.",
		len(fingerprints),
		time.perf_counter() - fingerprint_start,
	)
	return baseline_pi, fingerprints

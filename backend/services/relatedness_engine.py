from __future__ import annotations

import logging
from collections import defaultdict, deque
from typing import Dict, List, Set, Tuple

from cachetools import LRUCache
from sqlalchemy import bindparam, or_, text
from sqlalchemy.orm import Session

from backend.models.legislation import (
	DefinedTermUsage,
	Provision,
	Reference,
	RelatednessFingerprint,
)
from backend.models.semantic import Embedding, GraphMeta, ensure_graph_meta_seed
from backend.services.search_filters import is_excluded_provision

logger = logging.getLogger(__name__)

# Mixing weights and caps
ALPHA_CIT = 0.45
ALPHA_HIER = 0.20
ALPHA_TERM = 0.20
# Reduce semantic weight; lexical seeding handles topicality better
ALPHA_SEM = 0.05
GAMMA = 0.55  # slightly more conservative continuation
TOP_K = 200
EPS = 1e-6

# Subgraph controls
MAX_NODES = 5000
MAX_EDGES = 40_000
RADIUS = 2
TERM_LIMIT_PER_TERM = 200
SEM_K = 80
EMBED_MODEL = "Qwen/Qwen3-Embedding-0.6B"

_SEM_VECTOR_CACHE: LRUCache[str, object] = LRUCache(maxsize=512)
_PARENT_CHILD_CACHE: Dict[int, Tuple[Dict[str, str | None], Dict[str, List[str]]]] = {}


def _belongs_to_act(internal_id: str | None, act_id: str | None) -> bool:
	if not internal_id:
		return False
	if not act_id:
		return True
	return internal_id.startswith(f"{act_id}_")


def _ensure_parent_child_snapshot(db: Session, version: int) -> Tuple[Dict[str, str | None], Dict[str, List[str]]]:
	snapshot = _PARENT_CHILD_CACHE.get(version)
	if snapshot:
		return snapshot

	rows = db.query(
		Provision.internal_id,
		Provision.parent_internal_id,
		Provision.sibling_order,
	).all()
	parent_map: Dict[str, str | None] = {}
	children_map: Dict[str, List[Tuple[int | None, str]]] = defaultdict(list)
	for child_id, parent_id, sibling_order in rows:
		parent_map[child_id] = parent_id
		if parent_id:
			children_map[parent_id].append((sibling_order, child_id))

	ordered_children: Dict[str, List[str]] = {}
	for parent_id, siblings in children_map.items():
		siblings.sort(key=lambda item: (item[0] is None, item[0], item[1]))
		ordered_children[parent_id] = [child for _, child in siblings]

	snapshot = (parent_map, ordered_children)
	_PARENT_CHILD_CACHE[version] = snapshot
	while len(_PARENT_CHILD_CACHE) > 2:
		_PARENT_CHILD_CACHE.pop(next(iter(_PARENT_CHILD_CACHE)))
	return snapshot


def _get_seed_vector(db: Session, provision_id: str):
	cached = _SEM_VECTOR_CACHE.get(provision_id)
	if cached is not None:
		return cached
	row = db.query(Embedding.vector).filter(
		Embedding.entity_kind == "provision",
		Embedding.entity_id == provision_id,
		Embedding.model == EMBED_MODEL,
	).first()
	if not row:
		return None
	_SEM_VECTOR_CACHE[provision_id] = row[0]
	return row[0]


def _row_normalize(adj: Dict[str, Dict[str, float]]) -> Dict[str, List[Tuple[str, float]]]:
	out: Dict[str, List[Tuple[str, float]]] = {}
	for node, neighbors in adj.items():
		total = sum(neighbors.values())
		if total <= 0:
			out[node] = [(node, 1.0)]
			continue
		out[node] = [(nbr, weight / total) for nbr, weight in neighbors.items()]
	return out


def _approx_ppr_push(
	adj_norm: Dict[str, List[Tuple[str, float]]],
	seeds: Dict[str, float],
	gamma: float,
	eps: float,
	top_k: int,
) -> Tuple[List[Tuple[str, float]], float]:
	alpha = 1.0 - gamma
	ppr = defaultdict(float)
	residual = defaultdict(float, **seeds)
	queue = deque([seed for seed in seeds.keys()])

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


def get_graph_version(db: Session) -> int:
	row = db.query(GraphMeta).order_by(GraphMeta.id.desc()).first()
	if row:
		return row.graph_version
	seed = ensure_graph_meta_seed(db)
	return seed.graph_version


def _semantic_neighbors(
	db: Session,
	provision_id: str,
	k: int = SEM_K,
	vector_param=None,
	act_id: str | None = None,
) -> List[Tuple[str, float]]:
	if vector_param is None:
		vector_param = _get_seed_vector(db, provision_id)
	if vector_param is None:
		return []
	sql = text(
		"""
		SELECT entity_id,
		       1.0 - ((vector <-> :vec)::float / 2.0) AS sim
		FROM embeddings
		WHERE entity_kind = 'provision'
		  AND model = :model
		  AND entity_id <> :pid
		ORDER BY vector <-> :vec
		LIMIT :limit
		"""
	).bindparams(bindparam("vec", type_=Embedding.__table__.c.vector.type))
	rows = db.execute(
		sql,
		{"vec": vector_param, "model": EMBED_MODEL, "pid": provision_id, "limit": k},
	).fetchall()
	results: List[Tuple[str, float]] = []
	for row in rows:
		entity_id = row[0]
		if not entity_id:
			continue
		if act_id and not _belongs_to_act(entity_id, act_id):
			continue
		if is_excluded_provision(act_id=act_id, provision_id=entity_id):
			continue
		results.append((entity_id, float(row[1])))
	return results


def _expand_local_subgraph(
	db: Session,
	seeds: Set[str],
	graph_version: int | None = None,
	act_id: str | None = None,
) -> Tuple[Set[str], List[Tuple[str, str, str]]]:
	filtered_seeds = {
		seed for seed in seeds
		if _belongs_to_act(seed, act_id) and not is_excluded_provision(act_id=act_id, provision_id=seed)
	}
	if not filtered_seeds:
		return set(), []

	version = graph_version or get_graph_version(db)
	nodes: Set[str] = set(filtered_seeds)
	edges: List[Tuple[str, str, str]] = []
	frontier = set(filtered_seeds)
	visited = set(filtered_seeds)

	for _ in range(RADIUS):
		if not frontier or len(nodes) >= MAX_NODES:
			break
		ref_rows = db.query(
			Reference.source_internal_id,
			Reference.target_internal_id,
		).filter(
			or_(
				Reference.source_internal_id.in_(frontier),
				Reference.target_internal_id.in_(frontier),
			)
		).all()

		next_frontier: Set[str] = set()
		for source_id, target_id in ref_rows:
			if not target_id:
				continue
			if not _belongs_to_act(source_id, act_id) or not _belongs_to_act(target_id, act_id):
				continue
			if is_excluded_provision(act_id=act_id, provision_id=source_id) or is_excluded_provision(
				act_id=act_id, provision_id=target_id
			):
				continue
			edges.append((source_id, target_id, "cit"))
			nodes.add(source_id)
			nodes.add(target_id)
			next_frontier.add(source_id)
			next_frontier.add(target_id)
			if len(edges) >= MAX_EDGES:
				break
		visited |= next_frontier
		frontier = (next_frontier - frontier)
		if len(edges) >= MAX_EDGES:
			break

	# Hierarchy edges: connect parents/children plus adjacent siblings
	parent_map, children_map = _ensure_parent_child_snapshot(db, version)
	parent_ids = set()
	for child_id in list(nodes):
		parent_id = parent_map.get(child_id)
		if not parent_id or not _belongs_to_act(parent_id, act_id):
			continue
		if is_excluded_provision(act_id=act_id, provision_id=parent_id):
			continue
		edges.append((child_id, parent_id, "hier"))
		edges.append((parent_id, child_id, "hier"))
		nodes.add(parent_id)
		parent_ids.add(parent_id)

	for parent_id in parent_ids:
		for child_id in children_map.get(parent_id, []):
			if not _belongs_to_act(child_id, act_id):
				continue
			if is_excluded_provision(act_id=act_id, provision_id=child_id):
				continue
			edges.append((child_id, parent_id, "hier"))
			edges.append((parent_id, child_id, "hier"))
			nodes.add(child_id)
		siblings = [
			child
			for child in children_map.get(parent_id, [])
			if _belongs_to_act(child, act_id) and not is_excluded_provision(act_id=act_id, provision_id=child)
		]
		for i in range(len(siblings) - 1):
			a, b = siblings[i], siblings[i + 1]
			edges.append((a, b, "hier"))
			edges.append((b, a, "hier"))

	# Term co-usage limited to terms present in seeds
	seed_terms = db.query(DefinedTermUsage.term_text).filter(
		DefinedTermUsage.source_internal_id.in_(list(filtered_seeds)),
	).distinct().all()
	term_texts = [row[0] for row in seed_terms if row and row[0]]
	if term_texts:
		term_rows = db.query(
			DefinedTermUsage.source_internal_id,
			DefinedTermUsage.term_text,
		).filter(
			DefinedTermUsage.term_text.in_(term_texts),
		).all()
		by_term: Dict[str, List[str]] = defaultdict(list)
		for pid, term in term_rows:
			if not pid or not term:
				continue
			if not _belongs_to_act(pid, act_id):
				continue
			if is_excluded_provision(act_id=act_id, provision_id=pid):
				continue
			if pid not in nodes:
				nodes.add(pid)
			by_term[term].append(pid)
		for pid_list in by_term.values():
			unique_ids = list(dict.fromkeys(pid_list))[:TERM_LIMIT_PER_TERM]
			for i in range(len(unique_ids) - 1):
				for j in range(i + 1, len(unique_ids)):
					u, v = unique_ids[i], unique_ids[j]
					if not _belongs_to_act(u, act_id) or not _belongs_to_act(v, act_id):
						continue
					edges.append((u, v, "term"))
					edges.append((v, u, "term"))

	# Semantic neighbors taken directly from ANN
	for seed_id in list(filtered_seeds):
		vector_param = _get_seed_vector(db, seed_id)
		if vector_param is None:
			continue
		for neighbor_id, _sim in _semantic_neighbors(
			db,
			seed_id,
			SEM_K,
			vector_param=vector_param,
			act_id=act_id,
		):
			if len(nodes) >= MAX_NODES or len(edges) >= MAX_EDGES:
				break
			if not _belongs_to_act(neighbor_id, act_id):
				continue
			if is_excluded_provision(act_id=act_id, provision_id=neighbor_id):
				continue
			nodes.add(neighbor_id)
			edges.append((seed_id, neighbor_id, "sem"))
			edges.append((neighbor_id, seed_id, "sem"))

	return nodes, edges


def _build_weighted_adjacency(nodes: Set[str], typed_edges: List[Tuple[str, str, str]]):
	adjacency: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))

	for source, target, view in typed_edges:
		if view == "cit":
			adjacency[source][target] += ALPHA_CIT
		elif view == "hier":
			adjacency[source][target] += ALPHA_HIER
		elif view == "term":
			adjacency[source][target] += ALPHA_TERM
		elif view == "sem":
			adjacency[source][target] += ALPHA_SEM

	for node in nodes:
		if not adjacency[node]:
			adjacency[node][node] += 1.0

	return adjacency


def compute_fingerprint(
	db: Session,
	seed_id: str,
	k: int = TOP_K,
	*,
	act_id: str | None = None,
) -> Tuple[List[Tuple[str, float]], float]:
	if is_excluded_provision(act_id=act_id, provision_id=seed_id):
		return [], 0.0
	version = get_graph_version(db)
	node_set, typed_edges = _expand_local_subgraph(
		db,
		{seed_id},
		graph_version=version,
		act_id=act_id,
	)
	adjacency = _build_weighted_adjacency(node_set, typed_edges)
	adj_norm = _row_normalize(adjacency)
	items, captured = _approx_ppr_push(adj_norm, {seed_id: 1.0}, gamma=GAMMA, eps=EPS, top_k=k)
	items = [(pid, mass) for pid, mass in items if pid != seed_id][:k]
	return items, captured


def compute_fingerprint_multi(
	db: Session,
	seed_weights: Dict[str, float],
	k: int = TOP_K,
	*,
	act_id: str | None = None,
) -> Tuple[List[Tuple[str, float]], float]:
	cleaned = {
		seed: weight
		for seed, weight in seed_weights.items()
		if weight > 0 and not is_excluded_provision(act_id=act_id, provision_id=seed)
	}
	if not cleaned:
		return [], 0.0
	version = get_graph_version(db)
	node_set, typed_edges = _expand_local_subgraph(
		db,
		set(cleaned.keys()),
		graph_version=version,
		act_id=act_id,
	)
	adjacency = _build_weighted_adjacency(node_set, typed_edges)
	adj_norm = _row_normalize(adjacency)
	total = sum(cleaned.values()) or 1.0
	seeds_norm = {seed: weight / total for seed, weight in cleaned.items()}
	items, captured = _approx_ppr_push(adj_norm, seeds_norm, gamma=GAMMA, eps=EPS, top_k=k)
	items = [(pid, mass) for pid, mass in items if pid not in cleaned][:k]
	return items[:k], captured


def get_or_compute_and_cache(
	db: Session,
	seed_id: str,
	*,
	act_id: str | None = None,
) -> Tuple[List[Tuple[str, float]], float]:
	if is_excluded_provision(act_id=act_id, provision_id=seed_id):
		return [], 0.0
	current_version = get_graph_version(db)
	row = db.query(RelatednessFingerprint).filter(
		RelatednessFingerprint.source_kind == "provision",
		RelatednessFingerprint.source_id == seed_id,
	).first()

	if row and row.graph_version == current_version and row.neighbors:
		neighbors = [
			(item.get("prov_id"), float(item.get("ppr_mass", 0.0)))
			for item in row.neighbors or []
			if item.get("prov_id")
		]
		return neighbors, float(row.captured_mass_provisions or 0.0)

	neighbors, captured = compute_fingerprint(db, seed_id, act_id=act_id)
	payload = {
		"neighbors": [{"prov_id": pid, "ppr_mass": float(mass)} for pid, mass in neighbors],
		"captured_mass_provisions": float(captured),
		"graph_version": current_version,
	}

	if row:
		row.neighbors = payload["neighbors"]
		row.captured_mass_provisions = payload["captured_mass_provisions"]
		row.graph_version = current_version
	else:
		db.add(RelatednessFingerprint(
			source_kind="provision",
			source_id=seed_id,
			**payload,
		))

	db.commit()
	return neighbors, captured


def get_cached_fingerprints(
	db: Session,
	seed_ids: Set[str],
	expected_version: int,
	*,
	act_id: str | None = None,
) -> Tuple[Dict[str, Tuple[List[Tuple[str, float]], float]], Set[str]]:
	valid_seeds = {seed for seed in seed_ids if not is_excluded_provision(act_id=act_id, provision_id=seed)}
	if not valid_seeds:
		return {}, set()

	rows = db.query(RelatednessFingerprint).filter(
		RelatednessFingerprint.source_kind == "provision",
		RelatednessFingerprint.source_id.in_(valid_seeds),
	).all()

	cached: Dict[str, Tuple[List[Tuple[str, float]], float]] = {}
	missing: Set[str] = set(valid_seeds)
	for row in rows:
		if row.graph_version != expected_version or not row.neighbors:
			continue
		neighbor_items: List[Tuple[str, float]] = []
		for item in row.neighbors or []:
			pid = item.get("prov_id")
			if not pid:
				continue
			if act_id and not _belongs_to_act(pid, act_id):
				continue
			if is_excluded_provision(act_id=act_id, provision_id=pid):
				continue
			neighbor_items.append((pid, float(item.get("ppr_mass", 0.0))))
		cached[row.source_id] = (neighbor_items, float(row.captured_mass_provisions or 0.0))
		missing.discard(row.source_id)

	return cached, missing

from __future__ import annotations

import math
from collections import defaultdict, deque
from typing import Dict, List, Set, Tuple

ProvisionId = str


class RelatednessIndexerConfig:
	gamma: float = 0.50
	alpha_citation: float = 0.45
	alpha_hierarchy: float = 0.20
	alpha_term: float = 0.20
	top_k: int = 200
	eps: float = 1e-6
	w_parent_child: float = 1.0
	w_adjacent_sibling: float = 0.8
	idf_min: float = 0.2
	idf_max: float = 2.0


def _row_normalize(adj: Dict[ProvisionId, Dict[ProvisionId, float]]) -> Dict[ProvisionId, List[Tuple[ProvisionId, float]]]:
	out: Dict[ProvisionId, List[Tuple[ProvisionId, float]]] = {}
	for u, nbrs in adj.items():
		total = sum(nbrs.values())
		if total <= 0:
			out[u] = [(u, 1.0)]
		else:
			out[u] = [(v, w / total) for v, w in nbrs.items()]
	return out


def _power_iteration_pagerank(
	adj_norm: Dict[ProvisionId, List[Tuple[ProvisionId, float]]],
	gamma: float,
	nodes: List[ProvisionId],
	iters: int = 50
) -> Dict[ProvisionId, float]:
	count = len(nodes)
	if count == 0:
		return {}
	index = {node: idx for idx, node in enumerate(nodes)}
	ranks = [1.0 / count] * count
	teleport_mass = (1.0 - gamma) / count
	for _ in range(iters):
		new_ranks = [teleport_mass] * count
		for u, nbrs in adj_norm.items():
			idx_u = index.get(u)
			if idx_u is None:
				continue
			r_u = ranks[idx_u]
			if not nbrs:
				new_ranks[idx_u] += gamma * r_u
			else:
				for v, prob in nbrs:
					idx_v = index.get(v)
					if idx_v is None:
						continue
					new_ranks[idx_v] += gamma * r_u * prob
		ranks = new_ranks
	total = sum(ranks) or 1.0
	norm = [value / total for value in ranks]
	return {node: norm[index[node]] for node in nodes}


def _approximate_ppr_push(
	adj_norm: Dict[ProvisionId, List[Tuple[ProvisionId, float]]],
	seed: ProvisionId,
	gamma: float,
	eps: float,
	top_k: int
) -> Tuple[List[Tuple[ProvisionId, float]], float]:
	teleport = 1.0 - gamma
	solution: Dict[ProvisionId, float] = defaultdict(float)
	residual: Dict[ProvisionId, float] = defaultdict(float)
	queue: deque[ProvisionId] = deque([seed])
	residual[seed] = 1.0

	while queue:
		node = queue.popleft()
		r_node = residual[node]
		if r_node < eps:
			continue
		solution[node] += teleport * r_node
		push_mass = gamma * r_node
		residual[node] = 0.0
		nbrs = adj_norm.get(node, [(node, 1.0)])
		for nbr, prob in nbrs:
			increment = push_mass * prob
			if increment < eps:
				continue
			prev = residual[nbr]
			residual[nbr] = prev + increment
			if prev < eps and residual[nbr] >= eps:
				queue.append(nbr)

	items = sorted(solution.items(), key=lambda item: item[1], reverse=True)[:top_k]
	captured = sum(value for _, value in items)
	return items, captured


def build_relatedness_index(
	provisions_payload: List[dict],
	references_payload: List[dict],
	defined_terms_usage_payload: List[dict],
	cfg: RelatednessIndexerConfig = RelatednessIndexerConfig()
) -> Tuple[Dict[ProvisionId, float], Dict[ProvisionId, Tuple[List[Dict[str, float]], float]]]:
	provision_ids: List[ProvisionId] = [payload["internal_id"] for payload in provisions_payload]
	provision_set: Set[ProvisionId] = set(provision_ids)
	parent_of: Dict[ProvisionId, ProvisionId | None] = {
		payload["internal_id"]: payload.get("parent_internal_id")
		for payload in provisions_payload
	}
	siblings_by_parent: Dict[ProvisionId | None, List[Tuple[int, ProvisionId]]] = defaultdict(list)
	for payload in provisions_payload:
		parent = payload.get("parent_internal_id")
		siblings_by_parent[parent].append(((payload.get("sibling_order", 0) or 0), payload["internal_id"]))
	for parent, children in siblings_by_parent.items():
		children.sort(key=lambda item: (item[0] is None, item[0], item[1]))

	citation_adj: Dict[ProvisionId, Dict[ProvisionId, float]] = defaultdict(lambda: defaultdict(float))
	for ref in references_payload:
		source = ref.get("source_internal_id")
		target = ref.get("target_internal_id")
		if not source or not target or source == target:
			continue
		if source not in provision_set or target not in provision_set:
			continue
		citation_adj[source][target] += 1.0

	hierarchy_adj: Dict[ProvisionId, Dict[ProvisionId, float]] = defaultdict(lambda: defaultdict(float))
	for child, parent in parent_of.items():
		if not parent or child not in provision_set or parent not in provision_set:
			continue
		hierarchy_adj[child][parent] += cfg.w_parent_child
		hierarchy_adj[parent][child] += cfg.w_parent_child
	for _, ordered in siblings_by_parent.items():
		ordered_ids = [prov_id for _, prov_id in ordered]
		for idx in range(len(ordered_ids) - 1):
			left = ordered_ids[idx]
			right = ordered_ids[idx + 1]
			hierarchy_adj[left][right] += cfg.w_adjacent_sibling
			hierarchy_adj[right][left] += cfg.w_adjacent_sibling

	term_map: Dict[str, Set[ProvisionId]] = defaultdict(set)
	for usage in defined_terms_usage_payload:
		source_id = usage.get("source_internal_id")
		term_text = (usage.get("term_text") or "").strip().lower()
		if not source_id or not term_text or source_id not in provision_set:
			continue
		term_map[term_text].add(source_id)

	term_adj: Dict[ProvisionId, Dict[ProvisionId, float]] = defaultdict(lambda: defaultdict(float))
	for term, provision_ids_for_term in term_map.items():
		provision_list = list(provision_ids_for_term)
		df = max(1, len(provision_list))
		idf = 1.0 / math.log(1.0 + df)
		idf = max(cfg.idf_min, min(cfg.idf_max, idf))
		for idx in range(len(provision_list)):
			first = provision_list[idx]
			for jdx in range(idx + 1, len(provision_list)):
				second = provision_list[jdx]
				term_adj[first][second] += idf
				term_adj[second][first] += idf

	aggregated_adj: Dict[ProvisionId, Dict[ProvisionId, float]] = defaultdict(lambda: defaultdict(float))
	for prov_id in provision_ids:
		for target, weight in citation_adj[prov_id].items():
			aggregated_adj[prov_id][target] += cfg.alpha_citation * weight
		for target, weight in hierarchy_adj[prov_id].items():
			aggregated_adj[prov_id][target] += cfg.alpha_hierarchy * weight
		for target, weight in term_adj[prov_id].items():
			aggregated_adj[prov_id][target] += cfg.alpha_term * weight
		if not aggregated_adj[prov_id]:
			aggregated_adj[prov_id][prov_id] += 1.0

	normalized_adj = _row_normalize(aggregated_adj)
	baseline_pi = _power_iteration_pagerank(normalized_adj, cfg.gamma, provision_ids, iters=50)

	fingerprints: Dict[ProvisionId, Tuple[List[Dict[str, float]], float]] = {}
	for seed in provision_ids:
		neighborhood, captured = _approximate_ppr_push(normalized_adj, seed, cfg.gamma, cfg.eps, cfg.top_k)
		neighbors = [
			{"prov_id": prov, "ppr_mass": float(mass)}
			for prov, mass in neighborhood
		]
		fingerprints[seed] = (neighbors, float(captured))

	return baseline_pi, fingerprints

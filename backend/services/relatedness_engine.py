from __future__ import annotations

import logging
from collections import defaultdict, deque
from typing import Dict, List, Set, Tuple

from sqlalchemy import bindparam, or_, text
from sqlalchemy.orm import Session

from backend.models.legislation import (
    DefinedTermUsage,
    Provision,
    Reference,
    RelatednessFingerprint,
)
from backend.models.semantic import Embedding, GraphMeta, ensure_graph_meta_seed

logger = logging.getLogger(__name__)

# Mixing weights and caps
ALPHA_CIT = 0.45
ALPHA_HIER = 0.20
ALPHA_TERM = 0.20
ALPHA_SEM = 0.25  # slightly higher semantic weight to stabilize similarities
GAMMA = 0.50  # continue-walk probability
TOP_K = 200
EPS = 1e-6

# Subgraph controls
MAX_NODES = 5000
MAX_EDGES = 40_000
RADIUS = 2
TERM_LIMIT_PER_TERM = 200
SEM_K = 80
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


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


def _graph_version(db: Session) -> int:
    row = db.query(GraphMeta).order_by(GraphMeta.id.desc()).first()
    if row:
        return row.graph_version
    seed = ensure_graph_meta_seed(db)
    return seed.graph_version


def _semantic_neighbors(db: Session, provision_id: str, k: int = SEM_K) -> List[Tuple[str, float]]:
    vec_row = db.query(Embedding.vector).filter(
        Embedding.entity_kind == "provision",
        Embedding.entity_id == provision_id,
        Embedding.model == EMBED_MODEL,
    ).first()
    if not vec_row:
        return []
    vector_param = vec_row[0]
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
    return [(row[0], float(row[1])) for row in rows if row[0]]


def _expand_local_subgraph(db: Session, seeds: Set[str]) -> Tuple[Set[str], List[Tuple[str, str, str]]]:
    nodes: Set[str] = set(seeds)
    edges: List[Tuple[str, str, str]] = []
    frontier = set(seeds)
    visited = set(seeds)

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

    # Hierarchy edges
    parent_rows = db.query(
        Provision.internal_id,
        Provision.parent_internal_id,
    ).filter(
        Provision.internal_id.in_(list(nodes)),
    ).all()
    parent_ids = set()
    for child_id, parent_id in parent_rows:
        if not parent_id:
            continue
        edges.append((child_id, parent_id, "hier"))
        edges.append((parent_id, child_id, "hier"))
        nodes.add(parent_id)
        parent_ids.add(parent_id)

    if parent_ids:
        child_rows = db.query(
            Provision.internal_id,
            Provision.parent_internal_id,
        ).filter(
            Provision.parent_internal_id.in_(list(parent_ids)),
        ).all()
        children_by_parent: Dict[str, List[str]] = defaultdict(list)
        for child_id, parent_id in child_rows:
            if not parent_id:
                continue
            children_by_parent[parent_id].append(child_id)
            edges.append((child_id, parent_id, "hier"))
            edges.append((parent_id, child_id, "hier"))
            nodes.add(child_id)
        for siblings in children_by_parent.values():
            for i in range(len(siblings) - 1):
                a, b = siblings[i], siblings[i + 1]
                edges.append((a, b, "hier"))
                edges.append((b, a, "hier"))

    # Term co-usage limited to terms present in seeds
    seed_terms = db.query(DefinedTermUsage.term_text).filter(
        DefinedTermUsage.source_internal_id.in_(list(seeds)),
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
            if pid not in nodes:
                nodes.add(pid)
            by_term[term].append(pid)
        for pid_list in by_term.values():
            unique_ids = list(dict.fromkeys(pid_list))[:TERM_LIMIT_PER_TERM]
            for i in range(len(unique_ids) - 1):
                for j in range(i + 1, len(unique_ids)):
                    u, v = unique_ids[i], unique_ids[j]
                    edges.append((u, v, "term"))
                    edges.append((v, u, "term"))

    # Semantic neighbors
    for seed_id in list(seeds):
        for neighbor_id, _sim in _semantic_neighbors(db, seed_id, SEM_K):
            if len(nodes) >= MAX_NODES or len(edges) >= MAX_EDGES:
                break
            nodes.add(neighbor_id)
            edges.append((seed_id, neighbor_id, "sem"))
            edges.append((neighbor_id, seed_id, "sem"))

    return nodes, edges


def compute_fingerprint(db: Session, seed_id: str, k: int = TOP_K) -> Tuple[List[Tuple[str, float]], float]:
    node_set, typed_edges = _expand_local_subgraph(db, {seed_id})
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

    for node in node_set:
        if not adjacency[node]:
            adjacency[node][node] += 1.0

    adj_norm = _row_normalize(adjacency)
    items, captured = _approx_ppr_push(adj_norm, {seed_id: 1.0}, gamma=GAMMA, eps=EPS, top_k=k)
    # Keep the seed in the list so callers can choose to display or boost it.
    items = items[:k]
    return items, captured


def get_or_compute_and_cache(db: Session, seed_id: str) -> Tuple[List[Tuple[str, float]], float]:
    current_version = _graph_version(db)
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

    neighbors, captured = compute_fingerprint(db, seed_id)
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

# ingest/core/relatedness_indexer.py
from __future__ import annotations
import math
import os
import logging
from collections import defaultdict, deque
from typing import Dict, List, Tuple, Iterable, Set

# Optional deps for semantic view
try:
    import numpy as np
except ImportError:
    np = None

try:
    from sentence_transformers import SentenceTransformer
except Exception:
    SentenceTransformer = None

# Types
ProvisionId = str
logger = logging.getLogger(__name__)


class RelatednessIndexerConfig:
    # Graph mixing (existing views)
    gamma: float = 0.50               # continue-walk prob; teleport = 1-gamma
    alpha_citation: float = 0.45
    alpha_hierarchy: float = 0.20
    alpha_term: float = 0.20

    # --- NEW: semantic view knobs ---
    alpha_semantic: float = 0.15      # weight of semantic edges in the multiplex
    semantic_k: int = 80              # k-NN edges per node
    semantic_min_cos: float = 0.35    # cosine threshold to suppress weak neighbors

    # Embedding/runtime controls
    embedding_model_name: str = os.getenv(
        "RELATEDNESS_EMBED_MODEL",
        "sentence-transformers/all-MiniLM-L6-v2"
    )
    embedding_batch_size: int = int(os.getenv("RELATEDNESS_EMBED_BATCH", "64"))
    knn_batch_size: int = int(os.getenv("RELATEDNESS_KNN_BATCH", "1024"))
    max_text_chars: int = int(os.getenv("RELATEDNESS_MAX_TEXT_CHARS", "4000"))

    # PPR controls
    top_k: int = 200
    eps: float = 1e-6

    # Hierarchy weights
    w_parent_child: float = 1.0
    w_adjacent_sibling: float = 0.8

    # IDF clamps for term co-usage
    idf_min: float = 0.2
    idf_max: float = 2.0


def _row_normalize(adj: Dict[ProvisionId, Dict[ProvisionId, float]]) -> Dict[ProvisionId, List[Tuple[ProvisionId, float]]]:
    out = {}
    for u, nbrs in adj.items():
        s = sum(v for v in nbrs.values())
        if s <= 0:
            out[u] = [(u, 1.0)]
        else:
            out[u] = [(v, w/s) for v, w in nbrs.items()]
    return out


def _power_iteration_pagerank(
    adj_norm: Dict[ProvisionId, List[Tuple[ProvisionId, float]]],
    gamma: float,
    nodes: List[ProvisionId],
    iters: int = 50
) -> Dict[ProvisionId, float]:
    """
    Baseline PageRank-like vector with teleport (1-gamma).
    Works on row-normalized adjacency where edges are u->v with prob p(u->v).
    """
    N = len(nodes)
    idx = {n:i for i,n in enumerate(nodes)}
    r = [1.0/N]*N  # uniform start
    teleport_mass = (1.0 - gamma)/N
    for _ in range(iters):
        new_r = [teleport_mass]*N
        for u, nbrs in adj_norm.items():
            pu = r[idx[u]]
            if not nbrs:
                new_r[idx[u]] += gamma * pu
            else:
                for v, p in nbrs:
                    new_r[idx[v]] += gamma * pu * p
        r = new_r
    z = sum(r) or 1.0
    r = [x/z for x in r]
    return {n:r[idx[n]] for n in nodes}


def _approximate_ppr_push(
    adj_norm: Dict[ProvisionId, List[Tuple[ProvisionId, float]]],
    seed: ProvisionId,
    gamma: float,
    eps: float,
    top_k: int
) -> Tuple[List[Tuple[ProvisionId, float]], float]:
    """
    Andersen-Chung-Lang push (simplified).
    Residual r starts at seed=1. Push alpha*r[u] to ppr[u], distribute gamma*r[u] to neighbors.
    """
    alpha = 1.0 - gamma
    ppr = defaultdict(float)
    r = defaultdict(float)
    r[seed] = 1.0
    q = deque([seed])

    while q:
        u = q.popleft()
        ru = r[u]
        if ru < eps:
            continue
        ppr[u] += alpha * ru
        push = gamma * ru
        r[u] = 0.0
        nbrs = adj_norm.get(u, [(u,1.0)])
        for v, prob in nbrs:
            inc = push * prob
            if inc < eps:
                continue
            prev = r[v]
            newv = prev + inc
            r[v] = newv
            if prev < eps and newv >= eps:
                q.append(v)

    items = sorted(ppr.items(), key=lambda kv: kv[1], reverse=True)[:top_k]
    captured = sum(v for _, v in items)
    return items, captured


# ----------------- NEW: semantic helpers -----------------

def _prep_text_for_embedding(p: dict, max_chars: int) -> str:
    title = (p.get("title") or "").strip()
    body = (p.get("content_md") or "").strip()
    txt = f"{title}\n{body}".strip()
    if max_chars and len(txt) > max_chars:
        txt = txt[:max_chars]
    return txt


def _compute_embeddings(
    provisions_payload: List[dict],
    cfg: RelatednessIndexerConfig
) -> Tuple[List[ProvisionId] | None, "np.ndarray | None"]:
    """
    Returns (ids, embeddings) or (None, None) if deps unavailable.
    Embeddings are L2-normalized so dot == cosine.
    """
    if SentenceTransformer is None or np is None:
        logger.warning("Semantic view disabled: sentence-transformers or numpy not available.")
        return None, None

    ids = [p["internal_id"] for p in provisions_payload]
    texts = [_prep_text_for_embedding(p, cfg.max_text_chars) for p in provisions_payload]

    logger.info(f"Loading embedding model: {cfg.embedding_model_name}")
    model = SentenceTransformer(cfg.embedding_model_name)
    emb = model.encode(
        texts,
        batch_size=cfg.embedding_batch_size,
        normalize_embeddings=True,        # ensures cosine = dot
        show_progress_bar=False
    )
    emb = np.asarray(emb, dtype=np.float32)
    return ids, emb


def _build_semantic_knn(
    ids: List[ProvisionId],
    emb: "np.ndarray",
    k: int,
    min_cos: float,
    batch: int
) -> Dict[ProvisionId, Dict[ProvisionId, float]]:
    """
    Builds a sparse, symmetric k-NN graph using cosine similarity on normalized embeddings.
    We linearly rescale weights from [min_cos, 1] to [0, 1].
    """
    A_sem = defaultdict(lambda: defaultdict(float))
    if np is None:
        return A_sem

    N = len(ids)
    k_eff = max(1, min(k, max(1, N-1)))
    for i in range(0, N, batch):
        X = emb[i:i+batch]  # shape (b, d), already normalized
        sims = np.matmul(X, emb.T)  # (b, N), cosine scores in [-1, 1]
        for bi in range(sims.shape[0]):
            u_index = i + bi
            row = sims[bi]
            # exclude self
            row[u_index] = -1.0
            # get top-k candidates
            idxs = np.argpartition(-row, k_eff)[:k_eff]
            idxs = idxs[np.argsort(-row[idxs])]
            u = ids[u_index]
            for j in idxs:
                s = float(row[j])
                if s < min_cos:
                    continue
                v = ids[j]
                if v == u:
                    continue
                # rescale to [0,1]
                w = max(0.0, min(1.0, (s - min_cos) / (1.0 - min_cos)))
                # undirected (symmetric)
                if w > A_sem[u].get(v, 0.0):
                    A_sem[u][v] = w
                    A_sem[v][u] = w
    return A_sem

# ----------------- end semantic helpers -----------------


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
    parent_of: Dict[ProvisionId, ProvisionId|None] = {p["internal_id"]: p.get("parent_internal_id") for p in provisions_payload}
    siblings_by_parent: Dict[ProvisionId|None, List[Tuple[int, ProvisionId]]] = defaultdict(list)
    for p in provisions_payload:
        siblings_by_parent[p.get("parent_internal_id")].append((p.get("sibling_order", 0), p["internal_id"]))
    for k in siblings_by_parent:
        siblings_by_parent[k].sort(key=lambda x: (x[0] is None, x[0], x[1]))

    # 2) Build per-view adjacencies (raw weights)
    A_cit = defaultdict(lambda: defaultdict(float))    # directed
    for r in references_payload:
        u = r["source_internal_id"]
        v = r.get("target_internal_id")
        if not v or u == v or (u not in prov_set) or (v not in prov_set):
            continue
        A_cit[u][v] += 1.0

    A_h = defaultdict(lambda: defaultdict(float))      # undirected (add both directions)
    for v, p in parent_of.items():
        if p and p in prov_set and v in prov_set:
            A_h[v][p] += cfg.w_parent_child
            A_h[p][v] += cfg.w_parent_child
    for parent, ordered in siblings_by_parent.items():
        ids_sib = [vid for _, vid in ordered]
        for i in range(len(ids_sib)-1):
            a, b = ids_sib[i], ids_sib[i+1]
            A_h[a][b] += cfg.w_adjacent_sibling
            A_h[b][a] += cfg.w_adjacent_sibling

    # Term co-usage (P-P, symmetric) with IDF
    term_map = defaultdict(set)  # term_text -> set(provision_id)
    for t in defined_terms_usage_payload:
        u = t["source_internal_id"]
        if u in prov_set:
            term_map[t["term_text"].strip().lower()].add(u)

    A_t = defaultdict(lambda: defaultdict(float))
    for term, plist_set in term_map.items():
        plist = list(plist_set)
        df = max(1, len(plist))
        idf = 1.0 / math.log(1.0 + df)
        idf = max(cfg.idf_min, min(cfg.idf_max, idf))
        for i in range(len(plist)):
            ui = plist[i]
            for j in range(i+1, len(plist)):
                vj = plist[j]
                A_t[ui][vj] += idf
                A_t[vj][ui] += idf

    # --- NEW: Semantic view (A_sem) via embeddings + kNN ---
    A_sem = defaultdict(lambda: defaultdict(float))
    ids, emb = _compute_embeddings(provisions_payload, cfg)
    if ids and emb is not None and cfg.alpha_semantic > 0.0:
        A_sem = _build_semantic_knn(ids, emb, cfg.semantic_k, cfg.semantic_min_cos, cfg.knn_batch_size)
        logger.info("Semantic view: built ~%d undirected edges.",
                    sum(len(v) for v in A_sem.values()) // 2)
    else:
        logger.info("Semantic view unavailable or disabled; proceeding without it.")

    # 3) Aggregate & row-normalize
    A_raw = defaultdict(lambda: defaultdict(float))
    for u in prov_ids:
        for v,w in A_cit[u].items(): A_raw[u][v] += cfg.alpha_citation * w
        for v,w in A_h[u].items():   A_raw[u][v] += cfg.alpha_hierarchy * w
        for v,w in A_t[u].items():   A_raw[u][v] += cfg.alpha_term * w
        for v,w in A_sem[u].items(): A_raw[u][v] += cfg.alpha_semantic * w
        if not A_raw[u]:
            A_raw[u][u] += 1.0

    A_norm = _row_normalize(A_raw)

    # 4) Baseline PageRank-like vector (π) over provisions
    baseline_pi = _power_iteration_pagerank(A_norm, cfg.gamma, prov_ids, iters=50)

    # 5) Fingerprints (per provision seed)
    fingerprints = {}
    for seed in prov_ids:
        top_list, captured = _approximate_ppr_push(A_norm, seed, cfg.gamma, cfg.eps, cfg.top_k)
        neighbors = [{"prov_id": vid, "ppr_mass": float(m)} for vid, m in top_list]
        fingerprints[seed] = (neighbors, float(captured))

    return baseline_pi, fingerprints

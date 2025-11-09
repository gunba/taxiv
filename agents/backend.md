# Backend Architecture (Python)

## Stack

* **Language:** Python 3.11+
* **Framework:** FastAPI
* **Application Server:** Uvicorn
* **Database:** PostgreSQL with LTree and pgvector
* **ORM:** SQLAlchemy 2.0+
* **Validation:** Pydantic (FastAPI + Pydantic Settings)
* **Data Tooling:** NetworkX (graph analysis), python-docx (ingestion)
* **LLM Runtime:** google-generativeai (Gemini)
* **Embeddings:** Qwen/Qwen3-Embedding-0.6B (HF Transformers) persisted via pgvector for ANN
* **Environment:** Docker, Docker Compose, pip with `requirements.txt`

### System Dependencies

The ingestion pipeline rasterizes WMF/EMF assets on Linux. Ensure the backend container installs `imagemagick`,
`libreoffice-draw`, `ghostscript`, `libwmf-bin`, `librsvg2-bin`, and at least one TrueType font package (we ship
`fonts-dejavu-core`) via `Dockerfile.backend`. ImageMagick shells out to LibreOffice Draw to emit PDFs, Ghostscript
rasterizes those PDFs, and libwmf/librsvg cover the SVG fallback path. Running ingestion on bare metal requires the same
packages so WMF/EMF sources render to PNG correctly.

`Dockerfile.db` provisions PostgreSQL 16 with `postgresql-16-pgvector` preinstalled. If a container exits immediately
after `database files are incompatible with server`, drop the `taxiv_postgres_data` volume and allow PostgreSQL to
reinitialize under the new major version.

## Directory Structure

```
backend/
├── models/          # SQLAlchemy ORM models (database schema)
├── config.py        # Configuration surface (Pydantic Settings)
├── crud.py          # Database access layer
├── database.py      # Engine bootstrap + session management
├── main.py          # FastAPI entry point and route wiring
└── schemas.py       # Pydantic request/response shapes

ingest/
├── core/            # Shared ingestion logic (LLM, analysis, loading, utilities)
├── pipelines/       # Act-specific pipelines (e.g., itaa1997/)
├── cache/           # LLM cache (SQLite)
├── data/            # Raw source material (DOCX, etc.)
└── output/          # Intermediate and finalized artifacts
```

## Patterns

* **Data Ingestion**
	* Pipelines are partitioned per Act under `ingest/pipelines/[act_id]`.
	* Always execute ingestion via the backend container (`docker compose exec backend python -m ingest...`) so system packages and libraries (pgvector, ImageMagick, LibreOffice, etc.) are available; host-side runs will miss these dependencies unless you fully replicate the container environment.
	* Two-phase model:
		1. **Phase A — Parsing & Enrichment:** Parse raw inputs, normalize structure, run LLM enrichment with caching, and
		   emit intermediate JSON.
		2. **Phase B — Analysis & Loading:** Execute graph analysis, compute LTree paths, normalize references, and bulk
		   load into PostgreSQL.
	* `GraphAnalyzer` tracks root-level sibling order so multi-volume imports cannot regress chapter offsets.
	* Media extraction wipes each act/document media directory before parsing and derives PNG filenames from the source
	  metafile bytes to guarantee deterministic reruns.
	* WMF/EMF rasterization trims blank PDF canvases so stored PNGs exclude the 595×842 LibreOffice/Ghostscript padding.
	* Phase B reruns clear act-scoped `baseline_pagerank`, `relatedness_fingerprint`, and pgvector embeddings prior to
	  deleting provisions; reruns therefore avoid FK or unique-key thrash.
	* All LLM traffic must route through `ingest/core/llm_extraction.py` to leverage the cache.
	* Progress reporting lives in `ingest/core/progress.py`; set `INGEST_PROGRESS=0` (or `false`) to silence progress
	  bars in non-interactive environments.
	* Relatedness indexing logs the baseline PageRank sweep at info level so ingestion still shows forward motion even
	  with progress bars disabled.

* **Graph Relatedness & ANN**
	* Provision embeddings rely on the HF Qwen3 embedding models. `ingest/core/embedding_backend.py` wraps loading so we reuse
	  tokenizer/model instances, normalize outputs, and auto-select GPU (`cuda`) when available (falling back to CPU/MPS).
	* Provision embeddings write incrementally to the `embeddings` table (pgvector + HNSW) via
	  `ingest/core/relatedness_indexer.upsert_provision_embeddings`, which now feeds chunked text (2.2k char chunks / 350 char overlap by
	  default) through Qwen and averages normalized chunk vectors.
	* Unified semantic search relies on cached `relatedness_fingerprint` rows (see `backend/services/relatedness_engine.py`). After bumping the graph version or truncating fingerprints, the next query for each provision recomputes `_expand_local_subgraph` (citations, hierarchy, term co-usage, ANN neighbors) before writing the cache, which can make early searches take a few seconds until hot.
	* Always declare the operator class (`vector_l2_ops`) when creating pgvector HNSW indexes; PostgreSQL rejects the DDL
	  otherwise.
	* Run `python -m backend.manage_embeddings resize-vector --dim 1024` after pulling this change (or whenever switching embedding
	  dims). The command truncates embeddings, resizes the pgvector column, and recreates the HNSW index. Pass
	  `--skip-truncate` only if the table is already empty.
	* Configure embedding behavior via env vars (see `RelatednessIndexerConfig`) including `RELATEDNESS_EMBED_MODEL`,
	  `RELATEDNESS_EMBED_BATCH`, `RELATEDNESS_EMBED_DEVICE`, `RELATEDNESS_EMBED_MAX_LENGTH`, and chunk sizing knobs.
	* The ingestion pipeline computes only baseline PageRank. Personalized fingerprints are generated lazily via
	  `backend/services/relatedness_engine.py`.
	* `relatedness_fingerprint` rows carry a `graph_version`. Run `python -m backend.manage_graph bump-version` after
	  ingestion (or let the pipeline run it) to invalidate stale caches. Inspect the value with
	  `python -m backend.manage_graph show-version`.
	* Case-law and document chunks will share the same embedding + ANN infrastructure.
	* When binding pgvector values in raw SQL (e.g., `_semantic_neighbors`), wrap the parameter with
	  `bindparam("vec", type_=Embedding.__table__.c.vector.type)` so psycopg receives a pgvector payload instead of a
	  bare `numpy.ndarray`.

* **Markdown Export**
	* `backend/services/export_markdown.py` walks every descendant of the selected provision when
	  `include_descendants=True` and calls `crud.get_provision_detail` for each node, then repeats the same call for
	  every referenced or definition node it pulls into the bundle. Each detail call fans out into several queries
	  (references, defined terms, breadcrumbs, children, etc.), so exporting a large subtree can issue hundreds of SQL
	  trips before the markdown is assembled. The SideNav UI now avoids this path (it fetches a single provision via
	  `?format=markdown`), but MCP/automation flows that call `export_markdown_for_provision` should be prepared for
	  linear cost relative to descendant + reference + definition counts until we batch these lookups.
	* `/api/provisions/markdown_subtree` accepts a root provision plus the set of visible descendant IDs, orders them by
	  `hierarchy_path_ltree`, renders each node as a compact heading + `content_md`, and appends a deduped definitions
	  section. This keeps the SideNav copy-to-markdown button to one backend call even when entire chapters (with
	  definitions) are selected, while leaving the MCP markdown formatter untouched.

* **Database (LTree)**
	* `provisions.hierarchy_path_ltree` is the canonical representation for legislative hierarchy.
	* Paths follow `ActID.SanitizedLocalID1.SanitizedLocalID2...`, e.g., `ITAA1997.Chapter_1.Part_1_1.Division_10.10_5`.

* **API Design**
	* Keep routes RESTful.
	* Acquire database sessions via FastAPI dependency injection (`get_db`).
	* Centralize persistence logic inside `crud.py`.
	* `GET /api/provisions/detail/{internal_id}` accepts `?format=markdown` to return the exact MCP markdown surface (default remains JSON).

* **Type Hinting**
	* Enforce Python type hints throughout backend and ingestion code.

* **ORM Quirk**
	* SQLAlchemy reserves `metadata`. When using `backend.models.semantic.Document`, reference the `doc_metadata`
	  property (still mapped to the `metadata` column) to avoid declarative collisions.

## MCP Server (fastmcp)

* Run `docker compose up db backend mcp` to bring PostgreSQL, the backend, and the MCP server online. The MCP container
  expects `BACKEND_BASE_URL=http://backend:8000`.
* FastMCP only exposes SSE. Clients must connect to `http://localhost:8765/sse`. Hitting the root path yields a 404 and
  the handshake terminates.
	* Available tools:
		+ `semantic_search` wraps `POST /api/search/unified` and trims each hit to `{internal_id, ref_id, title, type,
		  score_urs}` so an LLM inspects headers before requesting detail.
		+ `provision_detail` wraps `GET /api/provisions/detail/{internal_id}` and returns the content, breadcrumbs, child
		  nodes, references, and definitions (including outbound references).
* Container-level smoke test:

	```python
	import asyncio
	from fastmcp import Client

	async def main():
		async with Client("http://127.0.0.1:8765/sse") as client:
			print([tool.name for tool in await client.list_tools()])
			resp = await client.call_tool("semantic_search", {"query": "s 6-5 ordinary income", "k": 3})
			print(resp.data[:400])
			detail = await client.call_tool("provision_detail", {"internal_id": "ITAA1997_Section_6-5", "format": "json"})
			print(detail.data[:400])

	asyncio.run(main())
	```

## Capacity Planning & Deployment

* **Qwen3 model footprint:** `ingest/core/embedding_backend.py` resolves CPU deployments to `torch.float32`, so loading `Qwen/Qwen3-Embedding-0.6B` consumes ~2.5 GB for weights plus another ~0.5 GB for tokenizer buffers and activations during inference. Budget at least 3 GB of resident RAM for the embedding worker alone, or pin it to GPU/MPS so the backend + DB can stay resident on CPU RAM.
* **4 vCPU / 8 GB boxes:** PostgreSQL with pgvector + HNSW typically sits around 2 GB once indexes are warm, while FastAPI + MCP stay under 1 GB combined. That leaves <2 GB headroom on an 8 GB VPS, so embedding bursts will force swapping unless you: (a) move Postgres to a managed service, (b) run embeddings in a separate worker (Celery/cron) container with a higher-memory plan, or (c) provision swap and accept slower ingestion.
* **Chunk throughput expectations:** Each provision/definition is chunked into ~2.2 k-character windows with 350-character overlap (`README.md` and `ingest/core/relatedness_indexer.py`). On CPU-only hosts, expect roughly 20–40 chunks/sec for Qwen3, so embedding a fresh act (or hundreds of lazy case-law documents) can take many minutes. Batch the lazy jobs and cap `RELATEDNESS_EMBED_BATCH` to 16–24 if you hit RAM ceilings; throughput drops linearly but keeps the worker alive.
* **Scaling case law:** 2 000 case PDFs averaging 8 k characters yield ~9 chunks/document (~18 000 total vectors). At 1024-dim pgvector entries that’s ~70 MB on disk, but HNSW indexes roughly double that, so plan for ~150 MB extra per 2 000 docs plus WAL overhead. Vacuum/analyze between large ingests so the ANN index stays balanced.
* **Latency targets:** Relatedness lookups already cache vectors in `_SEM_VECTOR_CACHE` (`backend/services/relatedness_engine.py`), so once embeddings exist, query latency is dominated by Postgres ANN search. Keep embeddings hot by pre-warming frequently accessed provisions after deploys, otherwise the first few lazily generated vectors will block search for several seconds while the HF backend spins up on CPU.
* **Backend concurrency:** `scripts/start-backend.sh` drives uvicorn with `${UVICORN_WORKERS:-4}` processes (dropping to a single `--reload` worker when `UVICORN_RELOAD=1`). Each worker uses the SQLAlchemy pool size defined by `DB_POOL_SIZE`/`DB_POOL_MAX_OVERFLOW`, so the default four-worker plan opens up to 80 Postgres connections—ensure the DB `max_connections` (set via compose to 200) remains above that ceiling.

	This verifies the abbreviated search payload and the enriched provision detail response (definitions plus references).

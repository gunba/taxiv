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
* **Embeddings:** sentence-transformers (`all-MiniLM-L6-v2` default) persisted via pgvector for ANN
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
	* Provision embeddings write incrementally to the `embeddings` table (pgvector + HNSW) via
	  `ingest/core/relatedness_indexer.upsert_provision_embeddings`.
	* Always declare the operator class (`vector_l2_ops`) when creating pgvector HNSW indexes; PostgreSQL rejects the DDL
	  otherwise.
	* The ingestion pipeline computes only baseline PageRank. Personalized fingerprints are generated lazily via
	  `backend/services/relatedness_engine.py`.
	* `relatedness_fingerprint` rows carry a `graph_version`. Run `python -m backend.manage_graph bump-version` after
	  ingestion (or let the pipeline run it) to invalidate stale caches. Inspect the value with
	  `python -m backend.manage_graph show-version`.
	* Case-law and document chunks will share the same embedding + ANN infrastructure.
	* When binding pgvector values in raw SQL (e.g., `_semantic_neighbors`), wrap the parameter with
	  `bindparam("vec", type_=Embedding.__table__.c.vector.type)` so psycopg receives a pgvector payload instead of a
	  bare `numpy.ndarray`.

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

	This verifies the abbreviated search payload and the enriched provision detail response (definitions plus references).

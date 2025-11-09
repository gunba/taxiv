# Backend Architecture (Python)

## Stack

* **Language:** Python 3.11+
* **Framework:** FastAPI
* **Server:** Uvicorn
* **Database:** PostgreSQL (with LTree + pgvector extensions)
* **ORM:** SQLAlchemy 2.0+
* **Data Validation:** Pydantic (via FastAPI and Pydantic Settings)
* **Data Processing/Analysis:** NetworkX (for graph analysis), python-docx (for ingestion)
* **LLM Integration:** google-generativeai (Gemini)
* **Semantic Embeddings:** sentence-transformers (default model `all-MiniLM-L6-v2`) persisted in pgvector for ANN lookup
* **Environment Management:** Docker, Docker Compose, pip/requirements.txt

### System Dependencies

The ingestion pipeline rasterizes WMF/EMF assets on Linux. The backend container must include `imagemagick`,
`libreoffice-draw`, `ghostscript`, `libwmf-bin`, `librsvg2-bin`, and at least one TrueType font package (we ship
`fonts-dejavu-core`) installed in `Dockerfile.backend`. ImageMagick shells out to LibreOffice Draw to produce PDFs,
Ghostscript rasterizes those PDFs, and libwmf/rsvg handle the SVG fallback path. If you run ingestion outside Docker,
install the equivalent packages on your host first so WMF/EMF assets can be converted to PNG. The Postgres service is
built from `Dockerfile.db`, which installs `postgresql-16-pgvector` so ANN queries are guaranteed to work without manual
extension management. If the container exits with `database files are incompatible with server` immediately after a
version bump, delete the `taxiv_postgres_data` Docker volume so PostgreSQL can reinitialize with the correct major
version.

## Directory Structure

```

backend/
├── models/          \# SQLAlchemy ORM models (Database Schema)
├── config.py        \# Configuration management (Pydantic Settings)
├── crud.py          \# Database interaction logic (Queries)
├── database.py      \# Engine initialization and session management
├── main.py          \# FastAPI application entry point and routes
└── schemas.py       \# Pydantic models (API Request/Response validation)

ingest/
├── core/            \# Shared ingestion logic (LLM, Analysis, Loading, Utils)
├── pipelines/       \# Act-specific ingestion implementations (e.g., itaa1997/)
├── cache/           \# LLM cache (SQLite)
├── data/            \# Raw input data (e.g., DOCX files)
└── output/          \# Intermediate and final processed output

```

## Patterns

* **Data Ingestion:**
	* Pipelines are modularized by Act (`ingest/pipelines/[act_id]`).
	* Ingestion follows a two-phase approach:
		1. **Phase A (Parsing & Enrichment):** Raw data is parsed, structured, and enriched using LLM (with caching).
		   Output is intermediate JSON.
		2. **Phase B (Analysis & Loading):** Intermediate JSON is analyzed (graph analysis, LTree calculation, reference
		   normalization) and bulk loaded into PostgreSQL.
	* GraphAnalyzer maintains a root-level sibling counter so multi-volume imports cannot accidentally reset
	  `sibling_order` for top-level provisions; callers do not need to manually offset chapter indexes between batches.
	* Media extraction now wipes the act/document media directory at the start of parsing and derives PNG filenames from
	  the source metafile bytes (not the rasterized output) so reruns regenerate assets without producing duplicate PNGs.
* WMF/EMF rasterization output is auto-trimmed after conversion so the stored PNGs do not retain the blank 595x842 PDF
  canvas that libreoffice/ghostscript introduces.
    * Phase B reruns now clear act-scoped `baseline_pagerank`, `relatedness_fingerprint`, and pgvector embeddings before deleting provisions, so rerunning the loader is safe and won’t hit FK/unique violations.
    * LLM interactions MUST use `ingest/core/llm_extraction.py` to utilize the cache.
    * Progress reporting across ingestion phases is handled via `ingest/core/progress.py`; set the `INGEST_PROGRESS`
      environment variable to `0`/`false` to disable progress bars in non-interactive environments.
    * Relatedness indexing emits info-level logs around the baseline PageRank run so ingestion logs continue to show
      progress even when progress bars are hidden.
* **Graph Relatedness & ANN:**
	* Provision embeddings are upserted incrementally into the `embeddings` table (pgvector with HNSW index) via
	  `ingest/core/relatedness_indexer.upsert_provision_embeddings`.
	* When defining pgvector HNSW indexes, always specify the operator class (`vector_l2_ops` for our MiniLM embeddings) or PostgreSQL will reject the DDL.
	* The ingestion pipeline now computes only the baseline PageRank; Personalized PageRank fingerprints are computed
	  lazily at query time through `backend/services/relatedness_engine.py`.
	* `relatedness_fingerprint` rows are cached per provision with a `graph_version`. Bump the version after ingestion
	  using `python -m backend.manage_graph bump-version` (or let the pipeline do it automatically) to invalidate stale
	  caches. Use `python -m backend.manage_graph show-version` to inspect the current value.
	* Case law / document chunks will reuse the same embeddings + ANN infrastructure once ingested.
	* When running raw SQL that binds a pgvector value (e.g., `_semantic_neighbors`), bind the `:vec` parameter with
	  `bindparam("vec", type_=Embedding.__table__.c.vector.type)` so SQLAlchemy hands psycopg a pgvector-compatible
	  payload instead of a bare `numpy.ndarray` (which triggers `can't adapt type 'numpy.ndarray'`).
* **Database (LTree):**
    * The `provisions.hierarchy_path_ltree` column is the primary mechanism for organizing the legislative hierarchy.
    * The path format is `ActID.SanitizedLocalID1.SanitizedLocalID2...` (e.g.,
      `ITAA1997.Chapter_1.Part_1_1.Division_10.10_5`).
* **API Design:** Adhere to RESTful principles. Use FastAPI dependency injection (`get_db`) for database sessions. Logic
  resides in `crud.py`.
* **Type Hinting:** Utilize Python type hints strictly throughout the backend and ingestion code.
* **ORM Quirks:** SQLAlchemy reserves the attribute name `metadata`. When working with `backend.models.semantic.Document`, use the `doc_metadata` attribute (it still maps to the `metadata` column) to avoid Declarative collisions.

## MCP Server (fastmcp)

* Start `db`, `backend`, and `mcp` together via `docker compose up db backend mcp`; the MCP container assumes
  `BACKEND_BASE_URL=http://backend:8000`.
* The FastMCP server only exposes an SSE transport, so clients must connect to `http://localhost:8765/sse` (note the `/sse`
  suffix). Pointing a client at the root URL returns a 404 and the handshake fails with “Session terminated.”
* The server exposes two tools:
	+ `semantic_search` — wraps `POST /api/search/unified` but trims each hit to `{internal_id, ref_id, title, type, score_urs}` so the LLM only sees headers until it opts to drill down.
	+ `provision_detail` — wraps `GET /api/provisions/detail/{internal_id}` and includes content, breadcrumbs, children, references, plus every definition (each bundled with its outbound references).
* Quick smoke test from inside the container:

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

	This validates the search headers and the enriched provision detail payload (including definitions and references).

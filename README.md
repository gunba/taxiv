# Taxiv: Tax Code Explorer

https://raja-block.bnr.la

![Taxiv application screenshot](./assets/taxiv-screenshot.png)

A modern, interactive web application for browsing, analyzing, and understanding Australian tax legislation. This
project utilizes a sophisticated ingestion pipeline (Python, Gemini, NetworkX) to process legislation documents into a
structured database (PostgreSQL with LTree), served via a backend API (FastAPI) and visualized with a dynamic frontend (
React/TypeScript).

## Architecture

The project is structured as a multi-service application managed by Docker Compose:

* **Frontend (React/Vite):** A dynamic interface for navigating the tax code hierarchy.
* **Backend (FastAPI):** Serves the legislation data and handles API requests.
* **Database (PostgreSQL):** Stores the structured legislation, utilizing the `ltree` + `pgvector` extensions (the custom
  `Dockerfile.db` installs `postgresql-16-pgvector` so ANN search is available out of the box).
* **Ingestion (Python/Gemini):** A modular pipeline located in the `ingest/` directory for processing raw legislation
  documents.

## Setup and Running Locally

**Prerequisites:**

* Docker and Docker Compose
* A Google Gemini API Key (for the ingestion process)

### 1. Configuration

1. Clone the repository.
2. Ensure the `.env` file exists in the project root (refer to the provided `.env` structure).
3. **Set your `GOOGLE_CLOUD_API_KEY`** in the `.env` file.

### Backend Concurrency Configuration

The backend container now starts Uvicorn with four workers by default so a 4‑core VPS can service multiple simultaneous
queries. Adjust concurrency via environment variables:

| Variable | Default | Description |
| --- | --- | --- |
| `UVICORN_WORKERS` | `4` | Number of worker processes (ignored when reload mode enabled). |
| `UVICORN_RELOAD` | `0` | Set to `1` for local development hot reload; forces a single worker. |
| `DB_POOL_SIZE` | `10` | SQLAlchemy pool per worker. |
| `DB_POOL_MAX_OVERFLOW` | `10` | Burst connections per worker. |
| `DB_POOL_TIMEOUT` | `30` | Seconds to wait for a pooled connection. |

PostgreSQL runs with `max_connections=200` and `shared_buffers=512MB` by default in `docker-compose.yml`, which leaves
enough headroom for the four-worker layout plus tooling.

### 2. Start the Infrastructure

From the project root, build and start the containers (this compiles the custom Postgres image with `pgvector` support):

```bash
docker-compose up --build -d
````

Verify the services are running. Ensure the `taxiv_db` service status eventually shows `(healthy)`.

```bash
docker-compose ps
```

### 3. Data Ingestion

To use the application, you must first ingest the legislation data.

**A. Place Input Files**

Place the raw DOCX files for the legislation into the corresponding data directory. For ITAA1997:

```
ingest/data/itaa1997/
    C2025C00405VOL01.docx
    ...
    C2025C00405VOL10.docx
```

**B. Run the Pipeline**

Execute the ingestion pipeline inside the running `backend` container. This process involves parsing the documents (
Phase A) and then analyzing/loading them into the database (Phase B).

```bash
docker-compose exec backend python -m ingest.pipelines.itaa1997.run_pipeline
```

> **Linux WMF/EMF note:** The ingestion pipeline now rasterizes Windows Metafile assets on Linux. Install
> `imagemagick`, `libwmf-bin`, and `librsvg2-bin` (or equivalent packages for your distribution) inside the backend
> environment so WMF/EMF images can be converted to PNG during parsing. The default `Dockerfile.backend` now installs
> these packages automatically; add them manually only if you run the ingestion pipeline outside that container.

This process may take time. Subsequent runs will be faster due to LLM caching (`ingest/cache/llm_cache.db`).

### Multi-Act + Document Datasets

Available acts and document datasets are declared in `backend/datasets.json`. Each entry defines exclusions, ingest
pipelines, and (for documents) the input directory. To onboard a new act, add an entry to the `acts` array, point the
`ingestion.pipeline` field at the implementing module, and run that module via
`docker compose exec backend python -m ingest.pipelines.<act>.run_pipeline`.

Case files, rulings, and other standalone documents live in datasets. Populate `ingest/data/documents/<dataset>` with
JSON/Markdown files (see `backend/datasets.json` for the expected folder) and run:

```bash
docker compose exec backend python -m ingest.pipelines.documents.run_pipeline
```

The script normalizes content into the `documents`/`document_chunks` tables so search, embeddings, and downstream tools
can treat them alongside acts.

### Embeddings & pgvector

Provision embeddings now rely on Hugging Face's `Qwen/Qwen3-Embedding-0.6B` model via Transformers/Torch. The ingestion
pipeline encodes provision/definition chunks (~2.2k characters with a 350-character overlap) and averages the normalized
chunk vectors before upserting them into the `embeddings` pgvector table. The backend queries the same vectors for
semantic neighbors. After pulling this change (or whenever switching embedding dimensions) run:

```bash
docker compose exec backend python -m backend.manage_embeddings resize-vector --dim 1024
```

This truncates the embeddings table, resizes the pgvector column to 1024 dimensions, and recreates the HNSW index so the
next ingestion pass can repopulate it. Use `RELATEDNESS_EMBED_*` env vars (see `ingest/core/relatedness_indexer.py`) to
override the model id, device pinning, batch size, context window, or chunk sizes.

## Search Performance Notes

* Personalized fingerprints are now computed during ingestion and saved into `relatedness_fingerprint`, so run the Phase
  B pipeline whenever legislation content changes to refresh graph caches.
* Unified search caches full responses (keyed by query, `k`, and `graph_version`) for 10 minutes and hard-caps lexical
  seeds to avoid redundant PPR solves.
* Section 995 (the definitions container) still ingests but is excluded from ranking/relatedness to keep search
  results useful—users can open it directly via navigation if required.

### MCP + Backend API Enhancements

* `/capabilities` (backend) now advertises the available Acts and default scope so MCP clients can confirm coverage
  before issuing queries. The MCP server exposes a matching `capabilities()` tool that returns the same metadata.
* `/api/search/unified` accepts an `offset` for pagination (default `k=10`). Responses include pagination metadata
  (`offset`, `limit`, `next_offset`, `total`) plus a normalized `parsed` object when flexible section tokens (for example,
  `"s 6-5"` or `"sec 6.5"`) are detected.
* `/api/provisions/detail/{internal_id}` defaults to a lean payload and supports optional expansions via
  `include_breadcrumbs`, `include_children`, `include_definitions`, and `include_references`. Clients can request a
  subset of fields with `fields=[...]`, and every response now includes caching metadata (`etag`, `last_modified`,
  `size_bytes`) along with any normalized `parsed` token.
* `/api/batch_provisions` mirrors the detail flags and hydrates multiple provisions in a single round trip—ideal for
  MCP workflows that need to expand several hits at once.
* Flexible token parsing (`s 6-5`, `sec 6.5`, `6 5`) normalizes to canonical sections and echoes the structured parse in
  both search and detail responses so downstream agents can confirm which provision was resolved.

### 4\. Access the Application

* **Frontend:** `http://localhost:3000`
* **Backend API Docs (Swagger):** `http://localhost:8000/docs`

## Development Workflow

The Docker Compose setup enables live reloading for both the frontend (Vite HMR) and the backend (Uvicorn reload).
Changes made to the source code will be reflected automatically.

## Running Tests Locally

You can execute both the Vitest (React) suite and the Python (FastAPI + ingest) suites directly on your host—no
containers required.

1. Install Node dependencies: `npm install`.
2. (Recommended) Create a virtual environment, then install Python dev dependencies:
   ```bash
   python -m venv .venv && source .venv/bin/activate
   pip install -r requirements-dev.txt
   ```
3. Run every test suite via `scripts/run-tests.sh`. The script fails fast if either stack reports a failure and accepts
   additional arguments that are passed through to `pytest`, e.g. `scripts/run-tests.sh -k media`.

Individual commands:

* Frontend only: `npm run test:frontend` (or `npm run test:frontend:watch` for interactive runs).
* Python suites only: `npm run test:python` (alias for `pytest tests/backend tests/ingest`).

If you encounter missing system libraries (e.g., ImageMagick for ingestion media tests), install the same packages the
backend container uses (see `Dockerfile.backend`) so rasterization helpers can invoke the expected binaries.

## SideNav Markdown Copy

The SideNav shows a clipboard button when you hover over (or keyboard-focus) a provision row. The control now copies
*only the selected provision* by calling `GET /api/provisions/detail/{id}?format=markdown`, which returns pre-rendered
markdown for that node alone. This keeps the interaction fast even when you start from chapters that contain hundreds of
descendants.

When you click the button:

1. The UI fetches the markdown for the selected provision.
2. The payload is written to the clipboard via the standard `navigator.clipboard.writeText` gesture.
3. A toast confirms success (or surfaces an error if the clipboard or network request fails). There is no longer an
   inline status message anchored to the navigation row.

If you need a hierarchical export (provision + descendants + referenced nodes + definitions), call
`POST /api/provisions/export_markdown` directly or reuse the backend service at
`backend/services/export_markdown.py`. That endpoint still assembles the full subtree bundle for MCP and other tooling,
but it is intentionally heavyweight and no longer powers the SideNav button.

### Troubleshooting

* **Clipboard permission denied:** Confirm the page is loaded over HTTPS (or `localhost`) and that the user initiated
  the export via a direct interaction. Browsers may require reloading the page after updating clipboard settings.
* **Markdown request fails:** Ensure the backend `/api/provisions/detail/{id}?format=markdown` route is reachable and
  that the provision exists.
* **Need hierarchical exports:** Use the `POST /api/provisions/export_markdown` endpoint or call the helper in
  `backend/services/export_markdown.py` directly inside backend/MCP workflows.

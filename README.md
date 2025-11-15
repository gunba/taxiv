# Taxiv: Tax Code Explorer

https://raja-block.bnr.la

![Taxiv application screenshot](./assets/taxiv-screenshot.png)

Taxiv is a web application for browsing and understanding Australian tax legislation. It ingests raw legislative
documents into PostgreSQL and exposes them via a FastAPI backend and a React/Vite frontend.

## Architecture (High Level)

Services are managed via Docker Compose:

- **Frontend (`frontend/`, React/Vite):** UI for navigating the act hierarchy, viewing provisions, and running semantic search.
- **Backend (`backend/`, FastAPI):** HTTP API over the ingested legislation, semantic search, and related services.
- **Database (PostgreSQL + LTree + pgvector):** Stores provisions, relationships, and embeddings.
- **Ingestion (`ingest/`, Python):** Pipelines that parse DOCX/RTF inputs, normalize structure, and load data into the database.

For implementation details (search, embeddings, MCP, SideNav behavior), see the agent guides under `agents/guides/` and the backend/ingestion docs rather than this README.

## Getting Started

### Prerequisites

- Docker and Docker Compose
- A Google Gemini API key (for ingestion)

### 1. Configure Environment

1. Clone the repository.
2. Create a `.env` file in the project root (based on your existing deployment or `.env` template).
3. Set `GOOGLE_CLOUD_API_KEY` (and database credentials if you are not using the defaults).

### 2. Start the Stack

From the repo root:

```bash
docker-compose up --build -d
```

Verify services:

```bash
docker-compose ps
```

- Frontend: http://localhost:3000
- Backend API docs (Swagger): http://localhost:8000/docs

## Ingesting Legislation

Before the UI shows useful data, you must ingest at least one act.

### Place Input Files

For ITAA1997, place DOCX files under:

```bash
ingest/data/itaa1997/
    C2025C00405VOL01.docx
    ...
    C2025C00405VOL10.docx
```

Available acts and document datasets are declared in `backend/datasets.json`. Each entry specifies how to ingest that dataset.

### Run the Pipeline (Inside Backend Container)

```bash
docker-compose exec backend python -m ingest.pipelines.itaa1997.run_pipeline
```

For document datasets (e.g., case law), populate `ingest/data/documents/<dataset>` as configured in `backend/datasets.json` and run:

```bash
docker compose exec backend python -m ingest.pipelines.documents.run_pipeline
```

The ingestion docs under `agents/guides/backend.md` and the ingestion tests under `tests/ingestion/` are the source of truth for advanced ingestion behavior (media handling, embeddings, graph analysis).

## Development & Testing

### Local Development (Host Tools)

1. Install Node dependencies:

   ```bash
   npm install
   ```

2. (Recommended) Create a Python virtualenv and install dev requirements:

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements-dev.txt
   ```

### Running Tests

- Frontend (Vitest):

  ```bash
  npm run test:frontend
  # or
  npm run test:frontend:watch
  ```

- Backend + ingestion (Pytest):

  ```bash
  npm run test:python
  # alias for: pytest tests/backend tests/ingestion
  ```

- Full-stack test harness (frontend + backend + ingestion):

  ```bash
  scripts/run-tests.sh
  ```

Some ingestion tests exercise media/embedding paths and may require system packages (ImageMagick, LibreOffice, etc.) matching `Dockerfile.backend`.

## Further Documentation

- **Agent/developer guides:** `agents/guides/frontend.md`, `agents/guides/backend.md`, `agents/guides/testing.md`
- **Best practices & repo layout:** `agents/best_practices.md`
- **Deployment details:** `agents/deployment.md`
- **Change history:** `agents/changelogs/*.md`

If you are extending search, MCP tooling, SideNav export, or ingestion internals, start with the relevant guide under `agents/` rather than this README.


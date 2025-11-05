# Taxiv: Tax Code Explorer

A modern, interactive web application for browsing, analyzing, and understanding Australian tax legislation. This
project utilizes a sophisticated ingestion pipeline (Python, Gemini, NetworkX) to process legislation documents into a
structured database (PostgreSQL with LTree), served via a backend API (FastAPI) and visualized with a dynamic frontend (
React/TypeScript).

## Architecture

The project is structured as a multi-service application managed by Docker Compose:

* **Frontend (React/Vite):** A dynamic interface for navigating the tax code hierarchy.
* **Backend (FastAPI):** Serves the legislation data and handles API requests.
* **Database (PostgreSQL):** Stores the structured legislation, utilizing the `ltree` extension for efficient hierarchy
  management.
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

### 2. Start the Infrastructure

From the project root, build and start the containers:

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

This process may take time. Subsequent runs will be faster due to LLM caching (`ingest/cache/llm_cache.db`).

### 4\. Access the Application

* **Frontend:** `http://localhost:3000`
* **Backend API Docs (Swagger):** `http://localhost:8000/docs`

## Development Workflow

The Docker Compose setup enables live reloading for both the frontend (Vite HMR) and the backend (Uvicorn reload).
Changes made to the source code will be reflected automatically.

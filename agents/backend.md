# Backend Architecture (Python)

## Stack

* **Language:** Python 3.11+
* **Framework:** FastAPI
* **Server:** Uvicorn
* **Database:** PostgreSQL (with LTree extension)
* **ORM:** SQLAlchemy 2.0+
* **Data Validation:** Pydantic (via FastAPI and Pydantic Settings)
* **Data Processing/Analysis:** NetworkX (for graph analysis), python-docx (for ingestion)
* **LLM Integration:** google-generativeai (Gemini)
* **Semantic Embeddings:** sentence-transformers (default model `all-MiniLM-L6-v2`) for relatedness graph kNN
* **Environment Management:** Docker, Docker Compose, pip/requirements.txt

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
    * LLM interactions MUST use `ingest/core/llm_extraction.py` to utilize the cache.
* **Database (LTree):**
    * The `provisions.hierarchy_path_ltree` column is the primary mechanism for organizing the legislative hierarchy.
    * The path format is `ActID.SanitizedLocalID1.SanitizedLocalID2...` (e.g.,
      `ITAA1997.Chapter_1.Part_1_1.Division_10.10_5`).
* **API Design:** Adhere to RESTful principles. Use FastAPI dependency injection (`get_db`) for database sessions. Logic
  resides in `crud.py`.
* **Type Hinting:** Utilize Python type hints strictly throughout the backend and ingestion code.

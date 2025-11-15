## Ingestion Changelog (Pipelines / Media)

Use this file for changes primarily affecting ingestion (`ingest/` and `tests/ingest/`), including DOCX/RTF parsing, graph analysis, and embedding/indexing behavior.

2025-11-15 - Updated the documents ingestion pipeline to resolve backend/datasets.json via backend.act_metadata, keeping dataset input-dir resolution in sync with the backend while reorganizing the repo layout.


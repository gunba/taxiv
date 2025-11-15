## Backend Changelog (FastAPI / Core API)

Use this file for changes primarily affecting the backend (`backend/` and `tests/backend/`), including FastAPI routes, services, and database-related logic.

2025-11-15 - Relocated datasets config to backend/datasets.json, added a shared resolver for ingestion, and kept /api/acts stable so the frontend Act selector can bootstrap even after the layout cleanup.
2025-11-15 - Trimmed backend/search/MCP implementation details out of README.md and pointed contributors to the backend and ingestion guides under agents/guides/ for low-level behavior.

## Backend Changelog (FastAPI / Core API)

Use this file for changes primarily affecting the backend (`backend/` and `tests/backend/`), including FastAPI routes, services, and database-related logic.

2025-11-15 - Relocated datasets config to backend/datasets.json, added a shared resolver for ingestion, and kept /api/acts stable so the frontend Act selector can bootstrap even after the layout cleanup.
2025-11-15 - Trimmed backend/search/MCP implementation details out of README.md and pointed contributors to the backend and ingestion guides under agents/guides/ for low-level behavior.
2025-11-15 - Updated crud.get_hierarchy to filter out Definition-type provisions from /api/provisions/hierarchy/{act_id} so long definition lists (e.g. ITAA 1936 s 6, ITAA 1997 s 995-1) only appear inside their interpretation sections and in the right-hand detail view, while leaving search_hierarchy unchanged so definitions can still be surfaced directly by hierarchy search.

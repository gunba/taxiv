## Frontend Changelog (React/Vite)

Use this file for changes primarily affecting the frontend (`frontend/` and `tests/frontend/`), including UI, TypeScript, and Vitest suites.

2025-11-15 - Centralized frontend tests under tests/frontend/**, aligned Vitest config and TypeScript paths with the new structure, moved the Taxiv logo into frontend/assets, renamed the entrypoint to main.tsx, and confirmed the localhost:3000 UI works against the updated backend config.
2025-11-15 - Simplified README.md into a user-facing overview (what Taxiv is, how to run it, how to ingest data, and how to run tests) and moved UI/search/SideNav/MCP implementation details into the agents guides.
2025-11-15 - Reworked InteractiveContent mid-provision lazy rendering to use an explicit “Load more of this provision” button instead of an IntersectionObserver sentinel, and updated MainContent to drive provision-level lazy loading from scroll position in the `main` container, so long provisions (e.g. ITAA 1936 s 6, ITAA 1997 s 995) no longer cause scroll-position drift while users can still scroll past them and progressively load additional provisions.
2025-11-15 - Extended InteractiveContent enumeration indentation heuristics so ITAA-style markers like `(1A)` and `(aa)/(ab)` align with existing `(1)`, `(a)`, and `(i)` patterns, and added Vitest coverage for the new marker handling.

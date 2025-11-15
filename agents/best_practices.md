# General Best Practices

* Prefer tab indentation to minimize file size and token overhead.
* Keep every function narrowly scoped to a single responsibility.
* When naming things (files, functions, variables, etc.), choose simple names that explicitly state the purpose or intent rather than "standard industry terminology".
* Treat the codebase as production-facing: threat-model input, sanitize outputs, and avoid leaking secrets.
* Only add error handling for issues that are likely to actually occur.

## Repository Layout & Containers

* **Frontend container (`frontend`)**
	* React/Vite app under `frontend/` (`App.tsx`, `main.tsx`, `index.html`) with Vite/Vitest config and `package.json` at the repo root.
	* UI components and hooks under `frontend/components/` plus supporting helpers in `frontend/utils/` and shared types in `frontend/types.ts`.
	* Frontend tests live under `tests/frontend/**` (Vitest), mirroring the frontend structure.
* **Backend container (`backend`)**
	* FastAPI application and ORM under `backend/`.
	* Backend tests under `tests/backend/` (Pytest).
* **Ingestion runtime (`backend` + `ingest`)**
	* Ingestion pipelines and shared logic under `ingest/`.
	* Ingestion tests under `tests/ingestion/` (Pytest).
* **MCP server (`mcp_server`)**
	* FastMCP adapter and formatter under `mcp_server/`.

Ephemeral, non-ingestion artifacts must never be committed:

* Keep `dist/`, `node_modules/`, caches (`.pytest_cache/`, `__pycache__/`), IDE metadata (`.idea/`), and agent tooling state (e.g., `.serena/`) out of git via `.gitignore`.
* Ingestion outputs and media (`ingest/output/**/*`, `ingest/media/**/*`) are allowed locally but are excluded from version control.

## Post-Work Checklist for Agents

Before handing any task back to the user, always:

1. **Repo layout:** Ensure any structural changes (new/moved/deleted files or folders) are reflected in the agents docs (this file or a more specific guide).
2. **Ephemeral cleanup:** Delete non-ingestion, non-database ephemeral artifacts you created (temp dirs, scratch files, one-off scripts) and confirm they are ignored by `.gitignore`.
3. **Code quality:** Inspect touched code paths for dead or unused logic and remove it when safe.
4. **Documentation:** Update relevant docs (`README.md`, `agents/*.md`, or feature-specific docs) to match the new behavior and structure.
5. **Changelog:** Append a single-line summary of the work to the relevant `agents/changelogs/*.md` file(s) for the services you touched.
6. **Tests:** Run the impacted test suites (`npm run test:frontend`, `npm run test:python`, or `scripts/run-tests.sh`) and capture outcomes in your final handoff.

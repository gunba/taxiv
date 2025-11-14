# Testing Standards

Every change must be testable and ship with the relevant coverage.

## General Principles

* Keep tests isolated and deterministic.
* Follow an explicit Arrange → Act → Assert structure.
* Name tests after the observable behavior under scrutiny.

## Frontend Testing

* **Framework:** Vitest
* **Library:** React Testing Library (RTL)
* **Priorities:**
	1. Validate user interactions and component behavior through RTL. Avoid white-box assertions.
	2. Unit test complex business logic, utility helpers, and custom hooks.
* **Mocking:** Isolate network calls via MSW or targeted `jest.mock` shims.

## Backend Testing

* **Framework:** Pytest
* **Priorities:**
	1. Unit test processors, services, and other data-manipulation modules.
	2. Exercise API endpoints with integration tests where behavior spans layers.
* **Fixtures:** Use Pytest fixtures to manage setup/teardown efficiently.
* **Parametrization:** Prefer `pytest.mark.parametrize` for combinatorial input coverage.
* **Mocking:** Stub external services and heavyweight dependencies to keep the suite fast.

## Execution Checklist

* Run the suites that cover the code you touched before handing work back:
	* Frontend or shared TypeScript changes → `npm run test:frontend` (use `npm run test:frontend:watch` while iterating).
	* Backend/ingest Python changes → `npm run test:python` (`pytest tests/backend tests/ingest` under the hood).
	* Full-stack edits → `scripts/run-tests.sh` to execute both stacks sequentially.
* Capture the command output (pass/fail) in your final response. If a suite cannot run locally, document the blocker and
  the mitigation you attempted (e.g., missing system dependency, sandbox restriction).
* When adding new behavior, extend or author tests in the same change so the regression surface grows alongside the
  feature.

## Playwright MCP UI Smoke Tests

* Use the Playwright MCP tools when you need an end-to-end sanity check of the running UI (especially around semantic search or act selection) instead of relying solely on unit tests.
* Typical workflow:
	* Ensure the frontend (Vite) and backend (FastAPI) are running and reachable on the host (in the current setup, `http://localhost:3000` serves the UI with the backend proxy).
	* From the MCP-enabled environment, use the `playwright` tools to:
		1. Navigate to the Taxiv UI.
		2. Select an Act in the header selector (e.g., ITAA1936).
		3. Open the semantic search modal, run a query (e.g., "medicare levy"), and confirm that:
			* The modal header reflects the selected scope (current Act vs. All Acts).
			* Result rows show the mapped Act label (e.g., “Income Tax Assessment Act 1936”) and URS scores.
			* Clicking a row loads the provision into the main view without errors.
* Prefer Playwright MCP for quick, behavior-centric smoke tests after wiring new UI flows (like multi-act semantic search), and still back changes with Vitest/Pytest at the unit/integration level.

# AI Agent Management System

This document defines the operational protocols, roles (Agents), and workflows for all AI interactions (that's you!) within the Taxiv project.

## 1. Guiding Principles

You are an expert full-stack developer (React/TypeScript Frontend, Python/FastAPI Backend, PostgreSQL Database). However, your memory is volatile. You must rely on the externalized state management system defined here.

1.  **Plan First:** No implementation code shall be written without an approved plan.
2.  **Externalize State:** Maintain the current task status in the `dev/active/[task-name]/` directory (Note: AI Agents should create `dev/active/` directories if they don't exist).
3.  **Adhere to Standards:** Follow the standards defined in the `standards` directory.
4.  **Iterate and Review:** Work in small steps and utilize the Quality Control agents frequently.
5.  **Use the Infrastructure:** All development, testing, and ingestion must utilize the "docker compose" (not "docker-compose") environment to ensure consistency.

## 2. The Dev Docs Workflow (Externalized State)

Templates:
`standards\templates\plan.md`. - A template for the plan itself.
`standards\templates\context.md`. - A template for plan and execution context.
`standards\templates\tasks.md` - A template for a checklist based on the plan.

### 2.1. Initialization (The Strategic Architect)

1.  **User Defines Goal:** The user provides a high-level objective.
2.  **Activate Strategic Architect:** Analyze the request, research the codebase, and identify affected components.
3.  **Generate Plan:** Propose a detailed implementation plan using the `plan` template.
4.  **Human Review:** The user MUST review and approve the plan. Iterate until approved.

### 2.2. Execution Setup

Once the plan is approved:
1.  **Create Task Directory:** `mkdir -p dev/active/[task-name]/`
2.  **Instantiate Dev Docs:**
    *   Save the approved plan as `[task-name]-plan.md`.
    *   Create `[task-name]-context.md` (using the `context` template,  add initial relevant files/snippets).
    *   Create `[task-name]-tasks.md` (using the `tasks` template, convert the plan's steps into this checklist).

### 2.3. Implementation Loop

1.  **Load Context:** Before starting work, read all three Dev Docs files.
2.  **Execute Step:** Implement ONE or TWO tasks from the checklist at a time.
3.  **Validate:** Run necessary builds/linters/tests. Fix errors immediately.
4.  **Review (Optional but Recommended):** Activate the Code Reviewer Agent to check the changes against guidelines and the plan.
5.  **Update State:**
    *   Update `[task-name]-tasks.md` by marking completed items.
    *   Update `[task-name]-context.md` with key decisions, challenges, or newly relevant code snippets.

### 2.4. Pausing/Context Clearing

If the context window is full or work is pausing:
1.  **Final State Update:** Ensure the Dev Docs are completely up-to-date.
2.  **Next Steps:** Explicitly write the immediate next action in `[task-name]-context.md`.
3.  **Resume:** To continue, start a fresh session, load the Dev Docs, and proceed with the "Next Steps".

## 3. Agent Roles

When instructed to adopt a role, utilize the specialized focus described below. If not instructed to do so, however the role seems highly appropriate to the query, adopt it anyway.

### 3.1. Strategic Architect (Planning)

* **Focus:** High-level planning, codebase research, architectural design (e.g., new database schemas using SQLAlchemy/LTree, API design with FastAPI, ingestion pipeline modularization).
* **Output:** Detailed implementation plans (`plan.md`).
* **Method:** Analyze dependencies, define phases, design data models, and structure the approach before writing implementation code.
* **Coordinate Parallel Tasks:** When drafting multi-step plans, choose task boundaries that minimize agents touching the same files. If overlap is unavoidable, explicitly call out which tasks can run in parallel without merge risks and which must wait for earlier steps to finish.

### 3.2. Code Reviewer (Quality Control)

* **Focus:** Adherence to guidelines, architectural consistency, error handling, database query optimization.
* **Input:** Specific code changes or the entire `plan.md`.
* **Method:**
    1.  Check adherence to relevant guidelines (Frontend/Backend/Testing).
    2.  Verify alignment with the goals in `plan.md`.
    3.  Scrutinize error handling, edge cases, and security (e.g., input validation in FastAPI).
    4.  Review SQLAlchemy queries for efficiency, particularly those involving LTree operations.
* **Output:** A structured review report with actionable feedback and suggested improvements.

### 3.3. Developer (Implementation)

* **Focus:** Deliver working software that satisfies the approved plan. Implement features/endpoints/UI, author and evolve schemas/migrations, and maintain high signal-to-noise code quality without over-engineering.
* **Principles (Style & Pragmatics):**
  * Indent with **tabs** across all languages; use spaces only for alignment inside a line.
  * Avoid excessive defensive coding: validate inputs at boundaries (API, DB, user input) and handle expected failure modes; do not wrap every call with redundant checks.
  * Prefer clarity over cleverness; keep functions small, pure where reasonable, and composable.
  * YAGNI: don’t generalize until duplication or requirements demand it.
  * Keep public surfaces narrow; expose the minimum needed for tests and consumers.
  * Instrument with lightweight logging/metrics where it aids debugging and ops.

## 4. Context Injection

You must consult the relevant standards ("standards" folder) before starting a task. 
- If the user asks you to work on the frontend, you MUST review `frontend.md`. 
- If working on the backend, review `backend.md`. 
- Always review `best_practices.md`.

This project uses `docker compose` (with a space) instead of the older `docker-compose` (with a hyphen).

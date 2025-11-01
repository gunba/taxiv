# AI Agent Management System

This document defines the operational protocols, roles (Agents), and workflows for all AI interactions within the Taxiv project.

## 1. Guiding Principles

You are an expert full-stack developer (React/TypeScript Frontend, Python/FastAPI Backend, PostgreSQL Database). However, your memory is volatile. You must rely on the externalized state management system defined here.

1.  **Plan First:** No implementation code shall be written without an approved plan.
2.  **Externalize State:** Maintain the current task status in the `dev/active/[task-name]/` directory (Note: AI Agents should create `dev/active/` directories if they don't exist).
3.  **Adhere to Guidelines:** Follow the standards defined in the `ai_management/guidelines/` directory.
4.  **Iterate and Review:** Work in small steps and utilize the Quality Control agents frequently.
5.  **Use the Infrastructure:** All development, testing, and ingestion must utilize the Docker Compose environment to ensure consistency.

## 2. The Dev Docs Workflow (Externalized State)

(Sections 2.1 through 2.4 remain the same as provided in the input, utilizing the templates.)

## 3. Agent Roles

When instructed to adopt a role, utilize the specialized focus described below.

### 3.1. Strategic Architect (Planning)

* **Focus:** High-level planning, codebase research, architectural design (e.g., new database schemas using SQLAlchemy/LTree, API design with FastAPI, ingestion pipeline modularization).
* **Output:** Detailed implementation plans (`plan.md`).
* **Method:** Analyze dependencies, define phases, design data models, and structure the approach before writing implementation code.

### 3.2. Code Reviewer (Quality Control)

* **Focus:** Adherence to guidelines, architectural consistency, error handling, database query optimization.
* **Input:** Specific code changes or the entire `plan.md`.
* **Method:**
    1.  Check adherence to relevant guidelines (Frontend/Backend/Testing).
    2.  Verify alignment with the goals in `plan.md`.
    3.  Scrutinize error handling, edge cases, and security (e.g., input validation in FastAPI).
    4.  Review SQLAlchemy queries for efficiency, particularly those involving LTree operations.
* **Output:** A structured review report with actionable feedback and suggested improvements.


## 4. Context Injection

You must consult the relevant guidelines before starting a task. If the user asks you to work on the frontend, you MUST review `frontend_architecture.md`. If working on the backend, review `backend_architecture.md`. Always review `testing_standards.md` and `general_best_practices.md`.

This project uses `docker compose` (with a space) instead of the older `docker-compose` (with a hyphen).
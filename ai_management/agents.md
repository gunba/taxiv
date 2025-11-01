# AI Agent Management System

This document defines the operational protocols, roles (Agents), and workflows for all AI interactions within this project.

## 1. Guiding Principles

You are an expert full-stack developer (React/TypeScript Frontend, Python Backend). However, your memory is volatile. You must rely on the externalized state management system defined here.

1.  **Plan First:** No implementation code shall be written without an approved plan.
2.  **Externalize State:** Maintain the current task status in the `dev/active/[task-name]/` directory.
3.  **Adhere to Guidelines:** Follow the standards defined in the `ai_management/guidelines/` directory.
4.  **Iterate and Review:** Work in small steps and utilize the Quality Control agents frequently.

## 2. The Dev Docs Workflow (Externalized State)

For any non-trivial task, the following workflow is mandatory.

### 2.1. Initialization (The Strategic Architect)

1.  **User Defines Goal:** The user provides a high-level objective.
2.  **Activate Strategic Architect:** Analyze the request, research the codebase, and identify affected components.
3.  **Generate Plan:** Propose a detailed implementation plan using the `task_plan_template.md`.
4.  **Human Review:** The user MUST review and approve the plan. Iterate until approved.

### 2.2. Execution Setup

Once the plan is approved:
1.  **Create Task Directory:** `mkdir -p dev/active/[task-name]/`
2.  **Instantiate Dev Docs:**
    *   Save the approved plan as `[task-name]-plan.md`.
    *   Create `[task-name]-context.md` (using the template, add initial relevant files/snippets).
    *   Create `[task-name]-tasks.md` (convert the plan's steps into this checklist).

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

When instructed to adopt a role, utilize the specialized focus described below.

### 3.1. Strategic Architect (Planning)

*   **Focus:** High-level planning, codebase research, risk assessment.
*   **Output:** Detailed implementation plans (`plan.md`).
*   **Method:** Analyze dependencies, define phases, estimate effort, and structure the approach before writing implementation code.

### 3.2. Code Reviewer (Quality Control)

*   **Focus:** Adherence to guidelines, architectural consistency, error handling, test coverage.
*   **Input:** Specific code changes or the entire `plan.md`.
*   **Method:**
    1.  Check adherence to relevant guidelines (Frontend/Backend/Testing).
    2.  Verify alignment with the goals in `plan.md`.
    3.  Scrutinize error handling and edge cases.
    4.  Identify potential security vulnerabilities or performance issues.
*   **Output:** A structured review report with actionable feedback and suggested improvements.

### 3.3. Documentation Architect

*   **Focus:** Maintaining technical documentation and the project Changelog.
*   **Method:**
    1.  Review `plan.md` and implementation changes.
    2.  Update or create necessary technical documentation (System Architecture, API specs, Data Flows) in the `docs/` directory according to `documentation_standards.md`.
    3.  Update `CHANGELOG.md` with a summary of the changes, categorized (Feature, Fix, Refactor).

### 3.4. Test Engineer

*   **Focus:** Ensuring code stability and test coverage.
*   **Method:**
    1.  Analyze the requirements in `plan.md`.
    2.  Develop a testing strategy (Unit, Integration, E2E).
    3.  Write tests according to `testing_standards.md`.
    4.  Ensure all new features have coverage and all regressions are captured.

## 4. Context Injection

You must consult the relevant guidelines before starting a task. If the user asks you to work on the frontend, you MUST review `frontend_architecture.md`. If working on the backend, review `backend_architecture.md`. Always review `testing_standards.md` and `general_best_practices.md`.
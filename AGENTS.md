# AI Agent Management System

This directive governs every workflow an AI agent must follow while supporting the Taxiv codebase. Treat the following
as binding policy.

1. Operate as a senior full-stack engineer and own the overall quality bar for Taxiv at all times.

2. Do not author implementation code until a plan has been drafted, reviewed against the guidance in `agents/`, and
   approved by the user.

3. For each user task or request, produce a plan using `agents/plan.md` as the template and submit it for approval before
   executing any change.

4. Prior to writing code:
   a. Read `agents/best_practices.md`.  
   b. Read every domain-specific guide relevant to the task (e.g., `agents/frontend.md`, `agents/backend.md`,
      `agents/testing.md`).

5. Treat the `agents/` directory as a first-class surface you own: keep these standards accurate, well-structured, and up to date as you discover new constraints or workflows, and prefer tightening or reorganizing the guidance over duplicating it elsewhere.

6. Before returning the task to the user:
   a. Update the applicable documentation with any **material** discoveries so future agents do not repeat the same
      research.  
   b. Inspect the touched code paths for dead or unused logic, remove it, and call out the cleanup explicitly to the
      user.  
   c. Append a single-line summary of the work to `agents/changelog.md`.  
   d. Run every automated test suite impacted by your changes (use `scripts/run-tests.sh` when both stacks move, or the
      narrower `npm run test:frontend` / `npm run test:python` commands) and include the results or blockers in your
      final handoff. If a suite cannot run locally, state why and what was attempted.

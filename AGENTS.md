# AI Agent Management System

This document defines the workflows and guidelines for AI agents (that's you!) to follow when working on the Taxiv project.

1. You are an expert full-stack developer working on the Taxiv project and take personal responsibility for ensuring the project maintains a high quality level.

2. No implementation code shall be written without an approved plan, and without first reading the agents directory and determining the relevant guidelines for the task.

3. When the user defines a task or request, you must first create a plan and submit it to the user for approval. The template for the plan is available in `agents/plan.md`.

4. Before writing any code:
  a. Review the best_practices.md document (`agents/best_practices.md`); and
  b. Review the documentation that is relevant to the task (e.g. in agents/ there is 'frontend.md', 'backend.md', 'testing.md')

5. Before the task is returned to the user
  a. Update this documentation with any **significant** changes. The goal is accuracy, not extraneous content. This should include things you had to waste time learning about the project;
  b. Review the section of the code you are interacting with for any extraneous code that is no longer utilised and remove it (making it clear to the user this has occurred); and
  c. Update `agents/changelog.md` with a single line entry describing the commit.

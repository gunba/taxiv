# Documentation Standards

Documentation must be kept up-to-date with code changes.

## Types of Documentation

### 1. In-Code Documentation
*   **Frontend (JSDoc/TSDoc):** Document complex functions, hooks, and components explaining their purpose, props, and return values.
*   **Backend (Docstrings):** Use NumPy or Google style docstrings for all modules, classes, and functions.

### 2. Technical Documentation
*   Location: `docs/`
*   Content:
    *   System Architecture Overview
    *   Data Flow Diagrams (Use Mermaid syntax when possible)
    *   API Specifications
    *   Setup Guides (Local development environment)

### 3. Changelog
*   Location: `CHANGELOG.md`
*   Format: Keep a Changelog standard.
*   Update Policy: The Changelog must be updated by the Documentation Architect for every merged feature, fix, or significant refactor.
*   Categories: Use [Added], [Changed], [Fixed], [Removed], [Deprecated].
# Task Plan: Local Backend Requirements Installation

**Date:** 2024-11-24  
**Status:** Approved

## 1. Executive Summary

Set up the backend Python environment locally so dependencies (including pgvector support) install cleanly for upcoming testing. This involves provisioning OS prerequisites and installing `requirements.txt` inside a virtual environment.

## 2. Context and Requirements

Backend stack runs on Python 3.11+, FastAPI, SQLAlchemy, PostgreSQL with pgvector. Local dev needs PostgreSQL client libraries, pgvector extension headers, and a clean venv with all pip packages installed to support ingestion/API workflows outside Docker.

## 3. Proposed Solution Architecture

Use host-level tooling: install required system packages (`postgresql-16`, `postgresql-16-pgvector`, `libpq-dev`, `build-essential`) via apt, then create `.venv` in repo root and `pip install -r requirements.txt`. Validate via `pip check` and basic import smoke test.

## 4. Implementation Phases

### Phase 1: Prep & Verification

* **Goal:** Confirm local tooling and inspect dependency manifest.
* **Steps:**
	1. Verify available Python interpreter/pip versions.
	2. Review `requirements.txt` for native build dependencies (psycopg/pgvector).

### Phase 2: System Dependencies

* **Goal:** Install OS packages required for pgvector/psycopg builds.
* **Steps:**
	1. Update apt cache (`sudo apt-get update`).
	2. Install `postgresql-16`, `postgresql-16-pgvector`, `postgresql-client-16`, `libpq-dev`, `build-essential`.

### Phase 3: Python Environment

* **Goal:** Provision Python packages in isolated venv.
* **Steps:**
	1. Create/refresh `.venv` via `python3 -m venv .venv`.
	2. Activate venv and upgrade pip/setuptools/wheel.
	3. Install backend dependencies with `pip install -r requirements.txt`.

## 5. Testing Strategy

Run `python -m pip check` and a short inline script to import key modules (e.g., `import pgvector.psycopg`) to ensure installation success.

## 6. Risks and Mitigation

* Missing apt packages → document installs, rerun with appropriate permissions.
* Build failures for psycopg/pgvector → ensure `build-essential` and `libpq-dev` present.
* Sandbox restrictions → request escalated permissions if apt installs blocked.

## 7. Success Metrics

* `.venv` contains all dependencies.
* `pip check` reports no conflicts.
* Import smoke test succeeds.

## 8. Queries

* Should a specific PostgreSQL/pgvector version be enforced beyond distro defaults?
* Any preference for documenting venv activation workflow for other developers?

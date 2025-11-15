#!/usr/bin/env bash
#
# Full-stack test harness for Taxiv.
# Runs frontend (Vitest) and backend/ingest (Pytest) suites from the repo root.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

log() {
	printf '\n==> %s\n' "$1"
}

cd "$ROOT_DIR"

log "Running frontend tests (Vitest)"
npm run test:frontend

log "Running Python tests (pytest)"
pytest "$@" tests/backend tests/ingestion

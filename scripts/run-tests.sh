#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

log() {
	printf '\n==> %s\n' "$1"
}

cd "$ROOT_DIR"

log "Running frontend tests (Vitest)"
npm run test:frontend

PYTEST_ARGS=()
if [[ $# -gt 0 ]]; then
	PYTEST_ARGS=("$@")
fi

log "Running Python tests (pytest)"
pytest "${PYTEST_ARGS[@]}" tests/backend tests/ingest

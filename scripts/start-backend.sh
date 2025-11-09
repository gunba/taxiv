#!/usr/bin/env bash
set -euo pipefail

APP_PATH=${UVICORN_APP:-backend.main:app}
HOST=${UVICORN_HOST:-0.0.0.0}
PORT=${UVICORN_PORT:-8000}
WORKERS=${UVICORN_WORKERS:-4}
RELOAD=${UVICORN_RELOAD:-0}
LOOP=${UVICORN_LOOP:-uvloop}
HTTP=${UVICORN_HTTP:-httptools}

CMD=(
	uvicorn "${APP_PATH}"
	--host "${HOST}"
	--port "${PORT}"
	--loop "${LOOP}"
	--http "${HTTP}"
)

if [[ "${RELOAD}" == "1" ]]; then
	echo "[backend] Starting uvicorn with reload mode (single worker)." >&2
	exec "${CMD[@]}" --reload
fi

echo "[backend] Starting uvicorn with ${WORKERS} workers." >&2
exec "${CMD[@]}" --workers "${WORKERS}"

#!/usr/bin/env bash
# E2E of the browser app: builds the front end, serves it with a scratch catalogue (imported,
# nothing released) and drives it with Playwright. Needs ngspice and Chromium for Playwright.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${PYTHON:-python}"
TMP="$(mktemp -d)"
PORT="${PORT:-8790}"
trap 'kill "${SERVER:-}" 2>/dev/null || true; rm -rf "$TMP"' EXIT

(cd "$ROOT/frontend" && npx vite build >/dev/null)
"$PY" - "$TMP/catalog.db" "$ROOT/data/components" <<'PY'
import sys
from pathlib import Path
from circuitos.components.repository import ComponentRepository
ComponentRepository(f"sqlite:///{sys.argv[1]}").import_directory(Path(sys.argv[2]))
PY
CIRCUITOS_DB_URL="sqlite:///$TMP/catalog.db" "$PY" -m uvicorn circuitos.api.app:app --port "$PORT" \
  >"$TMP/server.log" 2>&1 &
SERVER=$!
for _ in $(seq 50); do curl -sf "http://127.0.0.1:$PORT/api/v1/health" >/dev/null && break; sleep 0.2; done
BASE="http://127.0.0.1:$PORT" node "$ROOT/frontend/e2e/simulador.e2e.cjs"

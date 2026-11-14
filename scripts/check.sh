#!/usr/bin/env bash
# Local quality gate (replaces CI, decision D1). Run before each delivery:
#   scripts/check.sh            # everything
#   scripts/check.sh backend    # only Python
#   scripts/check.sh frontend   # only TypeScript
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TARGET="${1:-all}"

if [[ "$TARGET" == all || "$TARGET" == backend ]]; then
  echo "== backend =="
  cd "$ROOT/backend"
  uv run ruff format --check src tests
  uv run ruff check src tests
  uv run mypy
  uv run lint-imports
  uv run pytest --cov --cov-report=term-missing:skip-covered --cov-fail-under=80
fi

if [[ "$TARGET" == all || "$TARGET" == frontend ]]; then
  echo "== frontend =="
  cd "$ROOT/frontend"
  npm run --silent format:check
  npx tsc -b
  npm run --silent lint
  npm test --silent
  npm run --silent build
fi
echo "OK"

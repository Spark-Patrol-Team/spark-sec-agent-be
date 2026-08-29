#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-/opt/homebrew/bin/python3.11}"
API_HOST="${API_HOST:-127.0.0.1}"
API_PORT="${API_PORT:-8000}"

export PLATFORM_BACKEND=fixed_sample

cd "$ROOT_DIR"
exec uv run --python "$PYTHON_BIN" python -m uvicorn sec_agent.main:app --host "$API_HOST" --port "$API_PORT"

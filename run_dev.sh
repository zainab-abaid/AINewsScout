#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"

if [[ ! -d .venv ]]; then
  uv sync
fi

if [[ ! -d frontend/node_modules ]]; then
  (cd frontend && npm install)
fi

uv run uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000 &
API_PID=$!
trap 'kill $API_PID 2>/dev/null || true' EXIT

cd frontend
npm run dev

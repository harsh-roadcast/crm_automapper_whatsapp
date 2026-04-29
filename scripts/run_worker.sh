#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required but was not found in PATH." >&2
  exit 1
fi

LOG_LEVEL="${LOG_LEVEL:-info}"

exec uv run celery -A backend.app.api.tasks.reengagement_tasks.celery_app worker --loglevel "$LOG_LEVEL"
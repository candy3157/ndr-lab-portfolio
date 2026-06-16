#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

if [ -f .venv/bin/activate ]; then
  . .venv/bin/activate
fi

python -m traffic_client.main -c "${1:-config.json}" loop

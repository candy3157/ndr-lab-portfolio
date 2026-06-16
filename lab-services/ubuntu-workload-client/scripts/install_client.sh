#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$PROJECT_DIR"
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .

if [ ! -f config.json ]; then
  cp config.example.json config.json
fi

echo "Installed ubuntu-workload-client in $PROJECT_DIR"
echo "Edit config.json, then run:"
echo "  . .venv/bin/activate"
echo "  ubuntu-workload-client -c config.json check"
echo "  ubuntu-workload-client -c config.json loop"

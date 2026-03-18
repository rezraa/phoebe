#!/bin/bash
# Start Phoebe Dashboard
# Usage: ./start.sh [tome_path]
cd "$(dirname "$0")"
TOME="${1:-./demo.tome}"
echo "Phoebe Dashboard → http://127.0.0.1:8888"
echo "Tome: $TOME"
PYTHONPATH=src .venv/bin/python3 -m phoebe.dashboard.app "$TOME"

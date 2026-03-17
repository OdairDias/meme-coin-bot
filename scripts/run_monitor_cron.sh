#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE="$(cd "$SCRIPT_DIR/.." && pwd)"
source "$WORKSPACE/secrets.env"
source "$WORKSPACE/.venv/bin/activate"
cd "$WORKSPACE" || exit 1
python scripts/monitor_bitquery_fallback.py

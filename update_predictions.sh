#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════
# update_predictions.sh — Full pipeline refresh
#
# Now delegates to auto_update.py which handles:
#   scrape → predict → update website → log
#
# Falls back to the old CSV-based pipeline if auto_update.py is missing.
#
# Usage:
#   ./update_predictions.sh              # manual run
#   crontab -e  →  0 6 * * * /home/dale/chess_prediction/update_predictions.sh
# ══════════════════════════════════════════════════════════════════════

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$PROJECT_DIR/venv"

if [ ! -d "$VENV_DIR" ]; then
    echo "ERROR: venv not found at $VENV_DIR"
    exit 1
fi

# ── Activate venv ─────────────────────────────────────────────────
source "$VENV_DIR/bin/activate"

cd "$PROJECT_DIR"

RUN_TS=$(date '+%Y-%m-%d %H:%M:%S')
echo "[$RUN_TS] Starting pipeline update..."

# ── Run auto_update.py (scrape + predict + update site) ──────────
python auto_update.py

echo "[$RUN_TS] Pipeline update complete."

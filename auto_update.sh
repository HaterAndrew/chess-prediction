#!/bin/bash
# Cron wrapper for auto_update.py
# Usage: crontab -e → 0 6 * * * /home/dale/chess_prediction/auto_update.sh
cd ~/chess_prediction
source venv/bin/activate

# AUDIT.md E2 — rotate auto_update.log when it exceeds 5MB to prevent
# unbounded growth. Keep last 3 archives.
LOG=output/auto_update.log
if [ -f "$LOG" ] && [ "$(stat -c%s "$LOG")" -gt 5242880 ]; then
    mv "$LOG.2" "$LOG.3" 2>/dev/null
    mv "$LOG.1" "$LOG.2" 2>/dev/null
    mv "$LOG" "$LOG.1"
fi

python3 auto_update.py >> "$LOG" 2>&1

#!/bin/bash
# Cron wrapper for auto_update.py
# Usage: crontab -e → 0 6 * * * /home/dale/chess_prediction/auto_update.sh
cd ~/chess_prediction
source venv/bin/activate
python3 auto_update.py >> output/auto_update.log 2>&1

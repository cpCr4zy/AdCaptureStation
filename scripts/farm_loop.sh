#!/bin/bash
# Continuous playable-creative collection: the bot plays, the harvester picks up what it finds.
# Usage: farm_loop.sh [minutes_per_cycle]
set -u
cd $HOME/playables/adcapture || exit 1
PY=$HOME/playables/botvenv/bin/python
CYCLE=${1:-50}
LOG=run3h.log

while true; do
  echo "=== cycle start $(date '+%F %T') ===" >>"$LOG"
  "$PY" bot_screws.py --minutes "$CYCLE" >>"$LOG" 2>&1
  echo "=== cycle end $(date '+%F %T') ===" >>"$LOG"
  # pick up creatives the bot did not get to process before exiting
  "$PY" harvest_applovin.py >>harvest.log 2>&1
  sleep 15
done

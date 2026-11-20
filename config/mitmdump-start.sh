#!/bin/bash
# Canonical capture start: five addons, pinned CA, port 8080.
# Verify afterwards: stat -c %s $CAP/requests.jsonl twice, 15 s apart -> must grow.
set -u
CAP=$HOME/playables/adcapture
PY=$HOME/playables/mitmvenv/bin/mitmdump
LOG=$CAP/mitm.log

# truncate the log and mark the start, so "no Traceback" gates mean *this* run
: > "$LOG"
echo "=== mitmdump start $(date -Is) ===" >>"$LOG"

exec "$PY" \
    --set confdir=$CAP/mitmconf \
    --listen-port 8080 \
    --flow-detail 0 \
    -s $CAP/catch_playable.py \
    -s $CAP/capture_all.py \
    -s $CAP/catch_century.py \
    -s $CAP/capture_requests.py \
    -s $CAP/capture_responses.py >>"$LOG" 2>&1

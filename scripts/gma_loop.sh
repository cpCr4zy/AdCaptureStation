#!/bin/bash
# Second capture channel: Google auctions are replayed directly, no gameplay.
# One round = one auction per captured ad slot.
set -u
cd $HOME/playables/adcapture || exit 1
PY=$HOME/playables/botvenv/bin/python

while true; do
  "$PY" pull_gma.py --rounds 1 >>gma_pull.log 2>&1
  sleep 300
done

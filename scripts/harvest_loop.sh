#!/bin/bash
# Frequent harvest: a creative reaches the gallery minutes after it is shown,
# not at the end of the hour. Two independent sources:
#   harvest_applovin.py — flat res1.applovin.com URLs from the proxy logs
#   harvest_wvcache.py  — the app's WebView HTTP cache (byte-exact playable)
set -u
cd $HOME/playables/adcapture || exit 1
PY=$HOME/playables/botvenv/bin/python

while true; do
  "$PY" harvest_applovin.py >>harvest.log 2>&1
  "$PY" harvest_wvcache.py >>harvest_wv.log 2>&1
  sleep 180
done

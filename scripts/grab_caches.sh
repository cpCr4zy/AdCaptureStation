#!/bin/bash
# Pull every cached playable bundle (html/zip) out of all apps inside the
# Waydroid container into /sdcard/grab.tar, then show what was found.
# Run as root:  sudo bash $HOME/playables/adcapture/grab_caches.sh
set -u
LOG=$HOME/playables/adcapture/grab.log

{
  echo "== scanning app caches for playable bundles"
  /usr/bin/python3 /usr/sbin/waydroid shell "
    rm -f /sdcard/plist.txt /sdcard/grab.tar
    cd /data/data
    find . -maxdepth 7 -type f \\( -name '*.zip' -o -name '*.html' -o -name '*.htm' \\) -size +10k 2>/dev/null > /sdcard/plist.txt
    echo -n 'candidates: '; wc -l < /sdcard/plist.txt
    tar -cf /sdcard/grab.tar -T /sdcard/plist.txt 2>/dev/null
    ls -la /sdcard/grab.tar 2>&1
    echo '--- first 40 candidates'
    head -40 /sdcard/plist.txt
  " 2>&1
} > "$LOG" 2>&1

cat "$LOG"

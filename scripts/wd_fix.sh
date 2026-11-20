#!/bin/bash
# Bring up the Waydroid container's eth0 with the address waydroid expects,
# enable adbd on TCP 5555, and dump diagnostics for the host user to read.
# Run as root:  sudo bash $HOME/playables/adcapture/wd_fix.sh
set -u
OUT=$HOME/playables/adcapture/wd_net.txt

{
  echo "=== host: container state"
  lxc-info -P /var/lib/waydroid/lxc -n waydroid -sH

  lxc-attach -P /var/lib/waydroid/lxc -n waydroid -- /system/bin/sh -c "
    echo '--- before'
    ip -br addr
    ip route
    echo '--- fixing eth0'
    ip link set eth0 up
    ip addr add "${SERIAL%%:*}/24" dev eth0 2>&1   # SERIAL is <guest-ip>:5555
    ip route add default via 192.168.240.1 2>&1
    echo '--- adbd'
    setprop service.adb.tcp.port 5555
    stop adbd 2>&1
    start adbd 2>&1
    sleep 3
    echo '--- after'
    ip -br addr
    ip route
    getprop service.adb.tcp.port
    getprop sys.boot_completed
    getprop ro.dalvik.vm.native.bridge
    echo '--- ethernet'
    dumpsys ethernet 2>&1 | head -40
    echo '--- netd/listening'
    netstat -tlnp 2>/dev/null | head -20
  " 2>&1
} > "$OUT" 2>&1

chmod 666 "$OUT"
echo "written: $OUT"
tail -30 "$OUT"

#!/bin/bash
# Authorize host adb inside the Waydroid container, enable adbd on TCP,
# set the host mitmproxy as the global proxy and keep Android awake.
# Run as root:  sudo bash $HOME/playables/adcapture/wd_adbkey.sh
set -u
KEYFILE=$HOME/.android/adbkey.pub
[ -r "$KEYFILE" ] || { echo "no $KEYFILE"; exit 1; }
KEY=$(cat "$KEYFILE")

INNER=$(cat <<EOF
set -x
mkdir -p /data/misc/adb
printf '%s\n' "$KEY" > /data/misc/adb/adb_keys
chown system:shell /data/misc/adb/adb_keys
chmod 640 /data/misc/adb/adb_keys
setprop service.adb.tcp.port 5555
setprop ctl.restart adbd
settings put global http_proxy 192.168.240.1:8080
settings put system screen_off_timeout 2147483647
svc power stayon true
echo "--- state"
getprop service.adb.tcp.port
settings get global http_proxy
settings get system screen_off_timeout
ls -l /data/misc/adb/adb_keys
EOF
)

B64=$(printf '%s' "$INNER" | base64 -w0)

echo "=== unfreeze container"
lxc-unfreeze -P /var/lib/waydroid/lxc -n waydroid 2>&1 || true
sleep 2

echo "=== running inside container"
/usr/bin/python3 /usr/sbin/waydroid shell "/system/bin/sh -c 'echo $B64 | base64 -d > /data/local/tmp/wdfix.sh; /system/bin/sh /data/local/tmp/wdfix.sh'" 2>&1 | tail -25

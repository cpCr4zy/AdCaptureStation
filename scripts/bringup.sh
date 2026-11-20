#!/usr/bin/env bash
# Bring Waydroid + proxy back and start a short farm so the SDK emits ad calls.
set -u
export XDG_RUNTIME_DIR=/run/user/1000 WAYLAND_DISPLAY=wayland-1
ADB=$HOME/Android/Sdk/platform-tools/adb
DEV="${SERIAL:-$(waydroid status | sed -n 's/^IP address:[[:space:]]*//p')}:5555"
W="/usr/bin/python3 /usr/sbin/waydroid"
CAP=$HOME/playables/adcapture

if ! $W status 2>/dev/null | grep -q "Session:.*RUNNING"; then
  echo "== session start"
  $W session stop >/dev/null 2>&1; sleep 3
  $W session start >/dev/null 2>&1 &
  sleep 45
fi
$ADB connect $DEV >/dev/null 2>&1
for i in $(seq 1 15); do $ADB -s $DEV shell true >/dev/null 2>&1 && break; sleep 4; done
echo "== device: $($ADB devices | grep $DEV)"

$ADB -s $DEV shell "settings put global http_proxy 192.168.240.1:8080"
$ADB -s $DEV shell "pm disable-user --user 0 com.android.documentsui" >/dev/null 2>&1
$ADB -s $DEV shell "svc power stayon true" >/dev/null 2>&1
echo "== proxy: $($ADB -s $DEV shell 'settings get global http_proxy' | tr -d '\r')"
H=$(openssl x509 -inform PEM -subject_hash_old -in $HOME/playables/adcapture/mitmconf/mitmproxy-ca-cert.pem 2>/dev/null | head -1)
echo "== ca: $($ADB -s $DEV shell "ls /system/etc/security/cacerts/$H.0" | tr -d '\r')"

$ADB -s $DEV shell "am force-stop com.quok.screwJam"
sleep 2
$ADB -s $DEV shell "am start -n com.quok.screwJam/com.rollic.elephantsdk.ElephantActivity" >/dev/null
sleep 20
echo "== focus: $($ADB -s $DEV shell 'dumpsys window | grep -m1 mCurrentFocus' | tr -d '\r' | cut -c1-90)"

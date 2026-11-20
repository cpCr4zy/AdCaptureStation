#!/usr/bin/env bash
# Unstick Waydroid: the guest is booted (launcher resumed) but the boot
# animation layer never exits, so every screencap returns the spinner.
# Needs root: sudo bash wd_unstick.sh
set -u

export XDG_RUNTIME_DIR=/run/user/1000
export WAYLAND_DISPLAY=wayland-1

W="/usr/bin/python3 /usr/sbin/waydroid"

echo "[1/4] stopping boot animation"
$W shell -- 'setprop service.bootanim.exit 1; setprop ctl.stop bootanim; sleep 1; killall bootanimation 2>/dev/null; pidof bootanimation || echo "bootanim gone"'

echo "[2/4] adb over tcp"
$W shell -- 'setprop service.adb.tcp.port 5555; setprop ctl.restart adbd'

echo "[3/4] keep-awake + proxy"
$W shell -- 'settings put global http_proxy 192.168.240.1:8080; settings put system screen_off_timeout 2147483647; svc power stayon true'

echo "[4/4] re-adding adb key"
KEY="$(cat $HOME/.android/adbkey.pub)"
$W shell -- "mkdir -p /data/misc/adb; printf '%s\n' '$KEY' > /data/misc/adb/adb_keys; chown system:shell /data/misc/adb/adb_keys; chmod 640 /data/misc/adb/adb_keys; ls -l /data/misc/adb/adb_keys"

sleep 3
$HOME/Android/Sdk/platform-tools/adb connect "${SERIAL:-$(waydroid status | sed -n 's/^IP address:[[:space:]]*//p')}:5555" || true
$HOME/Android/Sdk/platform-tools/adb -s "${SERIAL:-$(waydroid status | sed -n 's/^IP address:[[:space:]]*//p')}:5555" shell 'getprop sys.boot_completed; dumpsys window | grep -m1 mCurrentFocus'
echo "done"

#!/usr/bin/env bash
# Recover Waydroid after the display pipeline died (SurfaceFlinger has no
# layers, boot animation stuck, mCurrentFocus=null) and restart the 3-hour
# creative-harvesting run.
#
#   sudo bash $HOME/playables/adcapture/recover_and_run.sh
#
# Everything below the container restart is idempotent.
set -u

ADB=$HOME/Android/Sdk/platform-tools/adb
DEV="${SERIAL:-$(waydroid status | sed -n 's/^IP address:[[:space:]]*//p')}:5555"
CAP=$HOME/playables/adcapture
U="sudo -u "$USER" env XDG_RUNTIME_DIR=/run/user/1000 WAYLAND_DISPLAY=wayland-1 PATH=/usr/bin:/bin:/usr/local/bin"

echo "== 1/6 restarting waydroid container"
systemctl restart waydroid-container
sleep 5

echo "== 2/6 starting waydroid session (as $USER)"
$U /usr/bin/python3 /usr/sbin/waydroid session start >/tmp/wd_session.log 2>&1 &
sleep 25

echo "== 3/6 waiting for boot"
for i in $(seq 1 40); do
  b=$($ADB -s $DEV shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')
  [ "$b" = "1" ] && break
  sleep 5
done
echo "   boot_completed=${b:-?}"

echo "== 4/6 killing boot animation + android services"
/usr/bin/python3 /usr/sbin/waydroid shell -- 'setprop service.bootanim.exit 1; setprop ctl.stop bootanim; settings put global http_proxy 192.168.240.1:8080; settings put system screen_off_timeout 2147483647; svc power stayon true; setprop service.adb.tcp.port 5555; setprop ctl.restart adbd; mkdir -p /data/misc/adb; chown system:shell /data/misc/adb; chmod 771 /data/misc/adb' || true
KEY="$(cat $HOME/.android/adbkey.pub)"
/usr/bin/python3 /usr/sbin/waydroid shell -- "printf '%s\n' '$KEY' > /data/misc/adb/adb_keys; chown system:shell /data/misc/adb/adb_keys; chmod 640 /data/misc/adb/adb_keys" || true
sleep 4
$ADB connect $DEV || true

echo "== 5/6 launching the game"
$ADB -s $DEV shell am start -n com.quok.screwJam/com.rollic.elephantsdk.ElephantActivity
sleep 12
$ADB -s $DEV shell 'dumpsys SurfaceFlinger --list | head -3; dumpsys window | grep -m1 mCurrentFocus'

echo "== 6/6 starting the 3-hour harvesting run"
pkill -f bot_screws.py 2>/dev/null
sudo -u "$USER" nohup $HOME/playables/botvenv/bin/python $CAP/bot_screws.py --minutes 180 \
  > $CAP/run3h.stdout 2>&1 &
sleep 20
sudo -u "$USER" tail -5 $CAP/run3h.stdout
echo "run started; watch with: tail -f $CAP/run3h.stdout"

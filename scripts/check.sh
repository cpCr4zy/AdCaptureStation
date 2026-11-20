echo "== basics"
echo -n "boot_completed: "; getprop sys.boot_completed
echo -n "sdk: "; getprop ro.build.version.sdk
echo -n "abilist: "; getprop ro.product.cpu.abilist
echo -n "native_bridge: "; getprop ro.dalvik.vm.native.bridge
echo -n "adb_tcp_port: "; getprop service.adb.tcp.port
echo "== power"
dumpsys power | grep -iE "mWakefulness=|Display Power" | head -3
echo -n "stay_on_while_plugged_in: "; settings get global stay_on_while_plugged_in
echo -n "screen_off_timeout: "; settings get system screen_off_timeout
echo "== proxy"
echo -n "http_proxy: "; settings get global http_proxy
echo -n "global_http_proxy_host: "; settings get global global_http_proxy_host
echo "== ca"
H=$(openssl x509 -inform PEM -subject_hash_old -in $HOME/playables/adcapture/mitmconf/mitmproxy-ca-cert.pem 2>/dev/null | head -1)
ls -l /system/etc/security/cacerts/$H.0
echo "== tools"
for t in curl wget nc ping; do echo -n "$t: "; command -v $t || echo missing; done
echo "== net"
ip -br addr show eth0
ip route | head -3
echo -n "gw ping: "; ping -c1 -W2 192.168.240.1 | tail -1
echo -n "inet ping: "; ping -c1 -W2 8.8.8.8 | tail -1
echo -n "dns: "; ping -c1 -W3 google.com | tail -2
echo "== apps"
pm list packages | grep -E "block.juggle|magicsort|documentsui"
echo "== top"
dumpsys activity activities | grep -m2 -E "mResumedActivity|topResumedActivity"
echo "== disk"
df -h /data 2>/dev/null | tail -2

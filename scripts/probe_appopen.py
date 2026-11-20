import os

HOME = os.path.expanduser("~")

def _guest_serial():
    """The guest address is assigned by DHCP: read it from waydroid, or take $SERIAL."""
    try:
        import subprocess as _sp
        out = _sp.run(["waydroid", "status"], capture_output=True, text=True).stdout
        m = re.search(r"IP address:\s*([0-9.]+)", out)
        return f"{m.group(1)}:5555" if m else ""
    except Exception:
        return ""


"""Does an app launch bring an ad? Probe before building a farming loop.

AppLovin's mediate traffic is an encrypted envelope, so the only readable signal is the
plain `res1.applovin.com` creative fetch that follows a real impression. If a cold start
shows an ad, restarting the game becomes a creative source that needs no gameplay.
"""
import subprocess
import time

ADB = [os.path.join(HOME, "Android/Sdk/platform-tools/adb"), "-s", os.environ.get("SERIAL") or _guest_serial()]
PKG = "com.quok.screwJam"
ACT = f"{PKG}/com.rollic.elephantsdk.ElephantActivity"


def sh(*args, timeout=40):
    return subprocess.run(ADB + list(args), capture_output=True, text=True, timeout=timeout).stdout


def focus():
    for line in sh("shell", "dumpsys window").splitlines():
        if "mCurrentFocus" in line:
            return line.strip()
    return ""


def main():
    for i in range(3):
        sh("shell", f"am force-stop {PKG}")
        time.sleep(2)
        sh("shell", f"am start -n {ACT}")
        t0 = time.time()
        ad_seen = None
        while time.time() - t0 < 30:
            f = focus()
            if "applovin" in f.lower() or "AdActivity" in f or "WebViewActivity" in f:
                ad_seen = round(time.time() - t0, 1)
                print(f"  launch {i}: AD at {ad_seen}s -> {f.split('u0 ')[-1][:70]}")
                break
            time.sleep(1)
        if ad_seen is None:
            print(f"  launch {i}: no ad within 30s ({focus().split('u0 ')[-1][:50]})")
        time.sleep(3)


if __name__ == "__main__":
    main()

"""Harvest playables from the app's WebView HTTP cache, byte-exact.

An ad's creative is rendered inside the game's WebView, so Chromium writes the whole
playable (HTML + JS + assets) into its HTTP cache before we ever see a URL. The cache
lives in app-private storage, which is readable through the container:

    sudo lxc-attach -P /var/lib/waydroid/lxc -n waydroid -- ...

Each `Cache_Data/*_0` file is a Chromium simple-cache entry: a small header, the URL,
then the response body. We copy the cache to /data/local/tmp (adb-readable), pull it,
and keep the entries whose URL belongs to a creative host.
"""
import argparse
import hashlib
import json
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

import re
import shutil
import subprocess
import time

PKG = "com.quok.screwJam"
ADB = [os.path.join(HOME, "Android/Sdk/platform-tools/adb"), "-s", os.environ.get("SERIAL") or _guest_serial()]
LXC = ["sudo", "-n", "lxc-attach", "-P", "/var/lib/waydroid/lxc", "-n", "waydroid", "--",
       "/system/bin/sh", "-c"]
CACHE = f"/data/data/{PKG}/cache/WebView/Default/HTTP Cache/Cache_Data"
STAGE = "/data/local/tmp/wvcache"
BASE = os.path.join(HOME, "playables/adcapture")
OUT = os.path.join(HOME, "playables/captured/misc/wv")
MANIFEST = os.path.join(HOME, "playables/captured/manifest.jsonl")

CREATIVE_HOSTS = ("unity3dusercontent.com", "res1.applovin.com", "cdn-creatives",
                  "applovin.com", "2mdn.net", "doubleclick.net/mad", "vungle.com",
                  "unityads.unity3d.com/legacy", "mintegral", "bidmachine")
SKIP_HOSTS = ("sdk-core-v40.html", "/mads/static/sdk/", "gstatic.com/", "w3.org")
URL_RE = re.compile(rb"https?://[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]{10,300}")
PKG_RE = re.compile(r"play\.google\.com/store/apps/details\?id=([A-Za-z0-9_.]+)")


def lxc(inner: str, timeout=120):
    return subprocess.run(LXC + [f"export PATH=/system/bin:/system/xbin; {inner}"],
                          capture_output=True, text=True, timeout=timeout)


def stage_and_pull():
    """Copy the cache to an adb-readable dir, then pull it into a clean local dir."""
    lxc(f"rm -rf {STAGE}; mkdir -p {STAGE}; cp -r '{CACHE}/'* {STAGE}/ 2>/dev/null; "
        f"chmod -R 777 {STAGE}")
    probe = subprocess.run(ADB + ["shell", f"ls {STAGE}"], capture_output=True, text=True)
    if not probe.stdout.strip():
        print("  staging failed:", probe.stderr.strip()[:120])
        return ""
    local = os.path.join(BASE, "wv_pull")
    shutil.rmtree(local, ignore_errors=True)
    os.makedirs(local, exist_ok=True)
    subprocess.run(ADB + ["pull", STAGE, local], capture_output=True, text=True, timeout=180)
    inner = os.path.join(local, os.path.basename(STAGE))
    return inner if os.path.isdir(inner) else local


def entry_url(blob: bytes) -> str:
    for m in URL_RE.finditer(blob[:4096]):
        u = m.group(0).decode("ascii", "ignore")
        if u.startswith("http") and not any(s in u for s in SKIP_HOSTS):
            return u
    return ""


def body_of(blob: bytes) -> bytes:
    """Chromium stores `key` then the response; the body starts at the first HTML/JS byte run."""
    low = blob.lower()
    for marker in (b"<!doctype", b"<html", b"function", b"var ", b"const ", b"{"):
        i = low.find(marker)
        if i > 0:
            return blob[i:]
    return blob


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-size", type=int, default=20_000)
    args = ap.parse_args()

    root = stage_and_pull()
    if not root or not os.path.isdir(root):
        raise SystemExit("cache pull failed")

    os.makedirs(OUT, exist_ok=True)
    kept = 0
    for name in sorted(os.listdir(root)):
        path = os.path.join(root, name)
        if not os.path.isfile(path):
            continue
        blob = open(path, "rb").read()
        if len(blob) < args.min_size:
            continue
        url = entry_url(blob)
        if not url or not any(h in url for h in CREATIVE_HOSTS):
            continue
        body = body_of(blob)
        if b"<html" not in body[:8000].lower() and b"<script" not in body[:8000].lower():
            continue
        sha = hashlib.sha1(body).hexdigest()
        dest = os.path.join(OUT, sha + ".html")
        if os.path.exists(dest):
            continue
        open(dest, "wb").write(body)
        text = body[:300_000].decode("utf-8", "ignore")
        pkgs = PKG_RE.findall(text)
        with open(MANIFEST, "a") as fh:
            fh.write(json.dumps({
                "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                "creative": sha, "size": len(body), "raw": dest, "project": "",
                "source": url, "channel": "webview-cache",
                "pkg": pkgs[0] if pkgs else "", "pkgs": pkgs[:5],
                "century": any("century" in p or p in (
                    "com.gof.global", "com.merge.game.foodstars", "com.phs.global",
                    "com.fatmerge.global", "com.run.tower.defense") for p in pkgs),
                "title": (re.search(r"<title>([^<]{0,80})</title>", text, re.I) or [None, ""])[1]
                if re.search(r"<title>([^<]{0,80})</title>", text, re.I) else "",
            }, ensure_ascii=False) + "\n")
        kept += 1
        print(f"  +{len(body)//1024}KB {url[:80]}")
    print(f"webview-cache: entries kept: {kept}, cache size: "
          f"{sum(os.path.getsize(os.path.join(root, f)) for f in os.listdir(root))//1024}KB")


if __name__ == "__main__":
    main()

"""Catch Century Games ad creatives live, whatever the network.

Two jobs:

1. Record every AppLovin playable URL the moment the SDK asks for it, so the
   offline harvester can fetch the twin `_v1_raw.html` later (`applovin_urls.txt`).
2. Save the body of any response that mentions a Century Games title or package
   (Kingshot / Whiteout Survival / Tiles Survive / ...), into `century/`, with an
   index line in `century_index.jsonl`.

Load with:  -s catch_playable.py -s capture_all.py -s catch_century.py
"""
import hashlib
import json
import os

HOME = os.path.expanduser("~")
import re
import time

from mitmproxy import http

BASE = os.path.join(HOME, "playables/adcapture")
OUT = os.path.join(BASE, "century")
URLS = os.path.join(BASE, "applovin_urls.txt")
IDX = os.path.join(BASE, "century_index.jsonl")
os.makedirs(OUT, exist_ok=True)

APPLOVIN_RE = re.compile(r"res1\.applovin\.com/.+?_v1_js_load\.js")

# cheap text markers; matching any of these means "this body is a Century creative"
MARKERS = (
    "com.run.tower.defense",   # Kingshot
    "com.gof.global",          # Whiteout Survival
    "com.fatmerge.global",     # Fat Merge
    "com.phs.global",          # Puzzle & Survival
    "kingshot",
    "whiteout survival",
    "century games",
    "centurygames",
)
MAX_BYTES = 20 * 1024 * 1024


def response(flow: http.HTTPFlow) -> None:
    url = flow.request.pretty_url

    if APPLOVIN_RE.search(url):
        line = url.split("?")[0] + "\n"
        try:
            if line not in open(URLS).read():
                with open(URLS, "a") as fh:
                    fh.write(line)
        except FileNotFoundError:
            with open(URLS, "a") as fh:
                fh.write(line)

    body = flow.response.content or b""
    if not body or len(body) > MAX_BYTES:
        return
    # only scan text-ish payloads; base64 zips hide the markers anyway
    ctype = flow.response.headers.get("content-type", "").lower()
    if not any(t in ctype for t in ("text", "json", "javascript")):
        return
    try:
        text = body.decode("utf-8", errors="ignore")
    except Exception:
        return
    low = text.lower()
    hits = [m for m in MARKERS if m in low]
    if not hits:
        return

    digest = hashlib.sha1(body).hexdigest()
    path = os.path.join(OUT, digest[:2], digest)
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(body)
    rec = {
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "url": url[:2000],
        "host": flow.request.pretty_host,
        "ctype": ctype,
        "size": len(body),
        "markers": hits,
        "file": path,
    }
    with open(IDX, "a") as fh:
        fh.write(json.dumps(rec) + "\n")

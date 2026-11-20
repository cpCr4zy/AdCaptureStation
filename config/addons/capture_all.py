"""Capture every ad-related response body so a playable creative can be
reassembled offline (html + js + images), with an index for grepping.

Restart mitmdump with:  -s catch_playable.py -s capture_all.py
"""
import hashlib
import json
import os

HOME = os.path.expanduser("~")
import time

from mitmproxy import http

BASE = os.path.join(HOME, "playables/adcapture")
OUT = os.path.join(BASE, "all")
IDX = os.path.join(BASE, "all_index.jsonl")
os.makedirs(OUT, exist_ok=True)

KEEP = (
    "text/html",
    "application/javascript",
    "text/javascript",
    "application/json",
    "application/zip",
    "application/octet-stream",
    "image/",
    "application/x-javascript",
)
MAX_BYTES = 12 * 1024 * 1024
# hosts that only serve telemetry/config noise
SKIP_HOST_PARTS = (
    "firebase", "crashlytics", "google-analytics", "doubleclick.net/pixel",
    "app-measurement", "adjust.com", "facebook.com/tr", "settings.crashlytics",
)


def response(flow: http.HTTPFlow) -> None:
    host = flow.request.pretty_host
    if any(s in flow.request.pretty_url for s in SKIP_HOST_PARTS):
        return
    ctype = flow.response.headers.get("content-type", "").lower()
    if not any(k in ctype for k in KEEP):
        return
    body = flow.response.content or b""
    if not body or len(body) > MAX_BYTES:
        return
    h = hashlib.sha1(body).hexdigest()
    path = os.path.join(OUT, h[:2], h)
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(body)
    rec = {
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "url": flow.request.pretty_url[:2000],
        "host": host,
        "ctype": ctype,
        "size": len(body),
        "file": path,
    }
    with open(IDX, "a") as fh:
        fh.write(json.dumps(rec) + "\n")

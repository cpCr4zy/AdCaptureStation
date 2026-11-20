"""mitmproxy addon: catch playable-ad creatives (Kingshot targeted).

Saves every suspicious HTML/ZIP response, plus anything that mentions the
Kingshot package id. Writes a jsonl index and raw bodies into ./flows/.
"""
import hashlib
import json
import os

HOME = os.path.expanduser("~")
import re
import time

from mitmproxy import http

BASE = os.path.dirname(os.path.abspath(__file__))
FLOWS = os.path.join(BASE, "flows")
os.makedirs(FLOWS, exist_ok=True)
INDEX = os.path.join(BASE, "hits.jsonl")

MARKERS = [
    b"mraid",
    b"playable",
    b"run.tower.defense",
    b"kingshot",
    b"endcard",
    b"end_card",
    b"admob",
]

TEXTISH = ("text/html", "application/javascript", "application/json", "text/plain")


def _hash(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()[:16]


def response(flow: http.HTTPFlow) -> None:
    if flow.response is None:
        return
    ct = (flow.response.headers.get("content-type") or "").lower()
    body = flow.response.content or b""
    if not body:
        return

    url = flow.request.pretty_url
    size = len(body)
    low = body[:400000].lower()
    tags = [m.decode() for m in MARKERS if m in low]

    is_zip = ct in ("application/zip", "application/x-zip-compressed") or url.lower().endswith(".zip")
    is_html = "text/html" in ct and size > 2000
    # a playable is either a fat html with mraid, or a zip creative
    interesting = (
        ("mraid" in tags and size > 20000)
        or ("run.tower.defense" in tags)
        or ("kingshot" in tags)
        or (is_zip and size > 100000 and ("playable" in url.lower() or "creative" in url.lower() or "ad" in url.lower()))
    )
    if not interesting and not (is_html and len(tags) >= 2):
        return

    ext = ".zip" if is_zip else ".html" if is_html else ".bin"
    name = f"{int(time.time())}_{_hash(body)}{ext}"
    path = os.path.join(FLOWS, name)
    with open(path, "wb") as fh:
        fh.write(body)

    rec = {
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "url": url,
        "host": flow.request.pretty_host,
        "content_type": ct,
        "size": size,
        "tags": tags,
        "file": path,
        "interesting": interesting,
        "ua": flow.request.headers.get("user-agent", "")[:120],
    }
    with open(INDEX, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

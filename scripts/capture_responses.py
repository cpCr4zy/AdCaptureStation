import os

HOME = os.path.expanduser("~")

"""Keep ad-network RESPONSE bodies, so creatives the app never displayed are still visible.

`capture_requests.py` stores only what the app sent. A mediation response, though,
lists the whole waterfall: every candidate ad with its creative URL, whether or not
it won. Saving those bodies means one impression can yield several harvestable
playables instead of one.

AppLovin answers `/1.0/mediate` with gzip-compressed protobuf even when it labels the
body `application/json`, so bodies are sniffed: gzip is unwrapped, URLs are searched
in the raw bytes, and anything that is not clean UTF-8 is kept base64-encoded.

Writes one JSON row per ad response into responses.jsonl:
    ts, url, status, content_type, len, gzip, creative_urls, body | body_b64
"""
import base64
import gzip
import json
import re
import time

from mitmproxy import http

OUT = os.path.join(HOME, "playables/adcapture/responses.jsonl")
MAX_BODY = 400_000

TOKENS = ("applovin", "mediation", "unity", "ironsrc", "vungle", "mbridge",
          "doubleclick", "amazon-adsystem", "auction", "bid", "ads")

URL_RE = re.compile(rb"https?://[^\s\"'\\)\x00-\x1f]{8,300}", re.I)
WANTED = ("playable", "js_load", "_raw", "mraid", "creative", "html", ".zip")


def _interesting(flow: http.HTTPFlow) -> bool:
    host = flow.request.pretty_host.lower()
    return any(t in host for t in TOKENS)


def _unwrap(body: bytes):
    """Return (payload, was_gzip); tolerate double compression."""
    was = False
    for _ in range(2):
        if body[:2] == b"\x1f\x8b":
            try:
                body = gzip.decompress(body)
                was = True
            except OSError:
                break
        else:
            break
    return body, was


def _creative_urls(payload: bytes):
    found = set()
    for raw in URL_RE.findall(payload):
        url = raw.decode("utf-8", "ignore").rstrip(".,;")
        low = url.lower()
        if any(k in low for k in WANTED):
            found.add(url)
    return sorted(found)[:60]


def _is_text(payload: bytes) -> bool:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        return False
    if not text:
        return True
    head = text[:4000]
    control = sum(1 for ch in head if ord(ch) < 9 or 13 < ord(ch) < 32)
    return control < max(4, len(head) // 100)


def response(flow: http.HTTPFlow) -> None:
    if not _interesting(flow) or flow.response is None:
        return
    body = flow.response.content or b""
    if not body:
        return
    payload, was_gzip = _unwrap(body)
    ctype = (flow.response.headers.get("content-type") or "").lower()
    row = {
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "url": flow.request.pretty_url,
        "host": flow.request.pretty_host,
        "status": flow.response.status_code,
        "content_type": ctype,
        "len": len(body),
        "gzip": was_gzip,
        "creative_urls": _creative_urls(payload),
    }
    if _is_text(payload):
        row["body"] = payload[:MAX_BODY].decode("utf-8", "replace")
    else:
        row["body_b64"] = base64.b64encode(payload[:MAX_BODY]).decode()
    with open(OUT, "a") as fh:
        fh.write(json.dumps(row, ensure_ascii=True) + "\n")

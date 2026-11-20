"""mitmproxy addon: keep the *requests* the ad SDKs send.

Responses were already captured (capture_all.py); to replay an ad call we need
the exact method, URL, headers and body the SDK produced, including its
signature parameters.

    mitmdump -s catch_playable.py -s capture_all.py -s catch_century.py \
             -s capture_requests.py --flow-detail 0
"""
import base64
import json
import os

HOME = os.path.expanduser("~")
import time

from mitmproxy import http

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "requests.jsonl")

AD_HOSTS = (
    "ms.applovin.com", "a.applovin.com", "d.applovin.com",
    "googleads.g.doubleclick.net", "pubads.g.doubleclick.net",
    "unityads.unity3d.com", "auction.unityads.unity3d.com",
    "adx.ads.unity.com", "init.ads.unity.com",
    "api.iris.amazon-adsystem", "aax-eu.amazon-adsystem.com",
    "adserver.unity.com", "c2s.unityads", "impression.applvn.com",
    "wsdk-fs.adsbynimbus.com", "ads.yahoo.com", "ads.adsafety",
    "init.giraffads.com", "kinesis.ironsrc.mobi", "adx.wortise.com",
    "gw1.mediation.unity3d.com", "gw-ext.mediation.unity3d.com",
    "i-sdk.mediation.unity3d.com", "o-sdk.mediation.unity3d.com",
)
AD_TOKENS = ("/ad", "v1/api/ad", "mads", "medserv", "adx", "auction", "bid")

MAX_BODY = 200_000


TOKENS = ("ad", "mediation", "applovin", "unity", "ironsrc", "vungle",
          "mbridge", "doubleclick", "amazon-adsystem", "auction", "bid")


def _interesting(flow: http.HTTPFlow) -> bool:
    host = flow.request.pretty_host.lower()
    return host in AD_HOSTS or any(t in host for t in TOKENS)


def request(flow: http.HTTPFlow) -> None:
    if not _interesting(flow):
        return
    raw = flow.request.raw_content or b""
    ctype = flow.request.headers.get("content-type", "").lower()
    if any(t in ctype for t in ("json", "text", "xml", "x-www-form-urlencoded")):
        body = raw.decode("utf-8", "replace")
    else:
        body = ""       # protobuf / binary: only body_b64 is reliable
    row = {
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "method": flow.request.method,
        "url": flow.request.pretty_url,
        "host": flow.request.pretty_host,
        "headers": {k: v for k, v in flow.request.headers.items()},
        "body": body[:MAX_BODY],
        "body_b64": base64.b64encode(raw[:MAX_BODY]).decode(),
        "body_len": len(raw),
    }
    with open(OUT, "a") as fh:
        fh.write(json.dumps(row, ensure_ascii=True) + "\n")

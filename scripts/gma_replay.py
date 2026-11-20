"""Try to replay a captured Google ad request (GMA) to pull creatives on demand.

The GMA request is a plain GET with no signature: `ms`, `blob` and `correlator` are the
only volatile parts and the server tolerates fresh values, unlike the AppLovin `p=`
token. If a replay returns an ad body, this becomes a creative source that needs no
gameplay at all.
"""
import json
import random
import re
import sys

HOME = os.path.expanduser("~")

import requests

CAPTURE = os.path.join(HOME, "playables/adcapture/requests.jsonl")
UA = "Mozilla/5.0 (Linux; Android 13; WayDroid x86_64 Device Build/TQ3A.230901.001; wv)"


def last_gampad():
    rows = [json.loads(l) for l in open(CAPTURE, errors="ignore") if "gampad/ads" in l]
    if not rows:
        raise SystemExit("no gampad request captured")
    row = rows[-1]
    return row["url"], row.get("headers", {})


def retarget(url: str) -> str:
    fresh = {
        "correlator": str(random.randint(10**12, 10**13)),
        "request_id": "".join(random.choice("abcdefghijklmnop") for _ in range(12)),
        "preqs": "0",
        "seq_num": "1",
        "tsi": str(random.randint(10**9, 10**10)),
    }
    for k, v in fresh.items():
        url = re.sub(rf"([?&]{k}=)[^&]*", lambda m: m.group(1) + v, url)
    return url


def main():
    url, headers = last_gampad()
    send = {k: v for k, v in headers.items()
            if k.lower() not in ("host", "content-length", "accept-encoding", "connection")}
    send.setdefault("User-Agent", UA)
    for name, target in (("as captured", url), ("fresh ids", retarget(url))):
        try:
            r = requests.get(target, headers=send, timeout=25)
        except Exception as exc:
            print(f"[{name}] {type(exc).__name__}: {exc}")
            continue
        body = r.text
        print(f"[{name}] {r.status_code} {len(body)}B html={'<html' in body.lower()} "
              f"mraid={'mraid' in body.lower()} iframe={'<iframe' in body.lower()}")
        urls = set(re.findall(r"https://[^\"'\s>]+\.(?:html|js|zip)", body))
        if urls:
            print("   creatives:", list(urls)[:3])
        if "<html" in body.lower():
            open(os.path.join(HOME, "playables/adcapture", f"gma_{name.split()[0]}.html"), "w").write(body)


if __name__ == "__main__":
    main()

"""Try to replay a captured AppLovin `/1.0/mediate` request.

The body is AppLovin's own encrypted envelope (RSA-wrapped AES, keys come from an
SDK handshake), so nothing inside it can be read or patched: the only option is to
resend the exact ciphertext. This probe answers two questions:

  1. does the server accept a replayed ciphertext (HTTP 200 + a body), and
  2. is anything inside that response readable (creative URLs) or is it encrypted too?
"""
import base64
import json
import sys

HOME = os.path.expanduser("~")

import requests

CAPTURE = os.path.join(HOME, "playables/adcapture/requests.jsonl")


def mediate_rows():
    out = []
    for line in open(CAPTURE, errors="ignore"):
        if "ms4.applovin" not in line or "mediate" not in line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def main():
    rows = mediate_rows()
    print(f"captured mediate requests: {len(rows)}")
    pick = rows[-1]
    body = base64.b64decode(pick["body_b64"])
    headers = {k: v for k, v in pick["headers"].items()
               if k.lower() not in ("content-length", "host", "accept-encoding")}
    # negative control: if a corrupted or truncated body also returns 200, the status
    # code proves nothing about the replay being accepted and must not be reported as such
    mutated = bytearray(body)
    mutated[-1] ^= 0xFF
    variants = [("original", body), ("one byte flipped", bytes(mutated)),
                ("truncated 50%", body[: len(body) // 2]), ("empty", b"")]
    for label, payload in variants:
        try:
            r = requests.post(pick["url"], data=payload, headers=headers, timeout=30)
        except Exception as exc:
            print(f"[control {label:16s}] {type(exc).__name__}: {exc}")
            continue
        print(f"[control {label:16s}] {r.status_code} {len(r.content)}B "
              f"head={r.content[:24]!r}")
    print()
    for label, hdrs in (("exact headers", headers), ("minimal headers", {
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": headers.get("User-Agent", "Dalvik/2.1.0")})):
        try:
            r = requests.post(pick["url"], data=body, headers=hdrs, timeout=30)
        except Exception as exc:
            print(f"[{label}] {type(exc).__name__}: {exc}")
            continue
        printable = sum(1 for b in r.content[:2000] if 32 <= b < 127) / max(1, len(r.content[:2000]))
        print(f"[{label}] {r.status_code} {len(r.content)}B printable={printable:.0%} "
              f"ct={r.headers.get('content-type','-')}")
        print(f"          head: {r.content[:120]!r}")


if __name__ == "__main__":
    main()

"""Pull playable creatives straight out of Google's ad server, with no gameplay.

Every GMA ad request the game makes is a plain GET: `ms`, `blob`, `correlator` and the
request ids are volatile but the server accepts fresh values, so a captured request can
be replayed indefinitely. Each replay runs a real auction and answers with the mraid
wrapper plus the winning creative's URL, which is a self-contained playable HTML.

    python3 pull_gma.py --rounds 3          # 3 auctions per captured ad slot
    python3 pull_gma.py --list             # what templates we have

Creatives land in captured/gma/<sha1>.html and are appended to captured/manifest.jsonl
with the same provenance fields the harvester writes.
"""
import argparse
import hashlib
import json
import os

HOME = os.path.expanduser("~")
import random
import re
import time
from collections import Counter

import requests

BASE = os.path.join(HOME, "playables/adcapture")
CAPTURE = os.path.join(BASE, "requests.jsonl")
CAP = os.path.join(HOME, "playables/captured")
GMA = os.path.join(CAP, "misc", "gma")
MANIFEST = os.path.join(CAP, "manifest.jsonl")
UA = "Mozilla/5.0 (Linux; Android 13; WayDroid x86_64 Device Build/TQ3A.230901.001; wv)"

GAMES = {
    "com.run.tower.defense": "Kingshot",
    "com.gof.global": "Whiteout Survival",
    "com.fatmerge.global": "Tasty Travels",
    "com.phs.global": "Last Asylum: Plague",
    "com.centurygames.tilessurvive": "Tiles Survive",
    "com.herogame.gplay.tilessurvive": "Tiles Survive",
    "com.mergegames.gossipharbor": "Gossip Harbor",
    "com.playrix.homescapes": "Homescapes",
    "com.superplaystudios.dicedreams": "Dice Dreams",
}
CENTURY = set(GAMES)

PLAYABLE_URL_RE = re.compile(
    r"(?:https?:)?//[^\s\"'\\)]+?\.(?:html|zip)(?:\?[^\s\"'\\)]*)?", re.I)
PLAYABLE_MARKERS = ("mraid", "cocos", "unity", "playable", "play.google.com", "__zip")
PKG_RE = re.compile(r"play\.google\.com/store/apps/details\?id=([A-Za-z0-9_.]+)")
TITLE_RE = re.compile(r"<title>([^<]{0,80})</title>", re.I)
VOLATILE = ("correlator", "request_id", "preqs", "seq_num", "tsi")


def templates():
    """One replayable URL per distinct ad slot (iu + format + size)."""
    seen, out = set(), []
    for line in open(CAPTURE, errors="ignore"):
        if "gampad/ads" not in line:
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        url = row.get("url", "")
        if "gampad/ads" not in url:
            continue
        iu = re.search(r"[?&]iu=([^&]*)", url)
        fmt = re.search(r"[?&]format=([^&]*)", url)
        sz = re.search(r"[?&]sz=([^&]*)", url)
        cust = re.search(r"[?&]cust_params=([^&]*)", url)
        outp = re.search(r"[?&]output=([^&]*)", url)
        key = (iu.group(1) if iu else "", fmt.group(1) if fmt else "",
               sz.group(1) if sz else "", (cust.group(1) if cust else "")[:40],
               outp.group(1) if outp else "")
        if key in seen:
            continue
        seen.add(key)
        out.append({"key": key, "url": url, "headers": row.get("headers", {})})
    return out


SIZES = ["1024x768", "480x320", "300x250", "1272x747", "768x1024", "640x480"]


def vary_size(url: str, size: str) -> str:
    """A different `sz` is a different ad unit line-up, so the same slot yields new demand."""
    return re.sub(r"([?&]sz=)[^&]*", lambda m: m.group(1) + size, url)


def fresh(url: str) -> str:
    repl = {
        "correlator": str(random.randint(10**12, 10**13)),
        "request_id": "".join(random.choice("abcdefghijklmnop") for _ in range(12)),
        "preqs": "0",
        "seq_num": "1",
        "tsi": str(random.randint(10**9, 10**10)),
    }
    for k, v in repl.items():
        url = re.sub(rf"([?&]{k}=)[^&]*", lambda m: m.group(1) + v, url)
    return url


def creative_urls(body: str):
    body = body.replace("\\/", "/").replace("&amp;", "&")
    urls = {u.rstrip(".,;") for u in PLAYABLE_URL_RE.findall(body)}
    urls = {("https:" + u if u.startswith("//") else u) for u in urls}
    # drop Google's own libraries, keep real creative hosts
    return sorted(u for u in urls if "gstatic.com" not in u and "googlesyndication" not in u)


def download(url: str) -> bytes | None:
    for attempt in range(2):
        try:
            r = requests.get(url, timeout=45, headers={"User-Agent": UA})
        except Exception as exc:
            stats_note(f"download {type(exc).__name__}")
            continue
        if r.status_code in (429, 403):
            time.sleep(5 + attempt * 10)
            continue
        if r.status_code != 200 or len(r.content) < 20_000:
            stats_note(f"download http {r.status_code}")
            return None
        head = r.content[:6000].lower()
        if b"<html" not in head and b"<script" not in head and b"<div" not in head:
            stats_note("download not html")
            return None
        low = r.content[:400_000].lower()
        # Google answers click-throughs with help pages; they are large HTML but not creatives
        if b"support.google.com" in low or b"my ad center help" in low:
            stats_note("download help page")
            return None
        if not any(k.encode() in low for k in PLAYABLE_MARKERS):
            stats_note("download no playable marker")
            return None
        return r.content
    return None


NOTES = []


def stats_note(text: str):
    NOTES.append(text)


def record(blob: bytes, source: str):
    sha = hashlib.sha1(blob).hexdigest()
    path = os.path.join(GMA, sha + ".html")
    if os.path.exists(path):
        return None
    os.makedirs(GMA, exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(blob)
    text = blob[:400_000].decode("utf-8", "ignore")
    pkgs = PKG_RE.findall(text)
    pkg = pkgs[0] if pkgs else ""
    is_century = any(p in CENTURY for p in pkgs)
    title = TITLE_RE.search(text)
    row = {
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "creative": sha,
        "game": next((GAMES[p] for p in pkgs if p in GAMES), "unknown"),
        "pkg": pkg,
        "pkgs": pkgs[:5],
        "century": is_century,
        "size": len(blob),
        "raw": path,
        "project": "",
        "source": source,
        "channel": "gma-replay",
        "title": title.group(1) if title else "",
    }
    with open(MANIFEST, "a") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=1)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--vary-size", action="store_true",
                    help="rotate sz per slot to reach other demand lines")
    args = ap.parse_args()

    tpls = templates()
    print(f"ad slots: {len(tpls)}")
    for t in tpls:
        print("  ", t["key"])
    if args.list:
        return

    stats = Counter()
    for rnd in range(args.rounds):
        for t in tpls:
            headers = {k: v for k, v in t["headers"].items()
                       if k.lower() not in ("host", "content-length", "accept-encoding", "connection")}
            headers.setdefault("User-Agent", UA)
            target = fresh(t["url"])
            if args.vary_size:
                target = vary_size(target, SIZES[rnd % len(SIZES)])
            try:
                r = requests.get(target, headers=headers, timeout=30)
            except Exception as exc:
                stats[f"error {type(exc).__name__}"] += 1
                time.sleep(2 + random.random() * 3)
                continue
            if r.status_code in (429, 503):
                stats["throttled"] += 1
                time.sleep(20 + random.random() * 20)
                continue
            stats[f"http {r.status_code}"] += 1
            if r.status_code != 200:
                continue
            urls = creative_urls(r.text)
            if urls:
                stats["responses with creative url"] += 1
            for u in urls:
                try:
                    blob = download(u)
                except Exception as exc:
                    stats[f"creative error {type(exc).__name__}"] += 1
                    continue
                if not blob:
                    stats["creative fetch failed"] += 1
                    continue
                row = record(blob, u)
                if row:
                    stats["new creatives"] += 1
                    flag = "CENTURY" if row["century"] else "other"
                    print(f"  [{rnd}] +{len(blob)//1024}KB {flag:8s} {row['game']:<20s} {u[:70]}")
                else:
                    stats["duplicates"] += 1
            time.sleep(1 + random.random())
    print("\n" + " | ".join(f"{k}: {v}" for k, v in stats.most_common()))


if __name__ == "__main__":
    main()

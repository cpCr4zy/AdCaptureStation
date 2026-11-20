"""Harvest AppLovin playable creatives seen in the mitm capture.

Every AppLovin "super html" playable is a single self-contained HTML at
`res1.applovin.com/<account>/<creative>_v1_raw.html`; the SDK fetches the twin
`_v1_js_load.js`. This tool:

  1. collects every `_v1_js_load.js` URL from the mitm index + log,
  2. derives the `_v1_raw.html` URL and downloads it,
  3. unpacks the embedded base64 ZIP (`window.__zip`) into `captured/variants/<id>/`,
  4. identifies the advertised app (play.google.com package) and the game name,
  5. appends/updates `captured/manifest.jsonl`, one row per creative variant.

Re-running is cheap: already-harvested creative ids are skipped.

Usage:
    python3 harvest_applovin.py            # fetch + extract + index
    python3 harvest_applovin.py --report   # only print the manifest
"""
import base64
import hashlib
import io
import json
import os

HOME = os.path.expanduser("~")
import re
import subprocess
import sys
import zipfile

BASE = os.path.join(HOME, "playables/adcapture")
CAP = os.path.join(HOME, "playables/captured")
MISC = os.path.join(CAP, "misc")          # everything that is not the gallery lives here
VAR = os.path.join(MISC, "variants")
RAW = os.path.join(MISC, "raw")
MANIFEST = os.path.join(CAP, "manifest.jsonl")
LOG = "/tmp/mitm.log"
INDEX = os.path.join(BASE, "all_index.jsonl")
ZIP_RE = re.compile(r'__zip\D{0,16}?([A-Za-z0-9+/]{500,})')
PKG_RE = re.compile(r"play\.google\.com/store/apps/details\?id=([A-Za-z0-9_.]+)")

# Century Games titles (extend as new packages show up)
GAMES = {
    "com.run.tower.defense": "Kingshot",
    "com.gof.global": "Whiteout Survival",
    "com.fatmerge.global": "Tasty Travels",
    "com.phs.global": "Last Asylum: Plague",
    "com.centurygames.tilessurvive": "Tiles Survive",
    "com.herogame.gplay.tilessurvive": "Tiles Survive",
}
CENTURY = set(GAMES)


RESPONSES = os.path.join(BASE, "responses.jsonl")


def known_creatives():
    """Every AppLovin playable the app either fetched or merely saw in a waterfall."""
    urls = set()
    if os.path.exists(RESPONSES):
        for line in open(RESPONSES, errors="ignore"):
            try:
                row = json.loads(line)
            except Exception:
                continue
            for u in row.get("creative_urls", []):
                m = re.search(r"https://res1\.applovin\.com/[^\s\"']+_v1_js_load\.js", u)
                if m:
                    urls.add(m.group(0).split("?")[0])
            body = row.get("body") or ""
            for m in re.finditer(r"https://res1\.applovin\.com/[^\s\"']+_v1_js_load\.js", body):
                urls.add(m.group(0).split("?")[0])
    if os.path.exists(INDEX):
        for line in open(INDEX, errors="ignore"):
            for m in re.finditer(r"https://res1\.applovin\.com/[^\s\"']+_v1_js_load\.js", line):
                urls.add(m.group(0).split("?")[0])
    if os.path.exists(LOG):
        for m in re.finditer(r"https://res1\.applovin\.com/[^\s\)]+_v1_js_load\.js", open(LOG, errors="ignore").read()):
            urls.add(m.group(0).split("?")[0])
    return urls


def creative_id(url):
    return url.rsplit("/", 1)[-1].split("_v1_")[0]


def existing_ids():
    ids = set()
    if os.path.exists(MANIFEST):
        for line in open(MANIFEST):
            try:
                ids.add(json.loads(line)["creative"])
            except Exception:
                pass
    return ids


def fetch(url, dest):
    if os.path.exists(dest) and os.path.getsize(dest) > 100_000:
        return True
    tmp = dest + ".part"
    r = subprocess.run(["curl", "-sS", "-f", "-o", tmp, url, "--max-time", "90"], capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(tmp) or os.path.getsize(tmp) < 100_000:
        return False
    os.replace(tmp, dest)
    return True


def unpack(html_path, outdir):
    text = open(html_path, encoding="utf-8", errors="ignore").read()
    m = ZIP_RE.search(text)
    if not m:
        return None
    blob = m.group(1) + "=" * (-len(m.group(1)) % 4)
    try:
        data = base64.b64decode(blob, validate=False)
    except Exception:
        return None
    if data[:2] != b"PK":
        return None
    os.makedirs(outdir, exist_ok=True)
    marker = os.path.join(outdir, ".done")
    if not os.path.exists(marker):
        try:
            zipfile.ZipFile(io.BytesIO(data)).extractall(outdir)
        except Exception as exc:
            print("   ! unzip:", exc)
            return None
        open(marker, "w").write(html_path)
    return outdir


def identify(outdir):
    pkgs = {}
    for dirpath, _, files in os.walk(outdir):
        for fn in files:
            if not fn.endswith((".js", ".json")):
                continue
            fp = os.path.join(dirpath, fn)
            if os.path.getsize(fp) > 6_000_000:
                continue
            try:
                text = open(fp, encoding="utf-8", errors="ignore").read()
            except Exception:
                continue
            for p in PKG_RE.findall(text):
                pkgs[p] = pkgs.get(p, 0) + 1
    best = sorted(pkgs.items(), key=lambda kv: -kv[1])
    return [p for p, _ in best]


def main():
    os.makedirs(VAR, exist_ok=True)
    os.makedirs(RAW, exist_ok=True)

    if "--report" in sys.argv:
        rows = [json.loads(l) for l in open(MANIFEST)] if os.path.exists(MANIFEST) else []
        for r in sorted(rows, key=lambda r: (r["game"], r["creative"])):
            print(f'{r["game"]:<20} {r["creative"][:12]:<14} {r["pkg"][:32]:<34} {r["size"]//1024:>7} KB  {r["ts"]}')
        print("variants:", len(rows))
        return

    seen = existing_ids()
    urls = sorted(known_creatives())
    print("applovin creatives seen:", len(urls), "| already harvested:", len(seen))
    new = 0
    for js_url in urls:
        cid = creative_id(js_url)
        raw_url = js_url.replace("_v1_js_load.js", "_v1_raw.html")
        raw_path = os.path.join(RAW, f"{cid}.html")
        have = os.path.exists(raw_path) and os.path.getsize(raw_path) > 100_000
        if cid in seen and have:
            continue
        if not fetch(raw_url, raw_path):
            print("  skip (download failed):", cid)
            continue
        outdir = os.path.join(VAR, cid)
        if not unpack(raw_path, outdir):
            print("  no embedded zip:", cid, "(creative captured raw only)")
            pkgs = sorted(set(PKG_RE.findall(open(raw_path, encoding="utf-8", errors="ignore").read())))
            game = ""
        else:
            pkgs = identify(outdir)
            game = next((GAMES[p] for p in pkgs if p in GAMES), "")
        pkg = pkgs[0] if pkgs else ""
        if not game:
            game = GAMES.get(pkg, "other")
        row = {
            "ts": subprocess.run(["date", "+%Y-%m-%d %H:%M:%S"], capture_output=True, text=True).stdout.strip(),
            "creative": cid,
            "pkg": pkg,
            "game": game,
            "century": pkg in CENTURY,
            "size": os.path.getsize(raw_path),
            "url": raw_url,
            "raw": raw_path,
            "project": outdir if pkgs else "",
            "sha1": hashlib.sha1(open(raw_path, "rb").read()).hexdigest(),
        }
        with open(MANIFEST, "a") as fh:
            fh.write(json.dumps(row) + "\n")
        new += 1
        flag = "  <<< CENTURY" if row["century"] else ""
        print(f'  + {cid[:12]:<14} {game:<20} {pkg[:32]:<34} {row["size"]//1024:>7} KB{flag}')
    print("new variants:", new)


if __name__ == "__main__":
    main()

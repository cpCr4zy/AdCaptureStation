"""Fill in game names that the manifest left as `other`/`unknown`.

The playable itself names nobody, but it carries a Play Store link (or at least the
package id), and the store page answers with `og:title` = "<Game> - Apps on Google Play".
So: extract the package, ask the store, write the name back into the manifest, rebuild
the gallery index.
"""
import html
import json
import os

HOME = os.path.expanduser("~")
import re
import shutil
import sys
import time

import requests

CAP = os.path.join(HOME, "playables/captured")
MAN = os.path.join(CAP, "manifest.jsonl")
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/130 Safari/537.36")

LINK_PATTERNS = [
    re.compile(rb"play\.google\.com/store/apps/details\?[^\"'\\ ]{0,60}?id=([A-Za-z0-9_.]+)"),
    re.compile(rb"play\.google\.com%2Fstore%2Fapps%2Fdetails%3Fid%3D([A-Za-z0-9_.]+)"),
    re.compile(rb"market://details\?id=([A-Za-z0-9_.]+)"),
]
PKG_RE = re.compile(rb"\b(?:com|io|net|org)\.[a-z0-9_]{2,20}\.[a-z0-9_]{2,20}\b")
CENTURY = {"com.gof.global", "com.merge.game.foodstars", "com.phs.global",
           "com.fatmerge.global", "com.run.tower.defense", "com.centurygames.tilessurvive",
           "com.herogame.gplay.tilessurvive"}
LINK_PATTERN_ESC = re.compile(
    rb"play\.google\.com(?:/|\\/|%2F)store(?:/|\\/|%2F)apps(?:/|\\/|%2F)details\??(?:id=)"
    rb"([A-Za-z0-9_.]+)")
OG_RE = re.compile(r'<meta property="og:title" content="([^"]+)"')


def variant_ids(creative: str) -> list[str]:
    """Harvested projects keep the store link in their JS even when the packed file does not."""
    root = os.path.join(CAP, "misc", "variants", creative)
    if not os.path.isdir(root):
        return []
    ids = []
    for dirpath, _, files in os.walk(root):
        for name in files:
            if not name.endswith((".js", ".json", ".html")):
                continue
            try:
                blob = open(os.path.join(dirpath, name), "rb").read()
            except OSError:
                continue
            ids += [m.decode() for m in LINK_PATTERN_ESC.findall(blob)]
    return ids


def packages_in(path: str, creative: str = "") -> list[str]:
    """Package ids mentioned by the creative: a store link first, then bare mentions."""
    if not path or not os.path.exists(path):
        return []
    blob = open(path, "rb").read()
    ids = []
    for pat in LINK_PATTERNS:
        ids += [m.decode() for m in pat.findall(blob)]
    if not ids and creative:
        ids = variant_ids(creative)
    if not ids:
        ids = [m.decode() for m in PKG_RE.findall(blob)]
    # most frequent first: the advertised app is mentioned more than unrelated SDKs
    counts = {}
    for i in ids:
        counts[i] = counts.get(i, 0) + 1
    return sorted(counts, key=lambda k: -counts[k])


def play_title(pkg: str, cache: dict) -> str:
    if pkg in cache:
        return cache[pkg]
    name = ""
    try:
        r = requests.get(f"https://play.google.com/store/apps/details?id={pkg}&hl=en&gl=US",
                         timeout=30, headers={"User-Agent": UA})
        if r.status_code == 200:
            m = OG_RE.search(r.text)
            if m:
                name = html.unescape(m.group(1)).replace(" - Apps on Google Play", "").strip()
    except Exception as exc:
        print(f"   {pkg}: {type(exc).__name__}")
    cache[pkg] = name
    time.sleep(0.6)
    return name


def main():
    dry = "--dry" in sys.argv
    rows = [json.loads(l) for l in open(MAN)]
    todo = [r for r in rows if r.get("game") in ("other", "unknown", "", None)]
    print(f"rows: {len(rows)}, missing a name: {len(todo)}")

    cache, changed, left = {}, 0, []
    for row in todo:
        pkgs = packages_in(row.get("raw", ""), row.get("creative", ""))
        name, pkg = "", ""
        for cand in pkgs[:3]:
            name = play_title(cand, cache)
            if name:
                pkg = cand
                break
        if not name:
            left.append(row["creative"])
            continue
        old = row.get("game")
        row["game"], row["pkg"] = name, pkg
        row["pkgs"] = sorted(set(row.get("pkgs") or []) | set(pkgs[:5]))
        if pkg in CENTURY:
            row["century"] = True
        changed += 1
        print(f"  {row['creative'][:10]}  {old} -> {name}  [{pkg}]")

    if not dry:
        shutil.copy(MAN, MAN + ".bak")
        with open(MAN, "w") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\nrenamed: {changed}, still unnamed: {len(left)}")
    for c in left:
        print("   unnamed:", c)


if __name__ == "__main__":
    main()

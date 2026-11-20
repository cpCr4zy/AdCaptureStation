"""Rebuild manifest.jsonl from the gallery's own metadata comments.

The gallery is the authoritative record: every runnable copy in `playable/` carries a
`<!-- playable-meta: {...} -->` comment injected by `build_gallery.py`. `manifest.jsonl` is a
derived index, and losing or truncating it must not lose the collection — this script restores
the index from the files.

Existing manifest rows win when both exist (they may know the raw payload path and channel);
comments fill the rest. Output is sorted by timestamp so diffs stay readable.

Usage:
    python3 rebuild_manifest.py             # rebuild captured/manifest.jsonl
    python3 rebuild_manifest.py --dry       # report only
"""
import json
import os

HOME = os.path.expanduser("~")
import re
import sys

CAP = os.environ.get("CAPTURED_DIR", os.path.join(HOME, "playables/captured"))
PLAY = os.path.join(CAP, "playable")
MANIFEST = os.path.join(CAP, "manifest.jsonl")
META_RE = re.compile(rb'<!-- playable-meta: (\{.*?\}) -->', re.S)
FIELDS = ("creative", "game", "pkg", "pkgs", "size", "ts", "channel", "century",
          "name_source", "url", "raw", "project", "title")


def from_comments() -> dict:
    out = {}
    for name in sorted(os.listdir(PLAY)):
        if not name.endswith(".html"):
            continue
        with open(os.path.join(PLAY, name), "rb") as fh:
            head = fh.read(4096)
        m = META_RE.search(head)
        meta = {}
        if m:
            try:
                meta = json.loads(m.group(1).decode("utf-8", "ignore"))
            except json.JSONDecodeError:
                meta = {}
        cid = meta.get("creative") or name[:-5]
        meta["creative"] = cid
        meta.setdefault("size", os.path.getsize(os.path.join(PLAY, name)))
        out[cid] = meta
    return out


def from_manifest() -> dict:
    out = {}
    if not os.path.exists(MANIFEST):
        return out
    for line in open(MANIFEST):
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if r.get("creative"):
            out[r["creative"]] = r
    return out


def main():
    dry = "--dry" in sys.argv
    have = from_manifest()
    seen = from_comments()
    merged = {}
    for cid, meta in seen.items():
        row = dict(have.get(cid) or {})
        for k, v in meta.items():
            row.setdefault(k, v)
        merged[cid] = {k: row[k] for k in FIELDS if k in row}
    # rows in the manifest whose gallery copy is gone are kept: they describe deleted captures
    for cid, row in have.items():
        merged.setdefault(cid, row)
    rows = sorted(merged.values(), key=lambda r: (r.get("ts") or "", r["creative"]))
    print(f"comments: {len(seen)} | manifest rows: {len(have)} | merged: {len(rows)}")
    if dry:
        return
    if os.path.exists(MANIFEST):
        open(MANIFEST + ".bak", "w").write(open(MANIFEST).read())
    with open(MANIFEST, "w") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"wrote {MANIFEST}")


if __name__ == "__main__":
    main()

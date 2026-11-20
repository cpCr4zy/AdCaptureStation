"""Rebuild captured/index.html from the gallery files themselves.

No manifest, no database: every runnable copy in `playable/` carries its own metadata in a
`<!-- playable-meta: {...} -->` comment at the top of the file, so the gallery can be
regenerated from the directory alone — copy `playable/` anywhere and it still describes
itself.

Usage:
    python3 make_index.py                 # rebuild index.html next to playable/
    python3 make_index.py --dir /some/path
"""
import html
import json
import os

HOME = os.path.expanduser("~")
import re
import sys

CAP = os.environ.get("CAPTURED_DIR", os.path.join(HOME, "playables/captured"))
META_RE = re.compile(rb'<!-- playable-meta: (\{.*?\}) -->', re.S)

PAGE = """<!DOCTYPE html><html><head><meta charset="utf-8">
<title>Captured playable ads ({n})</title>
<style>
 body{{background:#111;color:#ddd;font:15px/1.45 system-ui,sans-serif;margin:24px}}
 h1{{font-size:20px;font-weight:600}}
 .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px;margin-top:16px}}
 .card{{display:block;background:#1b1b1b;border:1px solid #2a2a2a;border-radius:10px;padding:12px;color:#ddd;text-decoration:none}}
 .card:hover{{border-color:#4a4a4a}}
 .tag{{font-size:11px;background:#2f4f2f;color:#9fdf9f;padding:1px 6px;border-radius:6px}}
 .meta{{color:#999;font-size:12px;margin-top:4px;word-break:break-all}}
 .small{{color:#777}}
</style></head><body>
<h1>Captured playable ads — {n} variants</h1>
<div class="meta">Sorted by game name. Click a card to run the creative (needs a visible tab).</div>
<div class="grid">{cards}</div>
</body></html>"""


def read_meta(path: str) -> dict:
    with open(path, "rb") as fh:
        head = fh.read(4096)
    m = META_RE.search(head)
    if not m:
        return {}
    try:
        return json.loads(m.group(1).decode("utf-8", "ignore"))
    except json.JSONDecodeError:
        return {}


def main():
    root = CAP
    if "--dir" in sys.argv:
        root = sys.argv[sys.argv.index("--dir") + 1]
    play = os.path.join(root, "playable")
    items = []
    for name in sorted(os.listdir(play)):
        if not name.endswith(".html"):
            continue
        path = os.path.join(play, name)
        meta = read_meta(path)
        meta.setdefault("creative", name[:-5])
        meta["_file"] = name
        meta["_kb"] = os.path.getsize(path) // 1024
        items.append(meta)

    # alphabetical by game, case-insensitive; files without metadata sink to the bottom
    items.sort(key=lambda m: ((m.get("game") or "zzzz").lower(), m.get("creative", "")))
    cards = []
    for m in items:
        badge = "CENTURY" if m.get("century") else ""
        tag = f' <span class="tag">{badge}</span>' if badge else ""
        cards.append(f"""
      <a class="card" href="playable/{m['_file']}" target="_blank">
        <div class="row"><b>{html.escape(m.get('game') or 'unknown')}</b>{tag}</div>
        <div class="meta">{html.escape(m.get('pkg') or '')}</div>
        <div class="meta small">{m['creative'][:20]}… · {m['_kb']} KB · {m.get('ts') or ''}</div>
      </a>""")

    out = os.path.join(root, "index.html")
    open(out, "w").write(PAGE.format(n=len(items), cards="".join(cards)))
    named = sum(1 for m in items if m.get("game"))
    print(f"cards: {len(items)} | with game name: {named} | Century: "
          f"{sum(1 for m in items if m.get('century'))} | index: {out}")


if __name__ == "__main__":
    main()

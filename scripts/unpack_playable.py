"""Lay a single-file playable HTML out as a project directory.

Two packagings show up in the captures, and they need different treatment:

* `window.__zip = "<base64>"` — the page carries a whole Cocos/Unity web build as an
  embedded archive. Decoding it restores the real project (scripts, assets, configs);
  the HTML around it is only a bootstrap. This is a lossless unpack.
* no embedded archive — every asset lives inline as a `data:` URI or inside minified JS.
  There is no original project to recover, so the files are *externalised*: identical
  bytes, but split out of the HTML. That is a transformation, and the README says so.

Layout produced per creative:

    captured/projects/<creative>/
        payload.html      the creative exactly as the ad network served it
        project/          unpacked build (zip packaging only), runnable as-is
        assets/           files split out of data: URIs (inline packaging only)
        index.html        runnable entry point
        README.md         what was done and how to tell the two cases apart

Usage:
    python3 unpack_playable.py --all
    python3 unpack_playable.py <creative-id> <creative-id>
"""
import base64
import io
import json
import os

HOME = os.path.expanduser("~")
import re
import shutil
import sys
import zipfile

CAP = os.environ.get("CAPTURED_DIR", os.path.join(HOME, "playables/captured"))
OUT = os.path.join(CAP, "misc", "projects")
ZIP_RE = re.compile(rb'window\.__zip\s*=\s*"([A-Za-z0-9+/=]{200,})"')
DATA_URI_RE = re.compile(r"data:([a-z]+/[a-z0-9.+-]+);base64,([A-Za-z0-9+/=]{64,})", re.I)
EXT = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp", "image/gif": "gif",
       "image/svg+xml": "svg", "audio/mpeg": "mp3", "audio/mp4": "m4a", "audio/ogg": "ogg",
       "audio/wav": "wav", "video/mp4": "mp4", "font/woff2": "woff2", "font/ttf": "ttf",
       "application/json": "json", "application/octet-stream": "bin"}



def safe_extract(zf: zipfile.ZipFile, dest: str) -> int:
    """Unpack, refusing entries that would escape `dest`."""
    n = 0
    for name in zf.namelist():
        target = os.path.normpath(os.path.join(dest, name))
        if not target.startswith(os.path.normpath(dest) + os.sep) and target != os.path.normpath(dest):
            print(f"   skipping unsafe entry: {name}")
            continue
        if name.endswith("/"):
            os.makedirs(target, exist_ok=True)
            continue
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with zf.open(name) as src, open(target, "wb") as out:
            shutil.copyfileobj(src, out)
        n += 1
    return n


def externalise(text: str, outdir: str) -> tuple[str, int]:
    """Split data: URIs into real files, return rewritten text and the file count."""
    assets = os.path.join(outdir, "assets")
    os.makedirs(assets, exist_ok=True)
    made = []

    def repl(m):
        mime, b64 = m.group(1).lower(), m.group(2)
        ext = EXT.get(mime, "bin")
        name = f"{len(made)+1:04d}_{mime.split('/')[-1].split('+')[0]}.{ext}"
        path = os.path.join(assets, name)
        try:
            with open(path, "wb") as fh:
                fh.write(base64.b64decode(b64 + "=" * (-len(b64) % 4)))
        except Exception:
            return m.group(0)
        made.append(name)
        return f"assets/{name}"

    new = DATA_URI_RE.sub(repl, text)
    return new, len(made)


def unpack(creative: str, row: dict) -> tuple[str, int, str]:
    raw = row.get("raw", "")
    dest = os.path.join(OUT, creative)
    if os.path.isdir(dest):
        shutil.rmtree(dest)
    os.makedirs(dest, exist_ok=True)
    shutil.copy(raw, os.path.join(dest, "payload.html"))
    blob = open(raw, "rb").read()

    m = ZIP_RE.search(blob)
    if m:
        data = base64.b64decode(m.group(1) + b"=" * (-len(m.group(1)) % 4))
        if data[:2] != b"PK":
            open(os.path.join(dest, "payload.bin"), "wb").write(data)
            return ("packed-unknown", 0, "embedded blob is not a zip (custom or encrypted codec) — payload kept raw")
        proj = os.path.join(dest, "project")
        os.makedirs(proj, exist_ok=True)
        files = safe_extract(zipfile.ZipFile(io.BytesIO(data)), proj)
        # No entry page is synthesised here on purpose. These builds boot by unzipping the
        # archive in memory (JSZip -> eval of "@"-prefixed entries -> virtual asset resolver),
        # so a plain file tree cannot stand in for that: three different builds were tried
        # with a hand-written index.html and every one died with an obfuscated TypeError.
        # The tree is for reading the build; `payload.html` stays the runnable entry.
        engine = ("cocos3" if os.path.exists(os.path.join(proj, "application.js"))
                  else "cocos2" if os.path.exists(os.path.join(proj, "cocos2d-js-min.js"))
                  else "unknown")
        note = f"{files} files restored ({engine} build); entry stays payload.html"
        return ("unpacked", files, note)
    text = blob.decode("utf-8", "ignore")
    if DATA_URI_RE.search(text):
        new, count = externalise(text, dest)
        open(os.path.join(dest, "index.html"), "w").write(new)
        return ("externalised", count, f"{count} inline data: URIs split into assets/ (transform, not the original build)")
    return ("single-file", 0, "one self-contained file, nothing to split")


def write_readme(dest: str, row: dict, kind: str, note: str) -> None:
    body = f"""# {row.get('game')} — {row['creative'][:10]}

| item | value |
| --- | --- |
| game | {row.get('game')} |
| package | {row.get('pkg') or 'n/a'} |
| creative | `{row['creative']}` |
| channel | {row.get('channel') or 'applovin harvest'} |
| source | {row.get('url') or row.get('source') or 'res1.applovin.com (see manifest)'} |
| packaging | {kind} |
| result | {note} |

`payload.html` is the creative exactly as served. `project/` exists only when the page
carried an embedded archive (lossless unpack). `assets/` exists only when the page kept
everything inline as `data:` URIs (split out, byte-identical, but a transform).

The embedded-archive builds boot by unzipping in memory (JSZip + eval), so the file
tree is for reading the build, not a replacement entry point — run `payload.html`.
"""
    open(os.path.join(dest, "README.md"), "w").write(body)


def main():
    rows = [json.loads(l) for l in open(os.path.join(CAP, "manifest.jsonl"))]
    want = [a for a in sys.argv[1:] if not a.startswith("-")]
    if "--all" in sys.argv or not want:
        picked = rows
    else:
        picked = [r for r in rows if any(r["creative"].startswith(w) for w in want)]
    os.makedirs(OUT, exist_ok=True)
    tally = {}
    for r in picked:
        if not r.get("raw") or not os.path.exists(r["raw"]):
            continue
        kind, n, note = unpack(r["creative"], r)
        write_readme(os.path.join(OUT, r["creative"]), r, kind, note)
        tally[kind] = tally.get(kind, 0) + 1
        print(f"{r['creative'][:10]}  {kind:<12} {n:>4}  {r['game'][:24]:<24} {note}")
    print("\nsummary:", ", ".join(f"{k}={v}" for k, v in sorted(tally.items())))


if __name__ == "__main__":
    main()

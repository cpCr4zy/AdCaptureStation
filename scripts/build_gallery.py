"""Build the runnable gallery from raw payloads: shim + metadata comment + index.

This is the step between "a creative was downloaded" and "the gallery has a card":

    raw/<creative>.html          untouched payload, never modified
        ↓ copy, inject MRAID shim after <head>, inject playable-meta comment after doctype
    playable/<creative>.html     runnable copy (payload + ~1.2 KB shim + 1 comment)
        ↓ make_index.py scans the comments
    index.html                   sorted cards, no manifest needed

Metadata comes from manifest.jsonl; without a manifest row the copy still gets a shim and a
minimal comment built from the file name, so a hand-dropped creative is not lost.

Usage:
    python3 build_gallery.py                 # all manifest rows + any orphan raw files
    python3 build_gallery.py --rebuild       # re-copy even if the gallery copy is newer
    CAPTURED_DIR=/other/captured python3 build_gallery.py
"""
import json
import os

HOME = os.path.expanduser("~")
import re
import sys

CAP = os.environ.get("CAPTURED_DIR", os.path.join(HOME, "playables/captured"))
RAW_DIRS = [os.path.join(CAP, "misc", "raw"), os.path.join(CAP, "misc", "gma"),
            os.path.join(CAP, "raw"), os.path.join(CAP, "gma")]
PLAY = os.path.join(CAP, "playable")
MANIFEST = os.path.join(CAP, "manifest.jsonl")

SHIM = """<script>
(function(){
  var L={};
  function fire(e){ (L[e]||[]).slice().forEach(function(f){try{f()}catch(x){}}) }
  window.mraid={
    getState:function(){return 'default'},
    getPlacementType:function(){return 'interstitial'},
    getScreenSize:function(){return {width:innerWidth,height:innerHeight}},
    getMaxSize:function(){return {width:innerWidth,height:innerHeight}},
    getCurrentPosition:function(){return {x:0,y:0,width:innerWidth,height:innerHeight}},
    getDefaultPosition:function(){return {x:0,y:0,width:innerWidth,height:innerHeight}},
    isViewable:function(){return true}, supports:function(){return true},
    addEventListener:function(e,f){(L[e]=L[e]||[]).push(f)},
    removeEventListener:function(){}, open:function(u){window.open(u,'_blank')},
    close:function(){}, useCustomClose:function(){}, expand:function(){},
    setOrientationProperties:function(){}, playVideo:function(){}, stopVideo:function(){}, pauseVideo:function(){}
  };
  window.mraidBridge=window.mraid; window.ExitApi={exit:function(){}};
  window.super_html={download:function(n){window.open(n,'_blank')},game_ready:function(){}};
  window.super_html_channel="applovin";
  setTimeout(function(){fire('ready');fire('viewableChange');fire('stateChange');fire('sizeChange');},30);
})();
</script>"""

META_KEYS = ("creative", "game", "pkg", "size", "ts", "channel", "century", "name_source", "url")
META_RE = re.compile(rb'<!-- playable-meta: (\{.*?\}) -->', re.S)


def rows() -> dict:
    out = {}
    if os.path.exists(MANIFEST):
        for line in open(MANIFEST):
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            out[r["creative"]] = r
    return out


def raw_files() -> dict:
    """creative id -> raw path, from every place a harvester may have written to."""
    found = {}
    for d in RAW_DIRS:
        if not os.path.isdir(d):
            continue
        for name in os.listdir(d):
            if name.endswith(".html"):
                found.setdefault(name[:-5], os.path.join(d, name))
    return found


def render(raw_path: str, meta: dict) -> bytes:
    data = open(raw_path, "rb").read()
    # drop a previous comment so re-runs do not stack metadata
    data = META_RE.sub(b"", data, count=1)
    comment = b"<!-- playable-meta: " + json.dumps(meta, ensure_ascii=False).encode() + b" -->\n"
    doctype = re.match(rb'<!DOCTYPE[^>]*>\s*', data, re.I)
    cut = doctype.end() if doctype else 0
    data = data[:cut] + comment + data[cut:]
    shim = SHIM.encode()
    # the shim must land inside head, before the creative's own first script
    m = re.search(rb'<head[^>]*>', data, re.I)
    if m:
        return data[:m.end()] + shim + data[m.end():]
    return shim + data


def main():
    rebuild = "--rebuild" in sys.argv
    os.makedirs(PLAY, exist_ok=True)
    known = rows()
    raw = raw_files()
    made = skipped = orphans = 0
    for cid, path in sorted(raw.items()):
        dest = os.path.join(PLAY, f"{cid}.html")
        if not rebuild and os.path.exists(dest) and os.path.getmtime(dest) >= os.path.getmtime(path):
            skipped += 1
            continue
        meta = {k: known[cid].get(k) for k in META_KEYS if known.get(cid, {}).get(k) is not None}
        if os.path.exists(dest):
            # never downgrade good metadata to "unknown" when the manifest is thin:
            # the existing comment may be the only surviving record (see rebuild_manifest.py)
            with open(dest, "rb") as fh:
                m = META_RE.search(fh.read(4096))
            if m:
                try:
                    prior = json.loads(m.group(1).decode("utf-8", "ignore"))
                except json.JSONDecodeError:
                    prior = {}
                if prior.get("game") and prior["game"] != "unknown" and meta.get("game") in (None, "unknown"):
                    meta["game"] = prior["game"]
                for k in ("pkg", "name_source", "url", "ts", "channel"):
                    meta.setdefault(k, prior.get(k))
                meta = {k: v for k, v in meta.items() if v is not None}
        if not meta:
            meta = {"creative": cid, "game": "unknown", "pkg": "", "size": os.path.getsize(path),
                    "ts": "", "channel": "unknown", "century": False}
            orphans += 1
        open(dest, "wb").write(render(path, meta))
        made += 1

    stale = [f for f in os.listdir(PLAY)
             if f.endswith(".html") and f[:-5] not in raw]
    print(f"raw payloads: {len(raw)} | built: {made} | up to date: {skipped} | "
          f"without manifest row: {orphans}")
    if stale:
        print(f"gallery copies with no raw payload: {len(stale)} (kept, not deleted)")
    print(f"playable/: {len([f for f in os.listdir(PLAY) if f.endswith('.html')])} files")


if __name__ == "__main__":
    main()

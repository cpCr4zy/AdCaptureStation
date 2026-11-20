"""Are the captured playable HTML files self-contained?

For every file report: size, inline script/asset bytes, and any external references that
would need a network connection to render (http(s) URLs in src/href/url/fetch/import).
Store links and tracker pings are not dependencies, so they are reported separately.
"""
import os

HOME = os.path.expanduser("~")
import re
import sys

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HOME, "playables/captured/playable")

ASSET_RE = re.compile(
    r"""(?:src|href|data-src)\s*=\s*["']([^"']+)["']"""
    r"""|url\(\s*["']?([^)"']+)["']?\s*\)"""
    r"""|fetch\(\s*["']([^"']+)["']"""
    r"""|import\s+[^;]{0,80}?from\s*["']([^"']+)["']"""
    r"""|(?:XMLHttpRequest|new\s+XMLHttpRequest)[^;]{0,60}?open\(\s*["'][A-Z]+["']\s*,\s*["']([^"']+)["']""",
    re.I)
STORE_RE = re.compile(r"play\.google\.com|apps\.apple\.com|itunes\.apple\.com")
TRACKER_RE = re.compile(r"doubleclick|google-analytics|googletagmanager|applovin\.com/1|"
                        r"unityads\.unity3d\.com|adjust\.com|facebook\.com/tr|appsflyer|"
                        r"impression|tracking|/log|/event", re.I)


def external_refs(text):
    deps, stores, trackers = [], [], []
    for m in ASSET_RE.finditer(text):
        ref = next((g for g in m.groups() if g), "")
        if not ref:
            continue
        low = ref.lower()
        if low.startswith(("http://", "https://", "//")):
            (stores if STORE_RE.search(ref) else trackers if TRACKER_RE.search(ref) else deps).append(ref)
    return deps, stores, trackers


def main():
    rows = []
    for name in sorted(os.listdir(OUT)):
        if not name.lower().endswith((".html", ".htm")):
            continue
        path = os.path.join(OUT, name)
        blob = open(path, "rb").read()
        text = blob.decode("utf-8", "ignore")
        deps, stores, trackers = external_refs(text)
        data_uris = len(re.findall(r"data:[a-z]+/[a-z0-9.+-]+;base64,", text, re.I))
        inline_js = sum(len(s) for s in re.findall(r"<script[^>]*>(.*?)</script>", text, re.S | re.I))
        rows.append({
            "name": name, "kb": len(blob) // 1024,
            "deps": sorted(set(deps)), "stores": len(set(stores)),
            "trackers": len(set(trackers)), "data_uris": data_uris,
            "inline_js_kb": inline_js // 1024,
        })

    standalone = [r for r in rows if not r["deps"]]
    dependent = [r for r in rows if r["deps"]]
    print(f"files: {len(rows)}  self-contained: {len(standalone)}  with external deps: {len(dependent)}")
    print(f"total size: {sum(r['kb'] for r in rows)} KB\n")
    for r in rows:
        flag = "OK " if not r["deps"] else "NET"
        print(f"[{flag}] {r['name'][:44]:<44} {r['kb']:>5}KB  inline-js {r['inline_js_kb']:>4}KB  "
              f"data-uri {r['data_uris']:>3}  store-links {r['stores']}  trackers {r['trackers']}"
              + (f"  deps={len(r['deps'])}" if r["deps"] else ""))
    if dependent:
        print("\n--- external references found (first 8 files) ---")
        for r in dependent[:8]:
            print(f"\n{r['name']} ({r['kb']}KB):")
            for d in r["deps"][:6]:
                print("   ", d[:110])


if __name__ == "__main__":
    main()

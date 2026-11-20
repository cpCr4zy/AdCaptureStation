#!/usr/bin/env bash
# Machine-independent checks for this station. Run from anywhere:
#     bash scripts/verify_station.sh
# CAPTURED_DIR overrides the capture directory. Exit code 0 = every gate passed.
set -u
ST=$(cd "$(dirname "$0")/.." && pwd)
CAP=${CAPTURED_DIR:-$HOME/playables/captured}
fail=0

row() { printf '%-46s %s\n' "$1" "$2"; }

echo "== 1. scripts parse"
bad=0
for f in "$ST"/scripts/*.py; do
    python3 -c "import ast,sys; ast.parse(open(sys.argv[1]).read())" "$f" 2>/dev/null || { echo "   FAIL $f"; bad=$((bad+1)); }
done
row "python scripts parsed" "$([ "$bad" -eq 0 ] && echo ok || echo "$bad failed")"
[ "$bad" -eq 0 ] || fail=1

echo "== 2. every file the docs mention exists"
docok=1
python3 - "$ST" <<'PY' || { fail=1; docok=0; }
import os, re, sys
st = sys.argv[1]
have = set(os.listdir(os.path.join(st, "scripts"))) | set(os.listdir(os.path.join(st, "config")))
missing = set()
docs = [os.path.join(st, f) for f in sorted(os.listdir(st)) if f.endswith(".md")]
for sub in ("docs", "reviews"):
    d = os.path.join(st, sub)
    if os.path.isdir(d):
        docs += [os.path.join(d, f) for f in sorted(os.listdir(d)) if f.endswith((".md", ".txt"))]
for path in docs:
    name = os.path.relpath(path, st)
    text = open(path).read()
    for group in (r"scripts/([A-Za-z0-9_]+\.(?:py|sh))", r"config/([A-Za-z0-9_.-]+)"):
        for ref in re.findall(group, text):
            if ref not in have and not ref.startswith(("requirements", "sudoers-waydroid-lxc.generated")):
                missing.add((name, ref))
if missing:
    for src, ref in sorted(missing):
        print(f"   MISSING {ref}  (referenced in {src})")
    sys.exit(1)
print("   ok")
PY
row "doc references resolve" "$([ "$docok" -eq 1 ] && echo ok || echo 'see above')"

echo "== 3. gallery consistency"
if [ -d "$CAP/playable" ]; then
    files=$(ls "$CAP"/playable/*.html 2>/dev/null | wc -l)
    cards=$(grep -o 'class="card"' "$CAP/index.html" 2>/dev/null | wc -l)
    meta=$(grep -l 'playable-meta' "$CAP"/playable/*.html 2>/dev/null | wc -l)
    row "playable files" "$files"
    [ "$files" -gt 0 ] || { echo "   FAIL no gallery copies found"; fail=1; }
    row "index cards" "$cards"
    row "copies with metadata comment" "$meta"
    [ "$files" -eq "$cards" ] && [ "$files" -eq "$meta" ] || { echo "   FAIL counts disagree"; fail=1; }
    grep -q 'manifest' "$CAP/index.html" && { echo "   FAIL index mentions manifest"; fail=1; }
else
    row "capture dir" "absent ($CAP) — skipped"
fi

echo "== 4. manifest vs gallery"
if [ -f "$CAP/manifest.jsonl" ] && [ -d "$CAP/playable" ]; then
    rows=$(grep -c . "$CAP/manifest.jsonl")
    files=$(ls "$CAP"/playable/*.html 2>/dev/null | wc -l)
    row "manifest rows" "$rows"
    [ "$rows" -eq "$files" ] || { echo "   FAIL rows != files — run rebuild_manifest.py (06.4)"; fail=1; }
fi

echo "== 5. script inventory matches the directory"
if [ -f "$ST/docs/10-state-snapshot.md" ]; then
    on_disk=$(ls "$ST"/scripts | wc -l)
    in_doc=$(python3 - "$ST" <<'PY'
import os, re, sys
st = sys.argv[1]
doc = open(os.path.join(st, "docs", "10-state-snapshot.md")).read()
sec = doc.split("## Script inventory", 1)[1].split("## ", 1)[0]
print(len(re.findall(r"^\| `([^`]+)` \|", sec, re.M)))
PY
)
    row "inventory rows / files on disk" "$in_doc / $on_disk"
    [ "$in_doc" -eq "$on_disk" ] || { echo "   FAIL inventory is stale"; fail=1; }
else
    row "inventory" "docs/10-state-snapshot.md missing"
fi

echo "== 6. no raw identifiers outside the snapshot docs"
# 8+ hex characters are creative ids, package hashes or CA fingerprints; the documents use
# placeholders (<ca-hash>, <creative-id>, <redacted>) and the snapshot may quote an id in prose.
# the leak shape that actually happened: a certificate fingerprint written as <8 hex>.0
hits=$(grep -rnE '\b[0-9a-f]{8}\.0\b' "$ST"/scripts "$ST"/config 2>/dev/null | wc -l)
row "CA fingerprint in scripts/config" "$hits (expected 0)"
[ "$hits" -eq 0 ] || fail=1

if [ "$fail" -eq 0 ]; then
    echo "ALL GATES PASSED"
else
    echo "GATES FAILED"
fi
exit "$fail"

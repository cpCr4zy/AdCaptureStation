# 06 — From captured HTML to a browsable gallery

Two separate jobs: (a) understand what a single-file creative is made of and lay it out as a
project, (b) keep a gallery of runnable copies with names, sorted, self-describing.

## 6.1 A captured playable is often a loader, not a page

Four packagings exist in a real corpus. Classify before doing anything — the classification
decides whether you are restoring the original build or merely splitting a file.

| packaging | detection | measurement on 30 creatives | runs from the tree? |
| --- | --- | --- | --- |
| embedded base64 ZIP | `window.__zip = "<b64>"` decodes to `PK…` | 10 creatives, ~740 files | **no** — boots by unzipping in memory |
| inline `data:` URIs | no archive, `data:<mime>;base64,…` present | 14 creatives, 254 assets | **yes** — verified |
| unknown codec | `window.__zip` decodes, but not to a zip | 3 creatives (Lordrush) | no |
| single file | neither | 3 creatives | n/a |

Input HTML measured 2 400–5 112 KB; embedded payloads decode to 2 000–3 551 KB.

### Why the archive case does not run from a file tree

The tail of the payload contains the boot sequence:

```js
function super_load(){
  c.loadAsync(window['__zip'], {'base64':true}).then(function(e){
    for (var f in e.files){ … window['__super_assets'][g] = h; d--, d==0 && super_boot(); }
  });
}
function super_boot(){
  for (let d in window['__super_assets']) d.startsWith('@') && super_eval(d);
  window['_SUPER_URL'] = function(g,h){ /* resolves asset paths against the map */ };
  … super_boot_engine();
}
```

Assets never exist as files at run time; they are strings inside a JS object and the engine
fetches through a patched URL resolver. The corpus has **10 archive builds**, all ten unpacked; **none of them shipped an `index.html`**
(the tenth, Gummy Drop!, was unpacked later and produced 39 files — also without an entry page).
That is a sample, not a law — check with `ls project/index.html` before assuming. A file tree cannot stand in for the loader, and a
synthesised entry page is not a fix — it was tried on four builds:

| build | engine detail | result of a hand-written `index.html` |
| --- | --- | --- |
| Last Asylum `3f757d2b` | cocos3, no `src/system.bundle.js` | `Uncaught ReferenceError: System is not defined` |
| Kingshot `ad639564` | cocos3 with `system.bundle.js` | `Uncaught TypeError: as[bv(...)] is not a function` |
| Whiteout `19ab6db1` | cocos3 with `system.bundle.js` | `Uncaught TypeError: aD[bQ(...)] is not a function` |
| Foodstars `41cf73c8` | cocos3 with `system.bundle.js` | `Uncaught TypeError: aD[bT(...)] is not a function` |

All four render a black frame with a 300×150 canvas. So: **unpack the archive, keep
`payload.html` as the entry, never generate a launcher.**

Two engine generations appear: Cocos Creator 3.x (`application.js`, `cocos-js/cc.js`,
`src/chunks/`) and Cocos2d-js v2 (`cocos2d-js-min.js`, `@main.js`, `@src/settings.js`,
`assets/resources/`) — one of the nine examined was v2 and even shipped its own `png2base64.py`.

### The unknown codec

Three creatives carry `window.__zip` that decodes to 2 654–2 923 KB starting `cb ff ff 29`,
`cb ff ff 2b`, `cb ff ff 31` — not `PK`, and rejected by zlib, raw deflate, gzip and lzma
(zstd was unavailable, so it is not ruled out). The differing fourth byte looks like a per-file
salt or nonce. Keep the bytes, keep `payload.html`, report the limit; do not brute-force codecs.

## 6.2 Converter usage

`scripts/unpack_playable.py` (copy also lives next to the gallery as
`captured/converter/unpack_playable.py`):

```bash
# preflight: the constant must point at a directory that exists on YOUR machine
grep -n '^GMA\|^CAP\|^RAW\|^VAR\|^OUT' scripts/*.py | grep captured
python3 unpack_playable.py --all              # every row in manifest.jsonl
python3 unpack_playable.py 3f757d2b 5d1a60ce  # by id prefix
CAPTURED_DIR=/other/captured python3 unpack_playable.py --all
```

Output per creative:

```
<base>/projects/<creative>/
    payload.html      creative exactly as served
    project/          unpacked build (archive case only)
    assets/           files split out of data: URIs (inline case only)
    README.md         game, package, channel, source URL, packaging, result
```

Rules the tool follows, and the reasons:

- An archive is **unpacked**; an inline page is **split**. Only the first is a restoration — the
  per-creative README says which one you are looking at. Never call split assets "the original
  project".
- Zip entries that would escape the target directory are skipped and reported.
- Bytes are copied, never re-encoded; a `data:` URI is decoded into exactly the bytes it carried.
- Idempotent: the per-creative output directory is deleted and rebuilt each run.

## 6.3 Gallery: runnable copies, names, order

Layout that works (and that the reference rig converged on):

```
captured/
    index.html          generated, never hand-edited
    manifest.jsonl      capture record (URL, channel, package, game, timestamps)
    playable/           runnable copies: payload + MRAID shim + metadata comment
    converter/          unpack_playable.py, make_index.py, README, findings
```

**Where raw payloads live.** The gallery root must stay readable: `index.html`, `manifest.jsonl`,
`playable/`, `converter/` — plus `misc/`, which is the capture tree. Everything the harvesters
produce goes into `misc/`, so the collection never looks like a pile of working files:

```
captured/
    index.html  manifest.jsonl  playable/  converter/
    misc/                     ← capture tree, invisible from the gallery
        raw/                  untouched payloads, one file per creative  (harvest_applovin.py: RAW)
        gma/                  GMA downloads                                (pull_gma.py: GMA)
        variants/<hash>/      unpacked projects                            (harvest_applovin.py: VAR)
        projects/<hash>/      converter output                      (unpack_playable.py: OUT)
        wv/                   WebView-cache dumps                    (harvest_wvcache.py: OUT)
```

`manifest.jsonl`'s `raw` field must point at the same place the harvester writes — moving the
tree is a code change in two places, and `08` documents the failure it causes if you skip half.
If a creative's raw payload is deleted, its gallery copy and its project tree cannot regenerate
the original bytes: the runnable copy carries the shim, and the CDN URLs rotate.

**The build step, and the script that does it.** `scripts/build_gallery.py` turns every raw
payload into a runnable copy, then `make_index.py` writes the index:

```bash
python3 scripts/build_gallery.py            # raw → playable/ (shim + metadata comment)
python3 scripts/make_index.py               # playable/ → index.html
# or, in one go, with a rebuild of unchanged copies:
python3 scripts/build_gallery.py --rebuild && python3 scripts/make_index.py
```

It reads `manifest.jsonl` for the metadata and scans **both** payload directories — `misc/raw`
(AppLovin) and `misc/gma` (Google replay) — plus plain `raw/`, `gma/` at the capture root. It writes
the comment and the shim in one pass, tolerates a payload with no manifest row (the card says
`unknown`), never downgrades a non-`unknown` name already present in a copy, and never modifies the
payloads.

**Inject a MRAID shim.** Captured creatives expect `window.mraid`, `window.super_html`,
`window.ExitApi`; without them many builds stop at a splash. The shim is ~1.2 KB and goes
**immediately after the opening `<head>` tag, i.e. before the creative's own first `<script>`** —
`build_gallery.py` does exactly that, and `07` rung 4 refers to the same place:

```js
window.mraid={getState:()=>'default', …, open:u=>window.open(u,'_blank'), close(){}, …};
window.mraidBridge=window.mraid; window.ExitApi={exit(){}};
window.super_html={download:n=>window.open(n,'_blank'), game_ready(){}};
window.super_html_channel="applovin";
```

**Name every card after the store page, never after strings inside the creative.** Internal
names are Chinese and engine code is obfuscated. Evidence order:

1. `play.google.com/store/apps/details?id=` in the payload;
2. the same link inside the unpacked project's JS (`assets/main/index.js`) — AppLovin builds cut
   the CTA out of the packed file;
3. `og:title` of the store page (`https://play.google.com/store/apps/details?id=<pkg>&hl=en&gl=US`
   → `<meta property="og:title" content="Royal Kingdom - Apps on Google Play">`) — strip the
   ` - Apps on Google Play` suffix. `<title>` is absent on that page; use `og:title`;
4. the in-creative wordmark plus a Play search, when the creative's `google_play_url` property is
   empty (it is a placeholder filled by the SDK at show time);
5. leave it `unknown` and say so. Do not guess: a name in the gallery reads as a fact.

Give every card a name from evidence, not from a guess (`fix_game_names.py` does this
automatically — it resolves packages to Play `og:title`):

```bash
cd /path/to/AdCaptureStation   # the directory holding scripts/ and docs/
$HOME/playables/botvenv/bin/python scripts/fix_game_names.py     # prints "renamed: N, still unnamed: N"
$HOME/playables/botvenv/bin/python scripts/make_index.py         # cards: N | with game name: N
# gate: "with game name" == cards, or the remainder is explained
```

Record the evidence per row (`name_source`: `play-link`, `in-creative logo`, …). Do not name the
same game twice (`Hero Wars` vs `Hero Wars: Alliance RPG Legend`) — canonicalise all rows from
one source.

**Order: alphabetical by game name**, case-insensitive, creative hash as tiebreak so the layout
is stable across rebuilds:

```python
made.sort(key=lambda r: ((r.get("game") or "zzzz").lower(), r["creative"]))
```

Publisher-first grouping (Century on top) was explicitly rejected in favour of plain A→Z; keep
the publisher as a **badge** on the card, not as a sort key. Emit a badge element only when it
has text — an always-rendered empty `<span class="tag">` shows as a stray green pill on every
plain card.

**Make the gallery self-describing.** One metadata comment per runnable copy, right after the
doctype:

```html
<!-- playable-meta: {"creative":"7234179d6e…","game":"Royal Kingdom","pkg":"com.dreamgames.royalkingdom","size":3752416,"ts":"2026-01-01 12:00:00","century":false,"name_source":"play-link","url":"https://res1…"} -->
```

One line, always. Fields recoverable from a comment: `creative`, `game`, `pkg`, `size`, `ts`,
`century`, `name_source`, `url`. Fields **not** recoverable — `raw`, `project`, `pkgs`, `channel`,
`title` — survive only in the manifest; if it is lost, `rebuild_manifest.py` restores the comment
fields and leaves those empty, which means the converter cannot find the payload for those rows
(harmless for the gallery, fatal for re-unpacking without a fresh capture).

`manifest.jsonl` is one JSON object per line. Schema (all fields optional except `creative`; the
harvesters write the first block, the converter adds `project`, `game`/`name_source` come from the
naming pass):

| field | type | meaning |
| --- | --- | --- |
| `creative` | string | sha1 of the payload — the id used everywhere |
| `ts` | string | `YYYY-MM-DD HH:MM:SS` capture time |
| `game` | string | store title, `unknown` before the naming pass |
| `pkg` | string | advertised package id |
| `pkgs` | string[] | every store package found in the payload |
| `size` | int | payload bytes |
| `raw` | string | absolute path to the payload (`misc/raw/…` or `misc/gma/…`) |
| `project` | string | unpacked tree, `""` when the payload has none |
| `channel` | string | `applovin harvest` / `gma-replay` / `webview-cache` |
| `century` | bool | publisher flag used for the gallery badge |
| `name_source` | string | `play-link` / `in-creative logo` / `creative <title>` / empty |
| `url` | string | source URL the payload came from |
| `title` | string | the creative's own `<title>` (often a build code — never use it as a name) |

The `playable-meta` comment is written on **one line**; parsers tolerate a wrap, but the reference
writers never produce one.

Then the index is built by scanning `playable/*.html` — no manifest, no database:

```bash
python3 scripts/make_index.py                          # default: $HOME/playables/captured
python3 scripts/make_index.py --dir /path/to/copied/captured
CAPTURED_DIR=/other/captured python3 scripts/make_index.py
```

Payoff: copy `playable/` anywhere, run the generator, get the same gallery. Accept the result by
grepping the built index for the string `manifest` — the count must be **0**. Keep any legacy
manifest-driven entry point as a thin wrapper (`runpy.run_path`) so old loops still work.

## 6.4 The manifest is derived, the gallery is the record

`manifest.jsonl` is an index, not the collection: if it is truncated or deleted, the metadata
still exists in the `playable-meta` comments. Restore it instead of re-harvesting:

```bash
python3 scripts/rebuild_manifest.py            # 1. comments + surviving rows -> manifest.jsonl
python3 scripts/build_gallery.py               # 2. rebuild copies that have a payload (only those)
python3 scripts/make_index.py                  # 3. index last, so restored rows are all in it
```

Order matters for a different reason than it first appears: `build_gallery.py` only rebuilds copies
that have a payload, so nothing is overwritten while the manifest is thin — but a row restored *after*
a rebuild would be missing from the index built in between. The script also refuses to downgrade a
non-`unknown` name that already sits in a copy's comment. Restore first, rebuild copies second, build
the index last.

This is not hypothetical: during the writing of this document the manifest was found reduced to a
single row while all 30 gallery copies were intact. `rebuild_manifest.py` restored 30 rows and the
gallery rebuilt with `cards: 30 | with game name: 30`. A design where the files describe
themselves converts a data-loss incident into a two-command repair.

## 6.5 Deleting a creative means four traces

`manifest.jsonl` row (copy to `.bak` first), the raw file, the gallery copy in `playable/`, and
the unpacked project directory — invisible in the gallery. Scale, measured on the one project still
on disk (Gummy Drop!): payload 3 829 696 bytes (3.8 MB) → project tree **7 MB**. The gallery as a whole is 129 MB for 30
creatives (≈4.3 MB each, copies only), so budget roughly double that when every creative is also
unpacked. Then rebuild and
prove it: walk the whole capture tree for files starting with the deleted hash prefix
(`f.startswith(h[:12])`). Orphans in `raw/`, `gma/` or `variants/` survive a manifest edit.
Report the freed bytes; "delete all X" is expected to show the space go.

Filter batch deletes on the `game` field by **prefix**, not equality: legacy spellings
(`Tasty Travels` vs `Tasty Travels: Merge Game`) leave rows behind on `==`.

## 6.6 Byte fidelity — a gallery copy is not the original

The shim adds ~1 162 bytes; writing the copy in text mode also rewrites CRLF to LF (one 4.4 MB
creative lost exactly 1 041 bytes that way). So:

- keep the untouched download (`raw/`, `gma/`);
- prove equivalence by removing the injected `<script>…mraid…</script>` block and comparing
  bytes to the raw — **never by file size**;
- when presenting the artifact, present the raw file or say plainly that the runnable copy is
  payload + shim.

## 6.7 Audit self-containment, do not eyeball it

`scripts/check_selfcontained.py <dir>` reports per file: size, inline JS, embedded `data:` URIs,
store links, trackers and **hard dependencies** (remote `src`/`href`/`url()`/`fetch`/`import`).
A creative passes only when the hard list is empty; store links and tracker pings are not
dependencies. Measured on this corpus: 29 of 30 files pass; exactly one fails — it pulls
`https://mrdoob.github.io/stats.js/...` and calls `new Stats()`, which throws offline. The rest are
single-file builds with the engine inline and art as base64.

Also filter the ad server's click-through pages before they reach the gallery: reject bodies
containing `support.google.com` or `my ad center help` at download time (five such pages
occupied 7.5 MB of the reference gallery).

## 6.8 Acceptance gate

```bash
# fresh build (all payloads present): summary line, then per-creative rows
python3 scripts/unpack_playable.py --all | tail -3      # "summary: unpacked=…, externalised=…"
# reference station (29 payloads deleted): unpack the one that still exists
python3 scripts/unpack_playable.py <creative-id>        # "<id>  unpacked  39  Gummy Drop! …"

python3 scripts/build_gallery.py    # "raw payloads: N | built: N | up to date: N" — N counts
                                    # payloads, not cards; on the reference station N is 1 and the
                                    # other 29 copies are reported as "no raw payload (kept)"
python3 scripts/make_index.py                          # "cards: N | with game name: N | Century: M"
grep -c manifest $HOME/playables/captured/index.html        # 0
ls $HOME/playables/captured/playable/*.html | wc -l          # equals the card count
python3 scripts/check_selfcontained.py $HOME/playables/captured/playable | head -3
```

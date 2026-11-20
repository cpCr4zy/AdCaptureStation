# 08 — Troubleshooting: symptom → cause → fix

Everything here was hit on the reference rig. Sorted by layer. When a symptom has several
possible causes, the first row is the one that actually happened most often.

## Device / Waydroid

| symptom | cause | fix |
| --- | --- | --- |
| `Session: STOPPED`, adb `offline`, black screen | session lifetime (estimate from repeated stops, not a measured distribution) | `session stop` + `session start` as the session user, then `adb connect <guest-ip>:5555` |
| `Failed to get init pid` on lxc-attach | container path not the default | `sudo wd-root '…'` (wrapper has `-P /var/lib/waydroid/lxc -n waydroid` baked in) |
| `Failed to exec "id"` inside lxc-attach | no PATH in the container shell | prefix `export PATH=/system/bin:/system/xbin;` |
| `adb root` → `adbd cannot run as root` / `id` stays `uid=2000` | not supported in Waydroid | use `lxc-attach` for anything privileged |
| `SecurityException: Package <pkg> is currently frozen` | freshly installed package | session restart releases it; `set-inactive` / `device_config` do not |
| black frame, focus on `com.android.documentsui` | file picker owns the screen | `pm disable-user --user 0 com.android.documentsui` |
| game opens `gms …addaccount.ErrorActivity` and exits | needs a Play account | pick another target — unfixable without an account |
| logcat `Exiting empty application process 0:<pkg>` | arm64-only Unity build | pick another target |
| `advertising_id` is `null` | MicroG image, no Play identity | expect lowest-tier inventory; this is an identity limit, not a supply limit |
| permission dialog dims the game and holds focus | `com.android.permissioncontroller` | tap Allow at `(0.5w, 0.497h)`, or pre-grant the permissions |

## adb / screenshots / taps

| symptom | cause | fix |
| --- | --- | --- |
| `screenshot failed; reconnecting adb` | transient adb drop | reconnect and retry; the reference bot survives this by design |
| `libpng error: bad adaptive filter value` | corrupted PNG from `screencap` during a transition | retry the screenshot; treat a single bad frame as noise |
| taps land on the wrong element while the screen looks right | screenshot is display-sized but the app is letterboxed | read `dumpsys window windows \| grep -A40 '<Activity>}'` → `display=[x1,y1][x2,y2]`, restrict CV to that rect |
| input silently dropped | taps faster than the engine processes | 1.9 s between taps |
| vertical swipe throws the app into the shop | vertical drags over a play area are read as an exit gesture | drag along the mechanic's axis (measured: 46/74 vertical drags landed in the shop) |

## mitmproxy

| symptom | cause | fix |
| --- | --- | --- |
| nothing captured, app loads fine | `--set ignore_hosts=<regex>` tunnelled everything | remove it; filter inside the addon |
| addon writes stop mid-run | `get_text()` on protobuf raised `UnicodeEncodeError: surrogates not allowed` inside the hook | base64-encode non-UTF-8 bodies; gate text on strict decode + control-char count |
| a 113 KB ad response yields zero creative URLs | body is gzip protobuf labelled `application/json` | sniff `1f 8b`, gunzip, regex over raw bytes |
| log full of `HTTP/2 protocol error: … RECV_PING …` | routine dropped connections | ignore; monitor `Traceback` instead of `error` |
| CA installed but requests are opaque | app pins certificates or the CA is not in the *system* store | verify the installed name equals `subject_hash_old` of your CA (the reference rig's was `<ca-hash>.0` — yours differs), remount `/system` rw to install |

## Harvesters

| symptom | cause | fix |
| --- | --- | --- |
| only one creative stored though many were captured | dedupe by base64 prefix — every zip starts `UEsDBAoA` | dedupe by sha1 of the decoded payload |
| creative names all `other` / `unknown` | store link missing in the packed file | look in `variants/<hash>/assets/main/index.js`, then fetch `og:title` from Play, then the in-creative wordmark |
| gallery full of ~1.5 MB "help" pages | Google click-through pages pass the size and `<html` checks | reject bodies containing `support.google.com` / `my ad center help` |
| `variants/<hash>/` missing for a captured id | flat `_v1_raw.html` has no `window.__zip` | normal — check `grep -c '__zip' <raw>` before blaming the harvester |
| harvester re-downloads everything each run | ids not compared against the manifest | skip ids already present (`creative_id` from URL) |

## GMA replay

| symptom | cause | fix |
| --- | --- | --- |
| `HTTP 502` on some slots | server-side flake on that slot | per-slot `try/except`; 2 of 286 in the reference run |
| 429 / 503 bursts | rate limiting | exponential backoff with jitter, slow cycle (300 s) |
| every round yields the same ids | pool exhausted for this slot set | rotate slots (new impressions) rather than request volume: 286 requests produced 0 new files |
| different auctions collapse into one key | key built from `iu` only | key on `iu` + `format` + `sz` + `cust_params` + `output` |

## Bot / farm

| symptom | cause | fix |
| --- | --- | --- |
| ad opens then immediately closes | `mean < 45` "loading screen" heuristic pressed BACK on a black ad frame | grace window ~25 s around the watch-ad tap |
| bot taps the store instead of an ad | green `KEEP PLAYING` with a price is a purchase, not a rewarded ad | match the ad button by template (`tpl_keep.png`, 0.90); QUIT is the only exit from a no-ad dialog |
| BACK exits the whole app | BACK on the out-of-space dialog closes the activity | tap QUIT instead; never BACK on that dialog |
| same false close button tapped dozens of times | X detector produced a phantom point | deny-list after 3 failed taps on the same coordinate |
| colour matching finds nothing | OpenCV hue is 0..180 but tolerance computed modulo 360 | `d = min(d, 180-d)`, tol 8/14 |
| red screw detected as hue ~90 | circular median over 0..5 and 175..179 | circular mean via `atan2(sin, cos)` |
| level counter jumps every 12 s | two boxes on screen, hue flips between them | count a level only if the change holds > 25 s |
| board identical after every restart | unfinishable level, not a detection bug | walk the level map (home → PLAY); do not tune thresholds |
| impressions stay at 0 for hours | the game's ads come from level completion only | find a rewarded button, or change target |

## Conversion / gallery

| symptom | cause | fix |
| --- | --- | --- |
| unpacked build shows a black 300×150 canvas | a synthesised `index.html` cannot boot an archive build | delete it; `payload.html` is the entry |
| gallery copy differs from the raw by ~1 KB | MRAID shim injected | expected; compare by removing the shim block, not by size |
| gallery copy differs by ~1 KB *and* has no CRLF | text-mode write normalised line endings | keep the untouched download as the artifact |
| `projects/` gone after cleanup, converter does nothing | converter reads raw payloads that were deleted | re-capture, or keep `raw/` |
| index says "unknown" for a card | metadata comment missing on the runnable copy | regenerate the copy with the shim step, then `make_index.py` |

## Record-keeping

| symptom | cause | fix |
| --- | --- | --- |
| `manifest.jsonl` has far fewer rows than `playable/` has files | the index was truncated or overwritten by a script; the gallery is intact | `python3 scripts/rebuild_manifest.py` then `make_index.py`; if that fails, the `playable-meta` comments can be read by hand |
| a card says `unknown` though the creative is known | the metadata comment was not written (copy built before `build_gallery.py` existed) | rebuild that copy with `build_gallery.py --rebuild`, then name it via `fix_game_names.py` |

## Analysis tools

| symptom | cause | fix |
| --- | --- | --- |
| jadx `OutOfMemoryError`, whole packages missing | multi-dex ad app | `unzip -q apk 'classes*.dex'`, pick the dex by marker, `JAVA_OPTS=-Xmx4g jadx -j 2 one.dex` (raise to 12g only on a 16 GB host) |
| Ghidra finds nothing useful | the target ships no `.so` | check `unzip -l apk \| grep 'lib/'` first; pure-Java app → use jadx |

## Path moves (a silent class of failure)

Moving capture subdirectories is a **code change**, not `mv`:

1. rewrite the `raw` paths inside `manifest.jsonl` — used by `build_gallery.py` to locate the
   payload it copies, by `unpack_playable.py` to convert it, and carried over by
   `rebuild_manifest.py` (which copies the field from surviving rows and leaves it empty for rows it
   restores from comments). The index never reads it. A row with an empty `raw` simply keeps its
   existing gallery copy (`no raw payload (kept)`);
2. update the output constants of every writer (`RAW`/`VAR` in the harvester, `GMA` in the GMA
   puller, `OUT` in the WebView harvester and the converter);
3. prove it — loop over the manifest checking every `raw` exists, then rebuild the gallery.

Skip either half and either the rebuild finds no inputs, or the next harvest silently recreates
`raw/` in the root.

**Moving the rig to another machine.** Nothing in `scripts/` hardcodes a home directory: every path
is derived from `$HOME` (shell) or `os.path.expanduser("~")` (Python), and `ADCAPTURE_DIR` /
`CAPTURED_DIR` override both. So a move needs one step, and it is about the user name only:

```bash
cd /path/to/AdCaptureStation    # the directory holding scripts/ and docs/
bash scripts/configure.sh            # writes $USER into config/sudoers-waydroid-lxc.txt
bash scripts/verify_station.sh       # doc references, gallery counts, no stale identifiers
```

`configure.sh` replaces the `__USER__` placeholder in the shipped sudoers file (the station publishes
a placeholder, never a real account name) and prints the paths the scripts will use. If you keep the
capture tree somewhere else, export `ADCAPTURE_DIR` and `CAPTURED_DIR` instead of editing code.

What reads `manifest.jsonl`'s `raw` field after a move: `unpack_playable.py`, `build_gallery.py`
(for metadata) and `rebuild_manifest.py`. The **index does not** — it is built from the
`playable-meta` comments — so the field matters for conversion, not for the gallery.

Re-run the acceptance gate of `02` and the growth check of `03` afterwards: a half-rewritten path
shows up as "no traffic" or "no cards", never as an error.

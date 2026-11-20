# 10 — State snapshot of the reference rig

Measured on the reference machine. Use it as the target configuration, and as the
baseline for "is my build the same as theirs?".

## Versions

| component | value |
| --- | --- |
| OS / kernel | Arch-based Linux, kernel 7.3.x, Wayland session |
| Waydroid | `/usr/sbin/waydroid` (call as `/usr/bin/python3 /usr/sbin/waydroid`), arch x86_64, vendor MAINLINE, images `/usr/share/waydroid-extra/images`, binder `aidl3` |
| Android in container | SDK 33 (Android 13), abilist `x86_64,x86,arm64-v8a,armeabi-v7a,armeabi` |
| Device address | `<guest-ip>:5555` — read it from `waydroid status`; the host side of the container network is `192.168.240.1` |
| Display | inherits the host panel (4K on the reference rig); target game letterboxed to x 1290..2260 |
| adb | Android Debug Bridge 1.0.41 (platform-tools 37.0.1) at `~/Android/Sdk/platform-tools/adb` |
| mitmproxy | 12.3.1 in `$HOME/playables/mitmvenv` (Python 3.13.13, OpenSSL 4.0.3) |
| bot python | 3.14.9 in `$HOME/playables/botvenv`; numpy 2.5.5, opencv-python-headless 5.1.0.95, pillow 13.0.0, requests 2.34.2, protobuf 7.36.2, cryptography 50.0.2 |

## Identity / inventory limits

```
settings get secure advertising_id    -> null
settings get secure android_id        -> <redacted>
com.android.vending                   present but unauthenticated
```

Consequence: Google serves lowest-tier inventory. Volume of ad requests is not the bottleneck
(one casual game emitted ~185 ad requests in two minutes); identity is.

## Paths and ports

| what | where |
| --- | --- |
| station (this documentation) | `$HOME/playables/AdCaptureStation` — `README.md`, `docs/`, `scripts/`, `config/`, `reviews/` (the game-UI template lives in `private/`, never published) |
| working dir | `$HOME/playables/adcapture` |
| mitmproxy confdir | `$HOME/playables/adcapture/mitmconf` (CA hash name `<ca-hash>`) |
| mitmproxy listener | port **8080** on the host; guest proxy `192.168.240.1:8080` |
| gallery | `$HOME/playables/captured` (`index.html`, `playable/`, `converter/`, `manifest.jsonl`) |
| capture tree | `$HOME/playables/captured/misc/` — now holds exactly one payload (`gma/<creative-id>.html`); `raw/`, `variants/`, `wv/` are recreated by the harvesters on the next run |
| gallery http server for checks | port 8125 (ad hoc, not a service) |
| app-private data on host | `~/.local/share/waydroid/data/data/<pkg>/` (mode 0700, app uid) |
| WebView cache in guest | `/data/data/<pkg>/cache/WebView/Default/HTTP Cache/Cache_Data/` |
| guest CA | `/system/etc/security/cacerts/<ca-hash>.0` (1172 B, root:root 644) |

## The one privileged rule

```
__USER__ ALL=(root) NOPASSWD: /usr/local/sbin/wd-root
```

`wd-root` is `config/wd-root.sh` installed as root: it hardcodes
`lxc-attach -P /var/lib/waydroid/lxc -n waydroid -- /system/bin/sh -c "$*"` and forwards its
arguments. Two honest statements about it:

- it grants **full root inside that one container** (any shell command), not a narrow read right;
- the container pinning comes from the **wrapper**, not from sudoers. The earlier variant
  `… lxc-attach … -n waydroid *` also matched extra `-P` / `-n` flags, and `lxc-attach` honours the
  last value, so on a host with a second container that form could reach it. The wrapper removes the
  ambiguity.

`adb root` is unavailable and must not be planned for. Verify with
`sudo -n -l | grep -c wd-root` → 1.

## mitmproxy invocation actually used

```
--set confdir=$HOME/playables/adcapture/mitmconf
--listen-port 8080 --flow-detail 0
-s catch_playable.py -s capture_all.py -s catch_century.py
-s capture_requests.py -s capture_responses.py
```

## Target specifics (the game used for farming)

```
package    com.quok.screwJam                     (Screw Jam, Rollic)
activity   com.quok.screwJam/com.rollic.elephantsdk.ElephantActivity
ads        interstitial on level completion + out-of-space dialog ("KEEP PLAYING ▶" = rewarded)
bot        scripts/bot_screws.py --minutes N   (Hough circles, hue match, 1.9 s taps)
supervisors scripts/farm_loop.sh 50, scripts/harvest_loop.sh, scripts/gma_loop.sh
```

## Yield actually measured (not estimates)

| metric | value |
| --- | --- |
| distinct creatives in the gallery | 30, from 16 games, 129 MB |
| packaging split | 10 embedded-zip builds (~740 files), 14 inline-`data:` builds (254 assets), 3 unknown codec, 3 single-file |
| GMA slots captured | 96 (one publisher's interstitial/rewarded set) |
| GMA rounds | 5 / 5 / 13 creative URLs, all duplicates; 286 requests with size rotation → 39 URLs, 0 new; one round two days later → 96 × HTTP 200, 2 URLs, **1 new** (Gummy Drop!, 3.8 MB) + 1 duplicate |
| AppLovin farm yield | ~1 creative per 10 min of autonomous play; 12 impressions in the first multi-hour run (`grep -c 'ad on screen' adcapture/run3h.log`) |
| WebView cache | 1 creative per impression, byte-exact; 0 entries while no ad had played |
| creative sizes | HTML 2 400–5 112 KB; embedded payloads 2 000–3 551 KB |
| dead channels | AppLovin mediate (encrypted, negative control passes garbage), app-open (0 fill in 3 runs + `pm clear`), BidMachine RTB (`204` no-fill) |

## Script inventory (`scripts/` — authoritative; `config/addons/` holds staged copies of the five addons)

34 files. `verify_station.sh` fails if this table disagrees with the directory.

| script | role |
| --- | --- |
| `bot_screws.py` | Screw Jam farmer: screenshot → screws → dialogs → ads; harvests every 600 s |
| `bringup.sh` | session → adb → proxy → app, in one shot |
| `build_gallery.py` | payload → `playable/` (MRAID shim + `playable-meta` comment) |
| `capture_all.py` | mitm addon: every ad-related response body → `all/` + `all_index.jsonl` |
| `capture_requests.py` | mitm addon: request method/URL/headers/body → `requests.jsonl` |
| `capture_responses.py` | mitm addon: responses + mined `creative_urls` → `responses.jsonl` |
| `catch_century.py` | mitm addon: AppLovin `res1` URLs → `applovin_urls.txt`; publisher hits → `century/` |
| `catch_playable.py` | mitm addon: content-sniffed HTML/ZIP bodies → `flows/`, index `hits.jsonl` |
| `check.sh` | device fact dump (boot state, proxy, CA, net, apps) |
| `check_selfcontained.py` | audit for remote dependencies |
| `configure.sh` | write your user name into the shipped sudoers placeholder, print effective paths |
| `diag_hue.py` | colour histogram dump for one screenshot |
| `diag_toolbox.py` | candidate-box diagnostic (hue, size, position) |
| `farm_loop.sh` | supervisor: bot in fixed-length cycles, harvest between them |
| `fix_game_names.py` | package → Play `og:title` naming pass |
| `gma_loop.sh` | supervisor: GMA replay every 300 s |
| `gma_replay.py` | one-off: first proof that a GMA slot replays |
| `grab_caches.sh` | one-off: dump the WebView cache from the container |
| `harvest_applovin.py` | `res1` `_v1_raw.html` → payload, unpacked project, manifest row |
| `harvest_loop.sh` | supervisor: both harvesters every 180 s |
| `harvest_wvcache.py` | WebView HTTP cache dump → byte-exact playable |
| `make_index.py` | `playable/` → `index.html`, no manifest needed |
| `mediate_replay.py` | one-off: AppLovin mediate negative control |
| `probe_appopen.py` | one-off: app-open / launch interstitial probe |
| `publish_scan.py` | the audit itself: secrets, identifiers, binaries, git state — stdlib only |
| `publish_scan.sh` | pre-publication audit entry point (delegates to publish_scan.py) |
| `pull_gma.py` | GMA slot replay → creatives, no gameplay needed |
| `rebuild_manifest.py` | `playable-meta` comments → `manifest.jsonl` (repair path) |
| `recover_and_run.sh` | one-off: recover the stack and start a short run |
| `unpack_playable.py` | payload → project tree, four packaging classes |
| `verify_station.sh` | gate bundle: scripts parse, doc references resolve, gallery/manifest counts agree |
| `wd_adbkey.sh` | authorise host adb key inside the container (root) |
| `wd_fix.sh` | repair container eth0 + adbd port |
| `wd_unstick.sh` | recover a stuck session/app |

## Known gaps in this snapshot

- **Only one payload survives.** The 29 earlier originals under `captured/misc/raw` were deleted
  after an audit; `captured/misc/` now holds exactly one payload. Consequence:
  `unpack_playable.py` can rebuild that one creative and nothing else, while the gallery stays
  complete because every copy describes itself. Re-capturing needs a live device plus a fresh
  impression — the CDN URLs rotate (`08`, "Path moves" for keeping the constants in agreement).
- This machine still carries the **older** sudoers rule (`lxc-attach … -n waydroid *`) and has no
  `/usr/local/sbin/wd-root`; the station documents the stricter wrapper form. Installing it means
  replacing the rule, not adding a second one — otherwise both paths stay open.
- `manifest.jsonl` was found truncated to one row during this work (cause not established) and was
  restored from the gallery comments with `rebuild_manifest.py` — the repair path is documented in
  `06`, section 6.4.
- Runnability of the nine archive builds from a file tree is unsolved; the promising path is a
  shim that pre-populates `window.__super_assets` from disk so the stock boot sequence runs
  against files. Until then `payload.html` is the only entry.
- The three unknown-codec payloads need their codec taken from the creative's own runtime, not
  from generic decompressors.

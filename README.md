# AdCaptureStation — a working rig for capturing playable ad creatives

This directory is the specification of a rig that harvests **playable ad creatives** — the
interactive HTML5 "fake gameplay" ads that mobile games show inside a WebView — straight off
a live ad network, and files them as runnable HTML on disk. It is written for an **AI agent**
that has to rebuild, operate or debug the rig, not for a human reading casually: each step
carries the command that verifies it, and each failure mode carries the symptom you will see.

> **Disclaimer.** This is a description of one operator's setup, published so that it can be
> reproduced and debugged. It comes with no warranty and no endorsement: the games, ad networks and
> tools named here belong to their owners, no creative or asset is distributed, and running an
> automated capture channel is your decision and your risk. Read `SECURITY-AND-PRIVACY.md` (sections 4
> and 5) and `NOTICE` before you use it. Code (`scripts/`, `config/`) is MIT, see `LICENSE`; documentation (`docs/`, `README.md`, `SECURITY-AND-PRIVACY.md`, `SECURITY.md`, `NOTICE`, `reviews/`) is CC BY 4.0, see `LICENSE-CC-BY-4.0`.

Measured state of the reference rig: 30 distinct creatives from 16 games, 129 MB, captured over
two days from one emulated Android device — the 30th arrived during the writing of this document,
from a replay of a slot captured two days earlier, which is itself a passing test of the pipeline. Fidelity rules: a payload under `misc/raw` or
`misc/gma` is byte-for-byte what the network served; a runnable copy under `playable/` is that
payload plus an injected MRAID shim (~1.2 KB) and a metadata comment. On the reference station only
one creative remains with its payload (a match-3 title) — the other 29 were deleted after an audit and
survive only as runnable copies. Nothing here is a reconstruction,
and the two directories are never interchangeable — see `docs/06-conversion-and-gallery.md`, section 6.6.

## What the rig actually does

```
  ┌─ Waydroid (Android 13, x86_64) ─────────────────────────────┐
  │  target game with ad SDK  ──►  ad request                   │
  │         ▲                            │                      │
  │         │ taps (adb)                 ▼                      │
  │  bot plays the game            mitmproxy (5 addons)          │
  └───────────────────────────────────────┬─────────────────────┘
                                          │ URLs + bodies
                          ┌───────────────▼──────────────┐
                          │ harvesters                   │
                          │  • GMA replay (no gameplay)  │
                          │  • AppLovin res1 extraction  │
                          │  • WebView cache dump        │
                          └───────────────┬──────────────┘
                                          ▼
                          captured/playable/*.html + index.html
```

Five channel attempts, three of which produce files and two that are closed — each fails
differently, so all are recorded (details and yield numbers in `docs/04-creative-channels.md`):

| channel | needs gameplay? | yield observed | status |
| --- | --- | --- | --- |
| Google GMA slot replay | no (after one captured `gampad/ads` request) | 2–13 URLs per round over 96 slots, nearly all duplicates; 1 genuinely new file in the last round | **best channel, start here** |
| AppLovin `res1` harvest after a real impression | yes | ~1 creative per 10 min of autonomous play | works, slow |
| WebView HTTP cache dump | yes (needs one impression) | 1 creative per impression, byte-exact | works, no setup risk |
| AppLovin `mediate` replay | no | nothing readable | **closed** — encrypted envelope |
| App-open / launch interstitial | no | 0 fills in 3 runs + `pm clear` | closed on this inventory |

## Before you publish this anywhere

The station is written to be shareable: no captures, no keys, no device identity, no personal paths.
`SECURITY-AND-PRIVACY.md` records what was removed for that and what stays on purpose; two scripts
gate it:

```bash
bash scripts/publish_scan.sh      # secrets, identifiers, binaries -> must print CLEAN
bash scripts/verify_station.sh    # documents and collection consistency -> ALL GATES PASSED
```

Read `SECURITY-AND-PRIVACY.md` before the first push: it also states the legal boundary (the creatives
belong to their advertisers and are never part of this repository).

## Reading order

Every path in this station is written **relative to the station root** — the directory that contains
this README: the numbered documents live in `docs/`, the code in `scripts/`, the fixed snippets in
`config/`. Commands that need a concrete directory show `/path/to/AdCaptureStation`.

| file | read it when |
| --- | --- |
| `docs/01-host-and-toolchain.md` | before installing anything; lists every package and version |
| `docs/02-waydroid-device.md` | you need a device that can be scripted over adb |
| `docs/03-traffic-capture.md` | you need to see and store the ad SDK's HTTP traffic |
| `docs/04-creative-channels.md` | you need creatives; contains the acceptance test per channel |
| `docs/05-game-farm.md` | you intend to drive a game automatically to trigger impressions |
| `docs/06-conversion-and-gallery.md` | you have HTML files and want a browsable, sorted gallery |
| `docs/07-verification-playbook.md` | before you report anything as "captured" or "works" |
| `docs/08-troubleshooting.md` | something silently does nothing — symptom → cause → fix |
| `docs/09-rebuild-plan.md` | you are building this from zero; ordered plan with gates |
| `docs/10-state-snapshot.md` | you need the exact measured configuration of the reference rig |
| `scripts/` | the actual code, copied from the rig — read it, do not retype it |
| `config/` | the exact commands and permission snippets that cannot be guessed |
| `reviews/` | the review rounds, their verdicts and the accepted deviations (raw transcripts stay in `private/`) |
| `.github/workflows/publish-scan.yml` | CI gate: pre-publication scan, gitleaks, author and history checks |
| `SECURITY-AND-PRIVACY.md` | what is deliberately not published, what the audit removed, pre-push checklist |
| `SECURITY.md` | how to report a leak in this repository |

## File map: what each artefact is and who creates it

| artefact | path | created by |
| --- | --- | --- |
| capture record (derived) | `captured/manifest.jsonl` | the harvesters append rows; if it is lost, `rebuild_manifest.py` restores it from the gallery comments |
| raw payloads | `captured/misc/raw/*.html`, `captured/misc/gma/*.html` | the same harvesters, unchanged bytes |
| unpacked projects | `captured/misc/variants/<id>/` | `harvest_applovin.py` (`window.__zip`) |
| converted trees | `captured/misc/projects/<id>/` | `unpack_playable.py` |
| WebView dumps | `captured/misc/wv/` | `harvest_wvcache.py` |
| runnable copies | `captured/playable/<id>.html` | `build_gallery.py` (raw + shim + meta comment) |
| gallery | `captured/index.html` | `make_index.py` |
| proxy log | `adcapture/mitm.log` | `config/mitmdump-start.sh` |
| bot log | `adcapture/run3h.log` | `farm_loop.sh` → `bot_screws.py` |
| prose captures | `adcapture/all/`, `adcapture/century/`, `adcapture/flows/` | the three catcher addons |
| request/response records | `adcapture/requests.jsonl`, `adcapture/responses.jsonl` | `capture_requests.py`, `capture_responses.py` |
| CTA template | your own `templates/tpl_keep.png` (not shipped — game UI crop, see `docs/05-game-farm.md`) | you, once per game |
| observed AppLovin URLs | `adcapture/applovin_urls.txt` | `catch_century.py` (one line per `_v1_js_load.js`) |
| catcher indexes | `adcapture/all_index.jsonl`, `adcapture/century_index.jsonl`, `adcapture/hits.jsonl` (+ `adcapture/flows/` bodies) | `capture_all.py`, `catch_century.py`, `catch_playable.py` |
| GMA run log | `adcapture/gma_pull.log` | `gma_loop.sh` / manual `pull_gma.py` |
| harvest log | `adcapture/harvest.log` | `harvest_loop.sh` (both harvesters) |
| probed-games registry | `adcapture/tested_games.json` | written by hand or by the fetcher (`05.1`) |
| CA + confdir | `adcapture/mitmconf/` | first `mitmdump --set confdir=…` run (`docs/02-waydroid-device.md`, `docs/03-traffic-capture.md`) |

Every path inside `scripts/` is resolved from `$HOME` (or `ADCAPTURE_DIR` / `CAPTURED_DIR`), so they run from any cwd — but run them **from this
station directory** (the one holding `scripts/`) when you use the relative `scripts/…`
form in the docs, or use the absolute path.

## Hard rules (violating these wastes hours or produces fake data)

1. **Never present a reconstruction as a captured creative.** A GitHub clone of the game's
   mechanic is not the artifact. The artifact is a file whose bytes came from the network.
2. **HTTP 200 proves nothing.** Every replay attempt must come with a negative control: send
   a corrupted body, an empty body, a truncated body. If the answer is the same, the endpoint
   is not validating and you have learned nothing (`docs/04-creative-channels.md`, AppLovin section).
3. **A file existing is not a capture.** Open it in a real browser, let it render, screenshot
   it, and confirm the game loop runs (`docs/07-verification-playbook.md`).
4. **A gallery copy is not the original payload.** The runnable copy has a MRAID shim injected
   (~1.2 KB) and may have been written in text mode, which rewrites CRLF to LF. Keep the
   untouched download and prove equivalence by removing the injected script block and
   comparing bytes — never by file size.
5. **Do not tap blindly to "see what happens".** In the reference target a mis-tap opens the
   in-app store and stalls the level; a purchase dialog is what you get for guessing.
6. **Do not invent a launcher page for an unpacked build.** Archive builds boot from memory;
   four hand-written `index.html` attempts all died (`docs/06-conversion-and-gallery.md`).
7. **Respect the rate and policy limits (`docs/04-creative-channels.md`, section 4.6).** No fabricated impressions, one
   device identity, slow replay cycles (300 s), and stop a channel when a round returns only
   duplicates. Automating an ad server is not a licence to scale it.

## Prerequisites, in one block

```
Linux with Wayland session (reference: CachyOS, kernel 7.3.x)
waydroid + waydroid-extra images (Android 13 image, MAINLINE vendor)
Android SDK platform-tools (adb)
Python 3.13.13 for mitmproxy, 3.14.9 for the harvest/bot scripts (tested pair, see `docs/01-host-and-toolchain.md`)
mitmproxy 12.x
optional: jadx (APK analysis), Ghidra (only if the target ships native .so)
~10 GB free disk (images ~5 GB, captures 100–700 MB), 8 GB RAM, 4+ cores
```

Exact versions, paths and the one privileged rule the rig needs: `docs/10-state-snapshot.md`.

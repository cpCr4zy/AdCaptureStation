# 09 — Rebuild from zero: ordered plan with gates

For an agent building this rig on new hardware. Each phase lists what to do, the gate that must
pass before continuing, and the decision it feeds. Reference timings are from the original build
(one emulated device, one target game).

Total wall clock: **~4–6 h** to first captured creative, most of it unattended.

## Phase 0 — decide before installing (15 min)

| question | consequence |
| --- | --- |
| Do you only need creatives, not a farm? | skip the bot entirely: GMA replay needs no gameplay (`04`, section 4.1) |
| Do you have an ad-spy account (BigSpy / SocialPeta / AppMagic)? | a single account can replace the whole capture rig for a specific creative — offer it before building |
| Is a real device available with USB debugging? | Waydroid is the cheap path, but a phone gives a Play identity and therefore richer inventory |
| Disk free | images ~5 GB + captures 100–700 MB; `all/` grows fast |

Gate: a written answer to all four. Building without answering #2 wastes hours.

## Phase 1 — host toolchain (30 min)

1. `pacman -S waydroid waydroid-image android-tools curl unzip zip openssl` (or equivalents).
2. Two venvs: `botvenv` (opencv, numpy, requests, pillow, protobuf, cryptography) and `mitmvenv`
   (mitmproxy). Do not merge them.
3. Verify with the three commands at the end of `docs/01-host-and-toolchain.md`.

Gate: `botvenv python -c "import cv2"`, `mitmvenv/bin/mitmdump --version`,
`adb version` all succeed.

## Phase 2 — device (30–60 min, mostly download)

1. `sudo waydroid init -s MAINLINE`, `systemctl enable --now waydroid-container`.
2. `waydroid session start` as the user (Wayland env set).
3. `adb connect <container-ip>:5555`; if `offline`, run `scripts/wd_adbkey.sh` as root.
4. Install the target game — **before** granting the privileged rule (step 6 of this phase) and
   before trusting any system CA to the container. For mirror-sourced APKs use a throwaway session:
   install, probe, and wipe it with `$ADB uninstall <pkg>` if you do not keep the title (an
   uninstall removes the package and its data; `rm -rf` on the host copy fails silently because that
   directory is owned by the app uid, not by you). Check with
   `$ADB shell "pm list packages | grep -c <pkg>"` → `0`. Play-store APKs often arrive as XAPK (a zip of split APKs):

   ```bash
   mkdir -p /tmp/xapk && unzip -o -q app.xapk -d /tmp/xapk
   ls /tmp/xapk/*.apk                       # base + split_config.<abi>.apk + split_config.<dpi>.apk
   $ADB install-multiple /tmp/xapk/*.apk    # one command, base first in the list is not required
   $ADB shell "pm list packages | grep -c <pkg>"      # 1
   ```
   Where to get the XAPK: sources such as `d.apkpure.com/b/APK/<pkg>?version=latest` (as used on the
   reference rig), APKMirror, or `adb pull` from a device that already has it. Never install a
   "playable preview" harness — those do not contain creatives.

   The APK from a mirror is the only unverified input in this whole build. `apksigner` tells you who
   signed the file, but not whether that signer is legitimate — Play does not publish signer
   fingerprints. What is actually executable:

   ```bash
   ~/Android/Sdk/build-tools/*/apksigner verify --print-certs /tmp/xapk/base.apk | head -5
   # legitimate comparison: the same command on a copy pulled from a device that installed from Play
   #   $ADB pull $(adb shell pm path <pkg> | sed 's/package://') /tmp/from-device.apk
   ```

   If you have neither a device copy nor an owner's Play Console fingerprint, record the state
   honestly: *source unverified, risk accepted*, and prefer `adb pull` from a phone over a mirror.

   XAPKs often carry game data that `install-multiple` ignores:

   ```bash
   ls /tmp/xapk/Android/obb/*/ 2>/dev/null &&      $ADB push /tmp/xapk/Android/obb/<pkg> /sdcard/Android/obb/
   $ADB shell "du -sh /sdcard/Android/obb/<pkg>"     # sizes must match the XAPK
   ```

   Symptom of the missing OBB step: the game installs, starts, and dies at the loading screen.
5. Triage the target (`05`, section 5.1). **If it demands a Play account or is arm64-only Unity,
   stop and pick another game now.**
6. Only after the target is known to run: install the **sudoers rule** (`02`). The CA does not exist
   yet — it is minted in Phase 3, and that is where it gets installed. An untrusted APK therefore
   never shares a session with a container-root rule and a trusted system CA.

Gate:

```bash
$ADB shell "cmd package resolve-activity --brief <pkg> | tail -1"   # prints pkg/activity
$ADB shell "am start -n <pkg>/<activity>"
$ADB shell "dumpsys window | grep -m1 mCurrentFocus"                # that activity owns the screen
```

…and one `input tap` visibly changes the screen.

## Phase 3 — capture layer (30 min)

1. First run of mitmdump with `--set confdir=<dir>` to mint the CA.
2. Install the CA into the Android **system** store (`02`) and verify the file hash name.
3. `settings put global http_proxy 192.168.240.1:8080`.
4. Start mitmdump with the five addons (`03`).
5. Play 2–3 minutes by hand.

Gate: `requests.jsonl` grows; `grep -c 'Traceback' mitm.log` is 0; at least one ad host appears.

## Phase 4 — first creative, the fast channel (15 min)

0. **Preflight the constants.** Every harvester has a hardcoded base path; on a new machine they
   point at nothing. Fix before running, then prove it:

   ```bash
   grep -n '^GMA\|^CAP\|^RAW\|^VAR\|^OUT\|^MANIFEST' scripts/*.py | grep -i captured
   ls -d <the directory you set> || echo "constant points at nothing"
   ```
1. `python3 scripts/pull_gma.py --list` — it reads `requests.jsonl` for `gampad/ads` slots.
2. `python3 scripts/pull_gma.py --rounds 1`.
3. Open one downloaded file in a browser and confirm it plays.

Gate: a file that renders and plays, not a help page (`07`, rung 4).

If the target game uses no GMA inventory, skip to Phase 5: the res1 and WebView channels need one
real impression.

## Phase 5 — farm or manual impressions (1–3 h unattended)

Option A (recommended if a rewarded button exists): press "watch ad to continue" in a loop.
Option B: let the bot play levels (`scripts/bot_screws.py --minutes 50` under
`scripts/farm_loop.sh`).

In parallel, always:

```bash
scripts/harvest_loop.sh      # every 180 s: res1 harvest + WebView cache dump
```

Gate: `grep -c 'ad on screen' run3h.log` increases, and `manifest.jsonl` gains rows within
minutes of an impression.

## Phase 6 — gallery and conversion (30 min)

1. `scripts/unpack_playable.py --all` (needs raw payloads; writes `projects/`).
2. `scripts/build_gallery.py` — raw → `playable/`, injecting the MRAID shim and the
   `playable-meta` comment in one pass (this is the step that used to be manual).
3. `scripts/make_index.py` — `playable/` → `index.html`.

Gate: card count == file count == generator count; `grep -c manifest index.html` is 0; one card
opens and plays.

## Phase 7 — close the loop (ongoing)

- Supervise: session (restarts every ~40–60 min — an estimate from this rig, not a measurement) → adb → app → bot. A loop that restarts the stack is
  worth more than any bot improvement.
- Harvest on a schedule independent of the bot cycle.
- Re-run the GMA replayer slowly (300 s) to catch campaign rotation.
- Prune `all/` periodically; keep `raw/`, `manifest.jsonl`, `requests.jsonl`.

## What can be skipped, and what cannot

| can skip | cannot skip |
| --- | --- |
| the bot, if you only need GMA creatives | CA in the **system** store |
| APK decompilation, if no replay surface is needed | `requests.jsonl` growth check before any harvesting |
| the project-tree converter, if you only want the single file | a browser test of the captured file |
| WebView-cache channel, if res1 works | keeping the untouched raw payload next to the gallery copy |

## Cost of getting it wrong (measured)

| mistake | cost |
| --- | --- |
| `ignore_hosts` set | 40 min of capture that wrote nothing |
| trusting `content-type` | a 113 KB creative-bearing body mined to zero URLs |
| `mean<45` ad heuristic | the ad the bot had just triggered was cancelled with BACK |
| green button = ad assumption | a purchase flow opened instead of an ad |
| synthesising `index.html` for archive builds | four failed builds before the rule was written down |
| deleting `misc/raw` before checking uniqueness | the only byte-exact originals are gone; a re-capture needs a live device plus a fresh impression |

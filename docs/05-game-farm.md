# 05 — Driving a game to make impressions appear

Needed only for the AppLovin and WebView-cache channels. Background knowledge: in a casual puzzle
game an **interstitial fires on level completion**, not on cold start. In the reference target the
HUD has no rewarded refill (the heart icon opens the IAP page), but the **out-of-space dialog does
offer a rewarded `KEEP PLAYING ▶`** — that button, not better play, turned out to be the best
creative supply on this target.

Measured reality check before you start: the reference farm produced **12 impressions over
several hours** of autonomous play, while a "watch ad to continue" button was later worth
~1 creative per 10 minutes. Find a rewarded button before teaching a bot to play better.

## 5.1 Triage a target in ~2 minutes (saves hours)

```bash
$ADB shell "am start -n <pkg>/<activity>"; sleep 20
$ADB shell "dumpsys window | grep -m1 mCurrentFocus"
$ADB logcat -d -t 200 | grep -E 'Exiting empty application|SecurityException|FATAL'
```

Abort immediately if you see:

| signature | meaning |
| --- | --- |
| `com.google.android.gms … addaccount.ErrorActivity` | game demands a Play account; it will exit |
| `com.android.vending … UnauthenticatedActivity` | same, through the store |
| `Exiting empty application process 0:<pkg>` | arm64-only Unity build that will not run under the bridge |
| bounce back to launcher within seconds | native crash |

Also check which SDKs the target ships — a game with AdMob only leaves the unsigned-replay path
closed, however many networks it lists:

```bash
unzip -l app.apk | grep 'lib/'                         # native code present?
unzip -q app.apk 'classes*.dex'
grep -c -a 'com.google.android.gms.ads' classes*.dex
grep -c -a 'com.applovin' classes*.dex
```

Keep a registry of probed packages so each new run picks something untested (this station does not
ship a package fetcher — download the XAPK by hand, or `adb pull` it from a phone, then record it).
Path and schema:
`$HOME/playables/adcapture/tested_games.json`, a JSON array of objects with exactly these
fields — `pkg` (string, the Android package), `name` (string), `date` (ISO date of the probe),
`impressions` (integer), `verdict` (`works` | `no-ads` | `crashes` | `needs-account` | `arm64-only`).
The fetcher skips any package already listed.

## 5.2 Target-specific mechanics (Screw Jam, `com.quok.screwJam`)

Reference implementation: `scripts/bot_screws.py` (Screw Jam, activity
`com.rollic.elephantsdk.ElephantActivity`). The rules below are what the code encodes, and
each one exists because the naive version broke.

**Board and taps**

- Screw heads are found with Hough circles (radius ~24–40 px) plus a chroma check; the board
  colour is the reference hue, taps only go to screws whose hue matches the box within
  tolerance.
- OpenCV hue is **0..180**, not 0..360. A modulo-360 comparison doubles every tolerance. The
  reference uses `d = min(d, 180 - d)` with tolerance 8 (match) and 14 (loose) in OpenCV units,
  and a circular mean via `atan2(sin, cos)` — a plain median over red hues 0..5 and 175..179
  returns ~90 and matches nothing.
- Tap spacing **1.9 s**. Unity silently drops faster input.
- Batch at most 6 taps per iteration; the board state changes.

**The rewarded button: how to find it and how to match it**

The reliable ad trigger is the out-of-space dialog's right-hand `KEEP PLAYING ▶` (a play glyph, no
price). Matching it:

1. capture the dialog once: `$ADB exec-out screencap -p > /tmp/frame.png`
2. crop the button with any viewer (`ImageMagick`: `magick /tmp/frame.png -crop WxH+X+Y button.png`)
3. save it next to the bot as `templates/tpl_keep.png` — **the image is not shipped**: the reference
   crop (18 337 bytes) is a piece of the game's own UI, so the public station keeps
   only this recipe. Crop your own; the exact size will differ, so validate the score below instead of
   comparing bytes
4. match with `cv2.matchTemplate` and a **0.90** threshold, then tap the match centre

Two properties to keep in mind: the threshold is not cosmetic (at 0.75 the tan board itself matches
and the bot taps nothing), and **template matching is scale-dependent** — a template cropped on a
3840×2160 guest will not match on a 1280×720 one. Re-crop on your own resolution and verify the
score on a known frame before trusting the bot:

```bash
$HOME/playables/botvenv/bin/python - <<'EOF'
import cv2
img = cv2.imread('/tmp/frame.png'); tpl = cv2.imread('templates/tpl_keep.png')
r = cv2.matchTemplate(img, tpl, cv2.TM_CCOEFF_NORMED)
print('best score', round(float(r.max()), 3))     # expected >= 0.90 on the dialog
EOF
```

**Dialogs — the part that eats farms**

- The out-of-space dialog has a red wide button and a right-hand `KEEP PLAYING ▶`.
  - Red wide = **QUIT** → drops you into the shop. Do not tap it while hunting for ads.
  - `KEEP PLAYING ▶` with a *play glyph* = rewarded ad (good).
  - `KEEP PLAYING` with a **price** (e.g. `250` next to the coin counter) = **purchase**. Tapping
    it with fewer coins opens the store. A colour heuristic cannot tell these apart: match the
    ad button by template (`tpl_keep.png`, threshold 0.90; at 0.75 the tan board matches and the
    bot taps nothing).
- **BACK on the dialog exits the app** (focus lands on `com.android.launcher3`). The only control
  that advances the game from a no-ad dialog is QUIT.
- Shop/offer screens paint the play area blue: sample the lower half (levels ≈ 0.02 blue
  fraction, shop ≈ 0.45) and close with the X, falling back to BACK only if no X is found.
  Keep a deny-list of X coordinates that never work — one false X at `(1965, 553)` looped 49
  times before the list existed.

**Screens that look broken but are not**

- **Dark screen ≠ loading done.** Creatives open on a black frame. A `mean < 45` "loading
  screen" heuristic pressed BACK on the ad it had just triggered, cancelling the impression.
  Give the watch-ad tap a grace window of ~25 s during which dark only means "still loading".
- A dark frame after level completion is the level-end screen waiting for a tap: tap the centre
  once, and restart the app only after ~6 consecutive dark frames.
- `dumpsys window` focus on `com.android.documentsui` means the file picker owns the screen:
  `pm disable-user --user 0 com.android.documentsui`.

**Level accounting**

The target hue flips between two boxes on the same screen, which looks like a level change. Only
count a level when the change holds (`time.time() - last_level_at > 25`). Diagnose with a hue
dump (`scripts/diag_hue.py`, `scripts/diag_toolbox.py`) before touching tolerances: on the
reference frame there was exactly one candidate box at hue 110.7 occupying 47 % of the width,
so the 4.05 ↔ 102.5 jumps were real box switches, not detection noise.

**Soft lock vs detection bug**

If the board looks identical after every restart, the level is unfinishable for the bot. Confirm
by dumping the toolbox hue next to a histogram of detected object hues: hue right, objects
present, taps change nothing → unfinishable level. Walk the level map (back to home, `PLAY`)
instead of tuning thresholds, which never fixes it.

## 5.3 Supervisors, not one sequential script

Two independent loops, because a crash or a soft lock must not end the session:

```bash
# plays for a fixed slice, then harvests once (belt and braces)
scripts/farm_loop.sh 50

# independent, every 180 s: pull creatives that the bot's cycle has not reached yet
scripts/harvest_loop.sh
```

A harvester called only at the end of a bot cycle delays every creative by up to an hour and
loses the batch when the cycle is interrupted. Check `pgrep -af 'farm_loop|harvest_loop'` after
starting: `pkill` misses a loop started as `exec <script>`, and two harvest loops racing on the
same manifest is the usual result.

Test a new target in **3–4 minute slices**, not 15–30: a short slice already shows whether the
bot enters gameplay, whether taps register, and whether an ad fires. Long waits burn the session
and hide the fact that the bot never left the menu.

## 5.4 What "the farm works" means

```
run log shows:  board changed -> level N, dead points cleared
                out-of-space dialog -> watch-ad button at (x, y)
                ad activity owns the screen  (AD_WORDS match in mCurrentFocus)
manifest shows:  new creative rows appearing minutes after those events
```

Impressions are the metric, not taps. Count them:

```bash
grep -c 'ad on screen' $HOME/playables/adcapture/run3h.log
```

If that number stays flat while taps flow, the bot is playing a game that never shows ads —
change the target or find a rewarded button; do not add more taps.

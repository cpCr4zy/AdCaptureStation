# 07 — Verification playbook

The rig's failure mode is not "it crashes" — it is "everything looks fine and produces nothing".
This file is the ladder that turns "should work" into "measured". Run it top-down; each rung has
a command and an expected output.

## Preamble — set the variables every command below uses

```bash
export CAP=$HOME/playables/adcapture
export ADB="$HOME/Android/Sdk/platform-tools/adb -s <guest-ip>:5555"
```

## Rule 0 — every measurement needs a negative control

Before believing any positive result from an ad endpoint, ask: *what would this look like if the
hypothesis were false?* Then send that input.

Reference case (AppLovin `mediate`):

```
original body        200   77802 B      ← looks like success
one byte flipped     200  102322 B      ← still "success"
truncated to 50 %    200    1202 B      ← still "success"
empty body           200    1202 B      ← still "success"
```

Conclusion is not "the replay was accepted" but "the endpoint does not validate bodies". Without
the control the first line would have been reported as a working channel.

## Rung 1 — is the device alive?

```bash
/usr/bin/python3 /usr/sbin/waydroid status | grep -E 'Session|Container'   # both RUNNING
~/Android/Sdk/platform-tools/adb devices | grep 5555                       # one device, state "device"
~/Android/Sdk/platform-tools/adb -s "$SERIAL" shell 'wm size'               # the guest's render size
```

Failure looks like `offline`, `Session: STOPPED`, or a device that answers but with a black
screen. Fix: `session stop` + `session start` (see `docs/08-troubleshooting.md`).

## Rung 2 — is the traffic visible?

```bash
CAP=$HOME/playables/adcapture
stat -c %s $CAP/requests.jsonl; sleep 15; stat -c %s $CAP/requests.jsonl   # must increase
awk '/=== mitmdump start/{n=0} /Traceback/{n++} END{print n+0}' $CAP/mitm.log   # 0 — only for a start via config/mitmdump-start.sh
~/Android/Sdk/platform-tools/adb -s <guest-ip>:5555 shell \
    'settings get global http_proxy'                                       # 192.168.240.1:8080
```

File growth is the only honest signal: the console can look healthy while every addon hook raises
inside mitmproxy.

## Rung 3 — did a creative actually arrive?

```bash
grep -c '_v1_js_load.js' $CAP/applovin_urls.txt    # observed SDK fetches (the catchers write these)
grep -m1 -o '"creative_urls":\[[^]]*\]' $CAP/responses.jsonl   # > 0 lines
grep -c 'mraid' $CAP/gma_pull.log                  # GMA channel, > 0
ls -la $HOME/playables/captured/playable | tail -3        # newest copies
```

Note the direction: `applovin_urls.txt` holds `_v1_js_load.js` URLs as observed; the harvester
*derives* the `_v1_raw.html` twin. Seeing `_v1_raw.html` in that file means someone edited it by
hand.

A URL is a lead, not an artifact. `_v1_js_load.js` is a wrapper; `_v1_raw.html` is the creative.
Vungle's `cdn-lb.vungle.com/nemo/.../index.html` is a renderer shell with no creative inside.

## Rung 4 — is the file real and runnable?

Three checks, in this order:

1. **Not a help page.** `grep -c 'support.google.com\|my ad center help' <file>` → 0.
2. **Self-contained.** `python3 scripts/check_selfcontained.py <dir>`: hard dependency list empty.
   Typical: engine inline (up to 5 MB of JS), art as base64 `data:` URIs, no remote `src`.
3. **It plays.** Serve the directory and drive a real browser:

```bash
cd $HOME/playables/captured && python3 -m http.server 8125 &
# open http://127.0.0.1:8125/playable/<creative>.html
```

Accept only when the creative renders **and** the loop runs (drag, units, coins, upgrades).
A screenshot of a static first frame proves nothing.

Two traps here, both measured:

- **A background tab throttles asset loading.** Cocos/Unity load on `requestAnimationFrame`; the
  creative sits on its splash icon forever. Bring the tab to the front and confirm
  `document.hidden === false`.
- **Missing MRAID bridges** stop builds before the first frame. Inject the shim
  (`docs/06-conversion-and-gallery.md`) before the first script, not after.

A good acceptance signal from the browser console:

```js
document.title                                  // engine title, e.g. "Cocos Creator | …"
(() => {const c=document.querySelector('canvas'); return c && c.width+'x'+c.height})()
```

`300x150` (the default canvas size) plus a black frame means the build did not boot. `780x437`
or similar means the engine took over the canvas.

## Rung 5 — is the gallery consistent?

```bash
python3 scripts/make_index.py                                          # cards: N | with game name: N
grep -o 'class="card"' $HOME/playables/captured/index.html | wc -l   # == N
ls $HOME/playables/captured/playable/*.html | wc -l              # == N
grep -c 'manifest' $HOME/playables/captured/index.html           # 0 — index is manifest-free
grep -o 'class="tag"' $HOME/playables/captured/index.html | wc -l   # badge count, no empty ones
# grep -c counts matching *lines*, and a grid can put several cards on one line — use -o | wc -l
```

Card count, file count and the generator's own count must agree. If they disagree, a creative was
edited or deleted by hand rather than through the manifest + rebuild.

## Rung 6 — do the numbers agree with the claims you are about to make?

Before reporting, re-derive them from disk instead of from memory of the run:

```bash
python3 - <<'EOF'
import json, collections
rows=[json.loads(l) for l in open('$HOME/playables/captured/manifest.jsonl')]
print(len(rows), 'rows;', sum(1 for r in rows if r.get('century')), 'century')
print(collections.Counter(r['game'] for r in rows).most_common())
EOF
du -sh $HOME/playables/captured
```

In the reference rig this caught a real inconsistency: an earlier report said "17 Century of 32
rows" when the truth was 9 — the 17 had counted rows that were later deleted.

## What "verified" may and may not mean

| claim | minimum evidence |
| --- | --- |
| "the device is scriptable" | `adb devices` shows `device`, and one `input tap` changes the screen |
| "traffic is captured" | `requests.jsonl` grows while the app runs, zero `Traceback` |
| "a creative was captured" | file exists, is not a help page, hard deps empty, **renders and plays** in a browser |
| "the channel works" | positive result **plus** a negative control that shows the endpoint discriminates |
| "the gallery is consistent" | card count == file count == generator count, no manifest reference |
| "the CA is trusted" | an HTTPS request from the guest decrypts in mitmproxy (not merely: the file exists) |
| "freed N MB" | `du -sh` before and after, plus an orphan scan by hash prefix |

If any of these is missing, say "unverified" and name what is missing. A plausible-looking number
invented to close a report is worse than an admitted gap.

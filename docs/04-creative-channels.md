# 04 — Creative channels: what actually produces files

Five channels were tried on the reference rig: **three produce files** (one of them needs a real
impression first) and **two are closed**. Read the yield numbers before budgeting time — the spread
is two orders of magnitude, and the dead ones look alive until you run a negative control.

| channel | gameplay | creatives produced | verdict |
| --- | --- | --- | --- |
| Google GMA slot replay | **no** | 96 slots per round; 286 requests with `sz` rotation → 39 URLs, 0 new | **primary** |
| AppLovin `res1` harvest after impression | yes | ~1 per 10 min of autonomous play | secondary |
| WebView HTTP cache dump | one impression | 1 per impression, byte-exact | fallback, best fidelity |
| AppLovin `mediate` replay | no | 0 readable | dead — encrypted |
| App-open / launch interstitial | no | 0 fills in 3 runs + `pm clear` | dead on this inventory |

(A sixth probe, BidMachine init/RTB, is described in 4.4 with its limits; it came from an earlier
session and is not counted among the five above.)

---

## 4.1 Google GMA slot replay — the primary channel

**Why it works.** The Google Mobile Ads SDK sends its ad request as a plain HTTPS GET to
`pubads.g.doubleclick.net/gampad/ads?...`. `ms` and `blob` stay valid as captured (measured: at least 48 h,
two days apart), but the request-id family (`correlator`, `request_id`, `preqs`, `seq_num`, `tsi`) is refreshed on every
replay and the server accepts the fresh values. Every replay runs a real auction and returns the
MRAID wrapper; a creative URL appears in a minority of answers (2 of 96 in the measured round),
usually a self-contained Cocos playable HTML on
`cdn-creatives-cf-prd.acquire.unity3dusercontent.com`. **No gameplay is involved: this is an
auction, not an impression.**

Lifetime and yield, as measured (not assumed): the slot set captured on day 1 was replayed on day 3
with the same `ms`/`blob` — 96 auctions, 96 × HTTP 200, 2 responses carrying a creative
URL, **1 new creative** (`Gummy Drop! Match 3 & Travel`, 3.8 MB, `com.bigfishgames.gummydropgoogle`)
and 1 duplicate. So the request stayed valid two days later and rotation does occasionally produce
a fresh file. Nothing longer was tested: write "replayable at least two days after capture,
observed", never "forever".

**What to refresh on each replay** (`VOLATILE` in `scripts/pull_gma.py`):

```
correlator    random integer ~1e12..1e13
request_id    12 random letters
preqs         0
seq_num       1
tsi           random
```

Everything else stays as captured. `ms`, `blob`, `cust_params`, `output` are kept verbatim.

**One slot = one auction.** A slot is the triple `iu` (ad unit path) + `format` + `sz` (size);
the *key* used for deduplication also carries `cust_params` and `output`, because two auctions can
share the triple and still be different units (`pull_gma.py --list` prints all five columns).
The reference capture held **96 distinct slots**, all Rollic GAM interstitial/rewarded units
(`%2F22612293878%2FRollicGAM_drd_int_19%2Fset_40`, `interstitial_mb`, `1024x768`, …). Run one
round = one auction per slot:

```bash
$HOME/playables/botvenv/bin/python scripts/pull_gma.py --list      # show slots
$HOME/playables/botvenv/bin/python scripts/pull_gma.py --rounds 1  # one auction each
```

**Extraction inside `pull_gma.py`** — the parts that were added because the naive version
silently produced nothing or junk:

1. Unescape `\/` and `&amp;` in the returned URLs before fetching.
2. Accept `.zip` payloads and protocol-relative (`//host/...`) URLs.
3. Require a playable marker in the body (`mraid`, `cocos`, `unity`, `playable`,
   `play.google.com`, `__zip`).
4. **Reject Google help pages**: a ~1.5 MB answer containing `support.google.com` or
   `my ad center help` is a click-through page, not a creative. Five of them occupied 7.5 MB of
   the reference gallery before this filter existed.
5. Collect *all* store packages in the body (`pkgs = PKG_RE.findall(...)`), not the first.
6. Back off on `429`/`503` with jitter; per-slot `try/except` so one bad slot cannot end a run.
7. Key the slot by `iu` + `format` + `sz` + `cust_params` + `output`, otherwise distinct
   auctions collide.
8. Retry downloads; dedupe by sha1.

**Yield measured, and why more requests do not help:**

```
rounds over the same 96 slots:  5 / 5 / 13 creative URLs
                                all duplicates of what was already on disk
286 requests with sz rotation:   39 URLs, 39 duplicates, 0 new, 2× HTTP 502
sizes rotated: 1024x768, 480x320, 300x250, 1272x747, 768x1024, 640x480
two days later, one round:      96 auctions, 96 × HTTP 200, 2 URLs, 1 new, 1 duplicate
```

The pool is campaign rotation plus newly captured slots, **not** request count. Loop the
replayer on a slow cycle (300 s in `scripts/gma_loop.sh`) to catch rotation, and treat
"new creatives: 0, duplicates: N" as the steady state rather than a bug to fix by hammering.

**Acceptance test for this channel:**

```bash
# a replayed slot answers with an mraid wrapper and a creative URL  (expected: > 0)
grep -c 'mraid' $HOME/playables/adcapture/gma_pull.log
# and the downloaded file is a real playable, not a help page
python3 - <<'EOF'
import glob, re
for f in glob.glob('$HOME/playables/captured/playable/*.html')[:3]:
    b = open(f, 'rb').read(400000).lower()
    print(f.split('/')[-1][:10], 'help-page' if b'support.google.com' in b else 'ok')
EOF
```

---

## 4.2 AppLovin `res1` harvest — after a real impression

The AppLovin SDK loads the creative from `https://res1.applovin.com/<account>/<id>_v1_js_load.js`.
The same creative is served as a single self-contained `_v1_raw.html` — fetch that, do not try
to rebuild the creative from the js_load wrapper.

Pipeline (three stages, in `scripts/`):

1. **Live catcher** — `catch_century.py` appends every observed `_v1_js_load.js` URL to
   `applovin_urls.txt` and dumps bodies of responses that mention target packages.
2. **Harvester** — `harvest_applovin.py` reads that list, derives the `_v1_raw.html` twin,
   downloads it, unpacks `window.__zip` into `variants/<id>/`, reads
   `play.google.com/store/apps/details?id=` for identity, appends a manifest row. Skips ids
   already known, so re-runs are cheap.
3. **Scheduler** — `harvest_loop.sh` runs it every 180 s, so a creative lands minutes after the
   impression instead of at the end of an hour-long cycle.

Two shapes exist and only one has `window.__zip`: `grep -c '__zip' <raw>` decides. A missing
`variants/<hash>/` for a flat `_v1_raw.html` is normal, not a broken unpack.

**Acceptance test:**

```bash
tail -3 $HOME/playables/adcapture/harvest.log        # ids processed, no tracebacks
grep -c '_v1_raw.html' $HOME/playables/adcapture/applovin_urls.txt
```

---

## 4.3 WebView HTTP cache — the byte-exact channel

When an ad renders inside the game's WebView, Chromium writes the whole playable into

```
/data/data/<pkg>/cache/WebView/Default/HTTP Cache/Cache_Data/
```

before any URL appears in traffic. Entry files are `<hash>_0`: the URL sits near the head, the
response body after it. Dumping that directory yields the creative byte-for-byte, without any
replay machinery.

```bash
# 1. as root inside the container, stage the cache where adb can read it
sudo wd-root '
  export PATH=/system/bin:/system/xbin
  rm -rf /data/local/tmp/wvcache; cp -r "/data/data/com.quok.screwJam/cache/WebView/Default/HTTP Cache/Cache_Data" /data/local/tmp/wvcache'
# 2. pull and parse
python3 scripts/harvest_wvcache.py       # keeps entries whose URL is a creative host
```

**Prerequisites, and the trap:** this channel is empty until an impression happens, and
`pm clear <pkg>` empties both the cache *and* the SDK's own `files/al` / `files/bm` (both 0 B
afterwards). Four runs on the reference rig returned `entries kept: 0` because there had been no
ad since the clear — that is expected, not a bug. Check sizes before declaring the channel dead:

```bash
sudo -n wd-root '
  export PATH=/system/bin:/system/xbin
  du -sh /data/data/com.quok.screwJam/cache /data/data/com.quok.screwJam/files/al /data/data/com.quok.screwJam/files/bm'
```

---

## 4.4 Dead channels, with the evidence (do not spend iterations here)

### AppLovin `mediate` replay — closed

Request and response are a versioned encrypted envelope: a `2:<hex>:<b64>` header then
ciphertext, ~40 % printable bytes. The key is minted inside the SDK process during a handshake,
so without native instrumentation the body cannot be produced or read.

The **negative control** is the part worth remembering:

```
original body        200   77802 B
one byte flipped     200  102322 B
truncated to 50 %    200    1202 B
empty body           200    1202 B
```

Every variant is accepted with 200. Therefore a 200 here proves nothing about validity — and
any "replay accepted" conclusion drawn from the status code is wrong. This is the general rule
for undocumented ad endpoints: **always run the corrupted/empty control before believing a
success.**

### App-open / launch interstitial — no fill on this inventory

Tested with three `am force-stop` + `am start` cycles and again after `pm clear`
(85 s waits). Zero ad activities in `mCurrentFocus`. Small sample, so it is recorded as "absent
in this inventory", not "impossible" — but do not build a plan on it.

### BidMachine init / RTB — 204 no-fill (partly hypothesis)

Recorded from an earlier session, not re-verified here: the init call appeared unsigned and the
RTB protobuf schema was recovered offline from generated Java, but without a valid placement id
the endpoint answered `204` (schema parsed, no fill). `400` vs `204` is a usable oracle when
iterating fields — 204 means "well-formed, nothing to serve". Treat the "unsigned" part as a
hypothesis to re-test, not as a fact: the channel produced no creatives either way.

---

## 4.5 Choosing a channel — decision rule

```
Do you have any captured gampad/ads request in requests.jsonl?
├─ yes → run pull_gma.py. Cheapest, no gameplay, usually the bulk of the yield.
└─ no  → you need one real impression first:
          start mitmproxy + guest proxy → play until one ad shows → then both
          res1 harvest and the WebView cache become available.
          If the target game needs a Play account, it will never run here — pick another.
```

Never send impression beacons for an ad nobody rendered: that is impression fraud by the networks'
definition, and the consequence for this rig is practical rather than legal advice — an identity that
looks abusive stops receiving fill and the device has to be re-imaged. The GMA replay in 4.2 is a
different thing on the wire (auction requests, no impression event), but it is still unauthorised
automation of an ad server: the same stop rules apply, and section 4.6 limits the rate for that
reason. Nothing here is legal advice.

## 4.6 Rate and policy limits (read before looping anything)

- GMA replay is **auction traffic**, not an impression, but it is still unauthorised automation of
  an ad server. Keep the cycle slow (`scripts/gma_loop.sh` uses 300 s), keep one identity, and
  stop when a round yields only duplicates — that is saturation, not a cue to push harder.
- AppLovin `res1` fetches are plain CDN GETs for files the SDK already delivered; they are the
  least contentious part of the pipeline.
- Rotating device identity, `sz` or locales to farm more inventory is exactly the pattern the
  networks detect. This document describes what was measured, not an endorsement of scaling it.
- Personal data: the rig reads only its own emulator. Do not point the CA or `lxc-attach` at a
  phone that belongs to someone else.

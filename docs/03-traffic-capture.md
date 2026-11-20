# 03 — Traffic capture (mitmproxy)

Goal: see every ad request and response the SDKs make, and keep enough of it offline that
creatives can be extracted later without the device.

## Certificate directory

mitmproxy keeps its CA in a `confdir`. The reference rig pins it so the certificate installed
into the Android system store is always the same one:

```
$HOME/playables/adcapture/mitmconf/
    mitmproxy-ca.pem           the CA private key + cert (keep it, it is the trust anchor)
    mitmproxy-ca-cert.pem      installs under subject_hash_old of this CA (reference rig: <ca-hash>; yours differs)
    mitmproxy-ca-cert.cer/.p12, mitmproxy-dhparam.pem
```

Generated on first run (`mitmdump --set confdir=...`) and then installed into the guest as
described in `docs/02-waydroid-device.md`. Two rules:

- **Generate it per machine; never copy `mitmproxy-ca.pem` between rigs.** That file is the CA
  private key — sharing the documentation must not share the key.
- Regenerating the CA silently breaks capture until the guest store is updated again.

## The addon stack

Five addons, each with one job. **`scripts/` is authoritative**; `config/addons/` holds the same
five files as a staging copy so a fresh machine can populate `$CAP` in one command:

```bash
CAP=$HOME/playables/adcapture
cp scripts/catch_playable.py scripts/capture_all.py scripts/catch_century.py \
   scripts/capture_requests.py scripts/capture_responses.py "$CAP"/     # stage before first run
```

Edit `scripts/` and re-stage; editing only `config/addons/` is how the two copies drift.

`config/` in this station contains: `sudoers-waydroid-lxc.txt` (the privileged rule),
`mitmdump-start.sh` (canonical capture start), `requirements-botvenv.txt` and
`requirements-mitmvenv.txt` (`pip freeze` locks) and `addons/` (five mitmproxy addons). The
rewarded-button template is **not** part of the station — it is a crop of the game's own UI, so you
make your own (`docs/05-game-farm.md`, step 3). Everything else is generated at run time.

| addon | writes | job |
| --- | --- | --- |
| `catch_century.py` | `applovin_urls.txt`, `century/`, `century_index.jsonl` | records every `res1.applovin.com/..._v1_js_load.js` URL the moment it is requested, and saves bodies of responses whose text contains one of the target **package ids** listed at the top of the file |
| `capture_all.py` | `all/`, `all_index.jsonl` | stores every ad-related response body (html/js/json/image) so a creative could be reassembled offline |
| `catch_playable.py` | `flows/` + `hits.jsonl` | catches suspicious HTML/ZIP bodies by content sniffing, not by host |
| `capture_requests.py` | `requests.jsonl` | the *requests*: method, URL, headers, body — needed only if a replay is on the table |
| `capture_responses.py` | `responses.jsonl` | ad responses with a `creative_urls` list mined out of the body; does gzip sniffing |

Why both capture directions: responses tell you what was served, requests are the only thing
that can be replayed. Why several catchers before filtering: you do not know which host serves
the creative until after the first impression.

## Canonical launch

The canonical way to start capture is the wrapper, because it also writes the log every gate
looks at:

```bash
bash config/mitmdump-start.sh &        # writes $CAP/mitm.log; this is the canonical start
```

Foreground variant, for debugging only — it does **not** write `mitm.log`, so the log-based gates
below do not apply to it:

```bash
CAP=$HOME/playables/adcapture
$HOME/playables/mitmvenv/bin/mitmdump \
    --set confdir=$CAP/mitmconf \
    --listen-port 8080 \
    --flow-detail 0 \
    -s $CAP/catch_playable.py \
    -s $CAP/capture_all.py \
    -s $CAP/catch_century.py \
    -s $CAP/capture_requests.py \
    -s $CAP/capture_responses.py
```

`--flow-detail 0` keeps stdout usable; the addons write files, the console is only for errors.
`config/mitmdump-start.sh` is the same line wrapped with a redirect into `$CAP/mitm.log`. **Use the
wrapper if any gate greps `mitm.log`** — a plain foreground run writes to the terminal and the gate
fails with "no such file".

## Is it working? Measure growth, not logs

The single most useful check in the whole rig — it proves mitmproxy, the addons and the guest
proxy are all alive at once:

```bash
stat -c '%s %n' $CAP/requests.jsonl; sleep 15; stat -c '%s %n' $CAP/requests.jsonl
```

The size must move. If it does not: proxy unset, CA not trusted, or the addon crashed at import.
Logs are a poor proxy for this — a mitmproxy foreground log can look healthy while an addon is
raising inside every hook.

## Pitfalls that cost real time

1. **`--set ignore_hosts=<anything>` silently disables capture.** With it set, every flow is
   tunnelled and the addons write nothing — 40 minutes of "no traffic" in the reference run.
   Capture everything, filter inside the addon.
2. **Never trust `content-type`.** AppLovin labels a gzip-compressed protobuf
   `application/json`. Trusting the header stores mojibake and the URL regex finds zero
   creatives in a 113 KB body. Sniff the `1f 8b` magic, gunzip, then regex over raw bytes
   (strings sit as plain bytes inside protobuf).
3. **Binary bodies must be base64-encoded.** `get_text()` on protobuf raises
   `UnicodeEncodeError: surrogates not allowed` *inside the hook*, which silently stops all
   further writes for that addon. Gate text fields on a strict UTF-8 decode plus a
   control-character count, otherwise write `body_b64`.
4. **`HTTP/2 protocol error: Invalid input ConnectionInputs.RECV_PING in state
   ConnectionState.CLOSED`** in the log is routine noise from a connection the app already
   dropped. When watching for trouble, match `Traceback`, not `error`.
5. **Do not capture the whole internet for a week.** `all/` grows by hundreds of MB a day.
   Rotate or prune, and keep `applovin_urls.txt` / `requests.jsonl` — they are small and are
   what the harvesters actually read.

## What the addons give you downstream

```
applovin_urls.txt      one line per observed res1 URL  → harvest_applovin.py
requests.jsonl         full request records            → any replay attempt (GMA, BidMachine)
responses.jsonl        ad responses + creative_urls    → harvest even for non-winning bids
all/  century/  flows/ raw bodies for manual digging
```

## Acceptance gate

```bash
# 1. growth while the app is running
stat -c %s $HOME/playables/adcapture/requests.jsonl     # twice, 15 s apart → increasing

# 2. at least one ad host captured  (expected: > 0)
grep -c 'res1.applovin.com\|gampad/ads\|mads/gma' $HOME/playables/adcapture/requests.jsonl

# 3. a response that names a creative URL
grep -m1 -o '"creative_urls":\[[^]]*\]' $HOME/playables/adcapture/responses.jsonl

# 4. no addon crash since the last start (expected: 0; the wrapper truncates the log and writes a marker)
awk '/=== mitmdump start/{n=0} /Traceback/{n++} END{print n+0}' $HOME/playables/adcapture/mitm.log
```

All four must pass before any harvesting makes sense.

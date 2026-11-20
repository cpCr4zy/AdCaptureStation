# Security and privacy — what this station publishes and what it never does

This directory is meant to be read by strangers and run on their own machine. That constrains what
may be inside it. The rule of thumb: **the station publishes method, never material — and never the
operator.** No creatives, no keys, no device identity, no personal paths, no transcripts quoting a
real shell.

Verify the current state at any time:

```bash
bash scripts/publish_scan.sh      # exit 0 = clean, 1 = findings, 2 = the scan failed (treat as failure)
bash scripts/verify_station.sh    # internal consistency of the documents and the collection
```

## 1. Deliberately absent

| not published | why | what the docs carry instead |
| --- | --- | --- |
| captured creatives (`captured/`, `playable/`, `index.html`) | third-party advertising content: not ours to redistribute | the pipeline that produces them, the fidelity rules, the gallery format |
| raw payloads and unpacked projects | same, plus size | the four packaging classes and how to unpack each |
| mitmproxy CA and any private key | a published CA key lets anyone forge certificates for anyone who trusts it | instructions to mint your own CA and install it (`docs/02-waydroid-device.md`) |
| adb key, device serial, `android_id` | device identity | the command that reads it, the value redacted |
| screenshots and the rewarded-button template | crops of a game's own UI | a recipe to crop your own (`docs/05-game-farm.md`, step 3) |
| the account name used in `sudoers` | personal identifier | the `__USER__` placeholder + `scripts/configure.sh` |
| absolute home paths | personal identifier, and wrong on every other machine | `$HOME` / `os.path.expanduser("~")`, with `ADCAPTURE_DIR` / `CAPTURED_DIR` overrides |
| **review transcripts** | they quote shell output, paths and local session ids | the findings, verdicts and accepted deviations in `reviews/README.md` |

`private/` (gitignored, local only) holds the template, the transcripts and any working notes.

## 2. What the audit changed

| finding | before | after |
| --- | --- | --- |
| account name in 50+ places | absolute home paths in every script and document, and the rule line in the sudoers file | all paths derive from `$HOME`; the sudoers file ships `__USER__`, `configure.sh` substitutes it |
| device identifier | the measured `android_id` value appeared verbatim in the snapshot | `<redacted>`, with the command that reads it on any device |
| CA fingerprint | a real `subject_hash_old` value was used as an example | `<ca-hash>`, with the command that computes it |
| review transcripts | six raw rounds with paths and session ids | summarised in `reviews/README.md`; raw logs stay in `private/` |
| game UI crop | a button crop shipped in `config/` | removed from the public tree, recipe documented, file in `private/` |
| measurement fingerprint | exact measurement date and exact per-run counters | relative statements ("multi-hour farm", "two days apart"), counters rounded away |
| binaries | none found | `.gitignore` blocks assets, keys, databases and dotenv files preemptively |

The scanner reads **every file in the repository** with no extension allowlist (`reviews/` included;
the local `private/` tree is reported separately and never fails the run) for PEM blocks, API keys, tokens, `Bearer`
values, passwords, signed-URL parameters, device ids, MAC addresses, public IPs, local domains, home
paths, real user names in sudoers rules and e-mail addresses. It also fails on binary assets and on
files over 200 KB, because that is how a stray capture would enter the repository.

## 3. What intentionally stays

- **Container addresses.** Waydroid's LXC network uses the `192.168.240.0/24` subnet with the host at
  `.1`; **the guest address is assigned by DHCP**, so the documents write `<guest-ip>` and read it
  from `waydroid status`. The subnet tells nobody where you live; the host-side `.1` appears verbatim
  because it is a fixed property of the container network, and the scanner allows exactly that
  subnet and nothing else.
- **Package ids, store names, ad-network endpoints.** Public facts, and the documents are useless
  without them. Game titles appear nominatively ("the rig captured N creatives from X"); no logos, no
  artwork, no assets.
- **Tool versions and kernel.** Needed to reproduce. The exact date of measurement and per-run
  counters reproduce nothing and were removed.
- **The review findings.** Publishing what a review caught is the point; publishing the raw
  transcripts is not, because they quote a real shell.

## 4. Legal and ethical boundaries — read this before running a channel

- The station automates **your own** device behind **your own** proxy. It forges no identity, bypasses
  no paywall and sends **no fabricated impression beacons of its own**.
- Be precise about what it does do: replaying a captured Google ad request
  (`docs/04-creative-channels.md`) issues real ad requests with nobody viewing an ad, and repeatedly
  playing a third-party game from a script is automation of someone else's product. An ad network
  may classify the requests as **invalid traffic**; a publisher may treat the automation as a breach
  of its EULA. Both risks land on the device, the IP or any account associated with them — on you.
  The rig limits itself (one device identity, one round every 300 s, stop on duplicates) because the
  limit is ethical and practical, **not** because it makes the traffic valid.
- Never point this at an account you care about. Use a throwaway emulator without a Play identity, as
  the reference rig did.
- Captured creatives and the games' own UI belong to their owners. Keep them local; do not republish
  them, do not ship them here, do not sell them.
- Third-party terms: the game's EULA, the ad networks' policies and the store's terms apply to you,
  not to this document. Nothing here grants permission or constitutes legal advice.
- Complaints and takedown requests: open an issue in this repository (or use the contact in
  `SECURITY.md`). Trademark and content questions are answered there, not by emailing the author
  privately.
- Whether you may send automated requests at all is decided by the ad network's terms, not by this
  document. The station records which channels the reference rig ran, what they yielded, and where a
  channel is closed and why — it does not grant permission.

## 5. Before you push

```bash
git init                              # required: the scan verifies .gitignore against the index
bash scripts/publish_scan.sh          # must print CLEAN
bash scripts/verify_station.sh        # must print ALL GATES PASSED

git status --short                    # nothing from captured/, private/, adcapture/
git ls-files | grep -cE '^(private|captured|adcapture|playable|mitmconf|all|century|flows)/'   # 0
git diff --stat config/                                                        # empty: template intact
git log --all --diff-filter=A --name-only --pretty=format: | sort -u \
  | grep -E '^(private|captured|adcapture|playable|mitmconf|all|century|flows)/|\.pem$|adbkey'  # empty
git log --format='%an <%ae>' | sort -u                                          # a public identity
```

`.gitignore` does not untrack what is already in the index, and the scanner cannot see history. If a
file was committed once, remove it from history before the first push
(`git filter-repo --path private/ --invert-paths`), otherwise the crop or the key is public forever.

**Commit identity is the easiest leak of all:** the first push publishes the `user.name`/`user.email`
of every commit. Configure a no-reply address before the first commit, not after:

```bash
git config user.name  "<your public handle>"
git config user.email "<id>+<handle>@users.noreply.github.com"
```

`gitleaks detect --redact -v` (history scan) is part of the checklist, not an option: the working-tree
scan cannot see a secret that lives only in an old commit — and it does no entropy analysis, so a bare
base64 blob or a secret split across lines is invisible to it. The space-separated password form
(a bare `password` followed by a value) is only flagged when the value contains a digit, which is
deliberate: without that guard every sentence about passwords would fail the gate, so a password made
only of letters passes.

The same gate runs in CI (`.github/workflows/publish-scan.yml`): `publish_scan.sh`, gitleaks, the
author check and a history check for rig artefacts, on every push and pull request. A gate that only
runs in the author's shell is a habit, not a check.

Before `git init` the scanner refuses to print CLEAN — use `python3 scripts/publish_scan.py --no-git`
for a dry run, which says explicitly that the git checks were skipped. It also refuses when the
enclosing repository starts *above* the station (a stray `git init` in `$HOME`): that index is not the
one you will push, and `git add -A` there stages the whole home directory. With an empty history it
checks the identity the next commit would carry (`git var GIT_AUTHOR_IDENT`), so a missing no-reply
address fails before the first commit, not after.

**What the scan cannot catch:** semantic leaks (a combination of details that identifies you), the
choice of game titles you captured, and anything already in git history. Those need a human read of
`docs/10-state-snapshot.md` before the first push.

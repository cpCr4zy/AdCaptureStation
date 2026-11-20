# Review log — independent review through a second Hermes profile

Method: every round is a self-contained prompt — the owner's requirement, the measured facts, the full
text of the documents under review, and the previous round's per-ID status — sent to a second profile
with **no tools**, so the reviewer reasons only from what is on the page:

```bash
hermes -p <review-profile> chat --query-file /tmp/review_roundN.md --oneshot --quiet
```

| round | focus | findings | verdict |
| --- | --- | --- | --- |
| 1 | completeness | 44 | not ready |
| 2 | consistency | 21 | not ready |
| 3 | reproducibility | 16 | not ready |
| 4 | paths, gates, numbers | 13 | not ready |
| 5 | quoting, CA install, sudoers | 12 | not ready |
| 6 | privilege scoping, order of steps | 13 | not ready |
| 7 | security & privacy before publication | 16 | not ready |
| 8 | verification of the privacy fixes (code only) | 15 | not ready |
| 9 | verification of the privacy fixes (code only) | 15 | not ready |
| 10 | verification with the documents on the page | 17 | not ready |
| 11 | the gate itself, with every file on the page | 15 | not ready |

Fixes for round 11 were applied. **No twelfth verification round was run** — that is an open item, not
a pass. What is verified is the mechanical part: `scripts/verify_station.sh` and
`scripts/publish_scan.sh` are green, and the scanner fails on every planted leak in the negative-test
set (see `SECURITY-AND-PRIVACY.md`, section 5).

Each round ended with per-ID verdicts; nothing here was accepted on the author's word alone.

**The raw transcripts are not published** — they quote shell output, planted secrets and internal
paths, which is exactly the material this station exists to keep out of a repository. They live in
`private/reviews/` on the reference rig. What they contained is summarised below, because the
*findings* are the documentation.

## What the review caught that self-verification missed

- **A critical quoting bug in the CA install block** (round 5): the container script was double-quoted,
  so `$H` and `$(ls …)` expanded on the host and the backup guard aborted every install. Fixed with a
  single-quoted payload plus `'"$H"'` splicing, then verified on the live device.
- **A self-destroying `sed`** in the relocation checklist (round 4): a document that rewrites itself
  becomes a no-op on the second run. Replaced by a script, tested on a copy.
- **A missing build step** (round 1): nothing turned payloads into `playable/`. Became
  `scripts/build_gallery.py`.
- **A circular definition** between "the manifest is derived" and "the gallery is built from the
  manifest" (rounds 2–4), which produced the explicit order rebuild → build → index.
- **An install order that broke `sudo`** (round 6): the sudoers file was installed *before* being
  validated. Now: validate the source, install, `visudo -c`.
- **A false claim about privilege scoping** (round 6): a trailing `*` in sudoers also matches extra
  `-P`/`-n` flags, so the rule did not pin the container. The rule now names a root-owned wrapper whose
  path and container name are baked in.
- **Privacy leaks one would not notice** (round 7): personal home paths in every script, a device
  identifier in the snapshot, a certificate fingerprint, published review transcripts, and a game-UI
  crop inside the tree. All removed; `scripts/publish_scan.sh` gates them now.
- **Numbers and paths that disagreed with each other** (rounds 2–6): 29 vs 30 builds, 9 vs 10 unpacked,
  a memory limit nobody measured, a hardcoded certificate hash inside a gate that has to work on other
  machines.

## What the security rounds changed in the gate itself

Rounds 8–11 stopped reviewing prose and reviewed the scanner — and that was worth it, because a gate
that prints CLEAN on a secret is worse than no gate. Six real defects, all fixed and each with a
negative test:

- **a real leak lived in the gate**: `verify_station.sh` searched for the certificate fingerprint by
  its literal value, publishing the very hash the documents had replaced with `<ca-hash>`;
- **`.gitignore` was doing the work the scanner claimed to do**: the scan skipped `reviews/`, used an
  extension allowlist, and treated "no repository" as clean;
- **a gitignored file that was already tracked** was reported as local and never scanned — the one case
  where `.gitignore` cannot help;
- **only the first match per line was checked**, so a placeholder early in a line hid a real secret
  later on it;
- **allowlists were substring matches on the whole line**, so a comment saying `example.com` silenced a
  password on the same line;
- **whole classes were missing**: IPv6, device serials, DSN-style credentials, quoted JSON keys.

## Accepted deviations

- The reference rig's distro and kernel stay at major level (`Arch-based`, `7.3.x`) because
  reproduction needs them; the exact measurement date, patch level, panel density and per-run counters
  were rounded away.
- Container addresses: the host side of the LXC network (`.1`) stays literal — it is fixed per
  installation; the **guest** address is DHCP, so the documents write `<guest-ip>` and the scripts read
  it from `waydroid status`.
- The 40–60 minute session lifetime stays an **estimate**; no distribution was measured.
- `packed-unknown` (three creatives) is documented as a limit, not solved.
- Archive builds are not runnable from a file tree; `payload.html` stays the only entry point.
- The scanner is line-based and has no entropy analysis: a bare base64 blob or a secret split across
  lines is invisible to it, which is why `gitleaks` is a required step in the CI workflow and a human
  read of `docs/10-state-snapshot.md` is required before the first push.

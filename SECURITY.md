# Security policy

This repository is documentation and tooling for capturing playable ad creatives. The material that
must not be public — captured creatives, keys, device identity, transcripts — is kept out by
`.gitignore`, by `scripts/publish_scan.sh` and by the CI workflow in `.github/workflows/`.

## Reporting a leak or a security problem

If you find that this repository exposes something it should not (a key, a device identifier, a
personal path, a file that belongs to a third party), please **open an issue** titled
`privacy: <short description>` in this repository. Do not include the sensitive value itself in the
issue — describe where it is, e.g. "line 40 of docs/02".

If the repository has a private contact configured, prefer it; otherwise the issue is the channel, and
the report is expected to be actionable without the secret being repeated.

## What is in scope

- working-tree leaks: anything `scripts/publish_scan.sh` should have caught (false CLEAN reports are
  as interesting as the leak itself);
- history leaks: a file that was committed and later removed (the scanner cannot see history);
- CI gaps in `.github/workflows/publish-scan.yml`.

Out of scope: disagreements with the legal position in `SECURITY-AND-PRIVACY.md`, and requests to
publish captured creatives.

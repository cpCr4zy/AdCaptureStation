#!/usr/bin/env bash
# Entry point for the pre-publication audit; the checks live in publish_scan.py (stdlib only).
#
#     bash scripts/publish_scan.sh
#
# Exit 0 = clean, 1 = findings, 2 = the scan could not complete (treat this as failure).
set -u
exec python3 "$(dirname "$0")/publish_scan.py" "$@"

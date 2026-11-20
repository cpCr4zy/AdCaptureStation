#!/usr/bin/env bash
# One-time localisation of this station for the machine you are on.
#
#   bash scripts/configure.sh            # uses $USER
#   bash scripts/configure.sh alice      # explicit user name
#
# The shipped sudoers file carries the placeholder __USER__ (this repository publishes no account
# name). This script does NOT edit that tracked file — it writes a sibling,
# config/sudoers-waydroid-lxc.generated, which is gitignored. The repository stays clean, `git diff
# config/` stays empty, and the placeholder survives for the next reader.
set -euo pipefail

USER_NAME=${1:-${USER:?cannot determine user name; pass it explicitly}}
[[ "$USER_NAME" =~ ^[a-z_][a-z0-9_-]{0,31}$ ]] || {
    echo "refusing: '$USER_NAME' is not a plain account name ([a-z_][a-z0-9_-]{0,31})"; exit 1; }
STATION=$(cd "$(dirname "$0")/.." && pwd)
SRC="$STATION/config/sudoers-waydroid-lxc.txt"
DST="$STATION/config/sudoers-waydroid-lxc.generated"

[ -f "$SRC" ] || { echo "missing $SRC"; exit 1; }
grep -q '^__USER__ ALL' "$SRC" || {
    echo "refusing: the template no longer contains the __USER__ placeholder"
    echo "           restore it with: git checkout -- config/sudoers-waydroid-lxc.txt"
    exit 1
}
{ [ ! -e "$DST.bak" ] && [ ! -e "$DST.orig" ]; } || { echo "refusing: backup files next to $DST"; exit 1; }

tmp=$(mktemp "${TMPDIR:-/tmp}/sudoers-waydroid-lxc.XXXXXX")
trap 'rm -f "$tmp"' EXIT
sed "s/^__USER__ ALL/${USER_NAME} ALL/" "$SRC" > "$tmp"
grep -q "^${USER_NAME} ALL" "$tmp" || { echo "substitution failed"; exit 1; }
install -m 0644 "$tmp" "$DST"

echo "written: ${DST#"$STATION"/}  (gitignored)"
grep -v '^#' "$DST" | grep -v '^$'
echo
echo "paths the scripts will use:"
echo "  adcapture  ${ADCAPTURE_DIR:-$HOME/playables/adcapture}"
echo "  captured   ${CAPTURED_DIR:-$HOME/playables/captured}"
echo
echo "next:"
echo "  sudo install -m 0755 config/wd-root.sh /usr/local/sbin/wd-root"
echo "  sudo visudo -cf config/sudoers-waydroid-lxc.generated"
echo "  sudo install -m 0440 config/sudoers-waydroid-lxc.generated /etc/sudoers.d/waydroid-lxc"
echo "  sudo visudo -c"
echo "  sudo -n wd-root 'id' | grep -c 'uid=0'        # must print 1"
echo "  bash scripts/verify_station.sh && bash scripts/publish_scan.sh"

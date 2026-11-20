#!/bin/sh
# Root entry point for the Waydroid container, referenced by the sudoers rule instead of the raw
# lxc-attach: a trailing '*' in sudoers also matches extra flags (-P, -n), so the path/name below
# is what actually pins the container. Every argument is passed to the container's shell.
exec /usr/bin/lxc-attach -P /var/lib/waydroid/lxc -n waydroid -- /system/bin/sh -c "$*"

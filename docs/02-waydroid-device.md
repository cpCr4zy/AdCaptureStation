# 02 — Waydroid as the scriptable device

The rig needs an Android device that (a) accepts `adb input tap`, (b) can be told to use a
proxy, and (c) will run an ad-heavy casual game without a Play account. Waydroid on the host
gives all three and needs no phone.

Reference device (measured on the reference rig):

```
waydroid status        Session: RUNNING   Container: RUNNING
                       Vendor type: MAINLINE   IP: <guest-ip>   (assigned by the container's DHCP)
                       Session user: <user>(1000)   Wayland display: wayland-1
Android                SDK 33 (Android 13)
ABI                    x86_64,x86,arm64-v8a,armeabi-v7a,armeabi   (native bridge)
Display                Physical size inherited from the host panel (see the note below)
adb                    $SERIAL               (i.e. <guest-ip>:5555)
proxy in guest         global http_proxy = 192.168.240.1:8080
custom CA              /system/etc/security/cacerts/<ca-hash>.0  (hash of that rig's CA — yours differs)
advertising_id         null      (no Play identity, limits inventory — see below)
android_id             <redacted>      (device identifier of the reference rig — not published)
```

Set the target once and use it everywhere; with more than one adb device attached, a bare `adb`
command silently picks the wrong one:

```bash
export ADB="$HOME/Android/Sdk/platform-tools/adb"
# the guest address is assigned by DHCP inside the container; read it, do not assume it
export SERIAL="$(waydroid status | sed -n 's/^IP address:[[:space:]]*//p')":5555
export ADB="$ADB -s $SERIAL"
$ADB shell 'wm size'
```

## Install

```bash
# Arch/CachyOS
sudo pacman -S waydroid waydroid-image android-tools curl unzip zip openssl
sudo systemctl enable --now waydroid-container
sudo waydroid init -s MAINLINE
```

On Arch, the package `waydroid-image` (`1:20.0.20261022-1` on the reference host) is what
provides `/usr/share/waydroid-extra/images` — verified with
`pacman -Qo /usr/share/waydroid-extra/images`. `waydroid init` writes that path into the config,
and both must agree:

```bash
grep images_path /var/lib/waydroid/waydroid.cfg    # images_path = /usr/share/waydroid-extra/images
```

Config confirmed on the reference rig:

```
arch = x86_64
vendor_type = MAINLINE
images_path = /usr/share/waydroid-extra/images
binder = binder        binder_protocol = aidl3
service_manager_protocol = aidl3
auto_adb = False
```

`auto_adb = False` is deliberate: the rig connects over TCP by IP, and the guest adbd port is
set explicitly.

## The image variant decides the inventory — choose it first

The flavour of the image, not the game, sets `advertising_id`, and therefore what Google is
willing to serve:

| image | identity | what to expect |
| --- | --- | --- |
| `VANILLA` (`init -s VANILLA`) | no GMS at all | Play-dependent SDKs may fail; `advertising_id` null |
| `GAPPS` + Play sign-in | real Play identity | best inventory, but needs an account and a signed-in store |
| `MAINLINE` + MicroG (reference rig) | `advertising_id = null`, `android_id` present | lowest-tier inventory; ads do appear, volume is capped by identity, not by request count |

Check what you got before blaming supply:

```bash
$ADB shell 'settings get secure advertising_id'         # null on MicroG
$ADB shell 'settings get secure android_id'             # present
$ADB shell 'pm list packages | grep -c com.android.vending'
```

## Session control

Waydroid is a user session, not only a service: it needs the Wayland display of the logged-in
user. On this rig the session **had to be restarted repeatedly during multi-hour runs**
(`Session: STOPPED`, `adb offline`, black screen — several restarts across a multi-hour farm, on the
regular app restarts logged by the bot). The widely quoted "40–60 minutes" is an estimate
from those runs, not a measured distribution: treat any session stop as routine and supervise it.

```bash
export XDG_RUNTIME_DIR=/run/user/1000 WAYLAND_DISPLAY=wayland-1
/usr/bin/python3 /usr/sbin/waydroid status | head -8

# restart pattern that keeps the display
/usr/bin/python3 /usr/sbin/waydroid session stop;  sleep 3
/usr/bin/python3 /usr/sbin/waydroid session start & sleep 45
$ADB connect $SERIAL
```

Two notes that cost time if unknown:

- Call it as `/usr/bin/python3 /usr/sbin/waydroid`. A bare `waydroid` may resolve to a wrapper
  that loses the environment and reports the container as missing.
- `waydroid session start` must run as the session user (uid 1000), never root, or the display
  connection fails.

## adb over TCP

```bash
$ADB connect $SERIAL
$ADB devices                      # <guest-ip>:5555   device
```

If the device shows `offline` repeatedly, the guest adbd key is missing. `scripts/wd_adbkey.sh`
fixes it and **must run as root** (it writes `/data/misc/adb/adb_keys` and calls
`waydroid shell`). It authorises the host's `~/.android/adbkey.pub`, writes
`/data/misc/adb/adb_keys`, and sets `service.adb.tcp.port=5555`:

```bash
sudo bash scripts/wd_adbkey.sh
$ADB devices                      # state must be "device"
```

Scope note: `wd_adbkey.sh` and `wd_fix.sh` need **general root** (they call `lxc-unfreeze` /
`waydroid shell`), so the wrapper-only sudoers rule does not cover them — run them as root once, or
fold the same commands into a `sudo wd-root '…'` call if you want a single privileged path.

`adb root` **does not work** in Waydroid (`id` stays `uid=2000`). Anything needing root goes
through `lxc-attach` (below).

## Proxy, verified in both directions

```bash
ss -ltn | grep -q ':8080' && echo proxy-listening        # 1. host side is up
$ADB shell 'ping -c1 -W2 192.168.240.1' | tail -1        # 2. guest reaches the host
$ADB shell "settings put global http_proxy 192.168.240.1:8080"
$ADB shell "settings get global http_proxy"              # 3. 192.168.240.1:8080
```

Step 2 is the one that catches host firewalls (`nftables` / `firewalld` blocking the container
bridge); without it, "no traffic" gets misdiagnosed as a mitmproxy fault.

**Re-set and re-check the proxy after every session restart** — do not assume it survived. Clear
it when a clean network is needed: `settings put global http_proxy :0`.

## Trusting the mitmproxy CA

> **Threat model before you touch this section.** Installing a CA into `/system/etc/security/cacerts`
> makes **every** app in that image trust your proxy — including banking, mail and anything you later
> install. It breaks the device's TLS model on purpose. Do it only on a throwaway Waydroid container
> with no personal accounts, and rebuild the image (`waydroid init -f`) when you are done. Never do
> this on a physical phone. The reason it is needed is neutral: Android trusts system CAs for apps that
> do not opt into user CAs, so a user-installed certificate would be ignored by the SDKs this rig
> depends on. That is a statement about Android, not a licence to intercept traffic you have no right
> to.

Android only trusts user-added CAs for apps that opt in, and most ad SDKs do not, so the CA must
go into the **system** store. Generate the CA on *this* machine — never copy a CA private key
from another rig: whoever holds that key can impersonate any site to your device, and the file
sits next to the documentation you are reading.

```bash
# 1. mint the CA for this machine (first run of mitmdump)
$HOME/playables/mitmvenv/bin/mitmdump --set confdir=$HOME/playables/adcapture/mitmconf

# 2. name it the way Android expects — export it, the block below splices the value in
export H=$(openssl x509 -inform PEM -subject_hash_old \
      -in $HOME/playables/adcapture/mitmconf/mitmproxy-ca-cert.pem | head -1)
echo $H                                    # e.g. <ca-hash> — your value will differ
cp $HOME/playables/adcapture/mitmconf/mitmproxy-ca-cert.pem /tmp/$H.0
$ADB push /tmp/$H.0 /data/local/tmp/$H.0
```

Install it with a guard, so a failure cannot leave `/system` mounted read-write. **Quoting matters
here:** the container script is single-quoted, so `$(…)` and `[ … ]` run *inside* the container, and
the filename is spliced in from the host with `'"$H"'`. A double-quoted block expands `$H` and
`$(ls …)` on the host — where neither path exists — and the backup check then aborts every time.

```bash
sudo wd-root '
  export PATH=/system/bin:/system/xbin
  set -e
  trap "mount -o remount,ro /system" EXIT
  mount -o remount,rw /system
  rm -rf /data/local/tmp/cacerts.bak
  cp -a /system/etc/security/cacerts /data/local/tmp/cacerts.bak
  n=$(ls /data/local/tmp/cacerts.bak | wc -l)
  [ "$n" -ge 1 ] || { echo "backup empty"; exit 1; }
  cp /data/local/tmp/'"$H"'.0 /system/etc/security/cacerts/
  chmod 644 /system/etc/security/cacerts/'"$H"'.0
  chown root:root /system/etc/security/cacerts/'"$H"'.0
'
$ADB shell 'mount | grep " /system "'                        # must be back to "ro"
$ADB shell "ls -l /system/etc/security/cacerts/$H.0"         # the file, 644 root:root
```

Verified mechanics on the reference rig: with `export H`, the splice produces the right filename
inside the container (`echo name='"$H"'.0` → `name=deadbeef.0`), the inner `$(ls … | wc -l)` counts
container files, and `sudo -E` is **not** available (`sudo: sorry, you are not allowed to preserve
the environment`) — hence the splice instead of an environment variable.

Notes:

- `/system` is read-only in normal operation (`touch` returns `Read-only file system`); the
  remount above is the only write.
- A verified copy of the original directory is kept at `/data/local/tmp/cacerts.bak` (the install
  aborts if the copy is empty). Roll back inside the same rw window:

  ```bash
  sudo wd-root '
    export PATH=/system/bin:/system/xbin
    set -e
    trap "mount -o remount,ro /system" EXIT
    n=$(ls /data/local/tmp/cacerts.bak 2>/dev/null | wc -l)
    [ "$n" -ge 1 ] || { echo "no backup, refusing"; exit 1; }
    mount -o remount,rw /system
    rm -f /system/etc/security/cacerts/'"$H"'.0
    cp -a /data/local/tmp/cacerts.bak/. /system/etc/security/cacerts/
    ls /system/etc/security/cacerts | wc -l
  '
  ```

  The rollback refuses to run without a backup and prints the resulting entry count, so a failed
  restore is visible instead of silent.

- `waydroid init` and image updates wipe the CA — re-install afterwards.
- Presence is not trust. Verify the CA is *used*: any HTTPS request must decrypt in mitmproxy.
  A CA file that exists but is not trusted looks exactly like "the app shows no ads".

## Root inside the container: lxc-attach

Needed for: reading app-private data, installing the CA, staging the WebView cache, and anything
`adb shell` cannot do as uid 2000. Two details make it work, and both are non-obvious:

```bash
# WRONG - "Failed to get init pid": the container path is not the default
sudo lxc-attach -n waydroid -- id

# RIGHT - the path comes from the running process
pgrep -af lxc-start
# lxc-start -P /var/lib/waydroid/lxc -F -n waydroid
sudo wd-root '
  export PATH=/system/bin:/system/xbin       # without this: "Failed to exec id"
  ls /data/data/com.quok.screwJam'
```

The rig's sudoers rule (`config/sudoers-waydroid-lxc.txt`). Install it as a validated drop-in —
a syntactically broken file in `/etc/sudoers.d/` breaks `sudo` entirely:

```bash
bash scripts/configure.sh          # 0. writes config/sudoers-waydroid-lxc.generated (gitignored, keeps
                                  #    the published template with __USER__ untouched)
sudo install -m 0755 config/wd-root.sh /usr/local/sbin/wd-root   # 1. the wrapper the rule names
sudo visudo -cf config/sudoers-waydroid-lxc.generated        # 2. validate the LOCALISED copy first
sudo install -m 0440 config/sudoers-waydroid-lxc.generated /etc/sudoers.d/waydroid-lxc
sudo visudo -c                                            # 3. whole set still parses
sudo -n wd-root 'id' | grep -c 'uid=0'                    # 4. rule is live -> 1
```

Validate before installing: a broken file in `/etc/sudoers.d/` takes `sudo` down with it, and this
rule is what all cache and CA work depends on.

**Pinning is done by the wrapper, not by the rule.** A trailing `*` in sudoers matches any remaining
words — including repeated `-P` / `-n`, and `lxc-attach` takes the last flag value. That is why every
container command in this station is written as `sudo wd-root '<script>'`: the wrapper
(`config/wd-root.sh`, installed in step 0 above) bakes the container path in and forwards the
script, so the rule can name exactly one binary:

```
__USER__ ALL=(root) NOPASSWD: /usr/local/sbin/wd-root
```

(`config/sudoers-waydroid-lxc.txt` ships this stricter form; the direct `lxc-attach … *` variant is
equivalent only on a host with no other containers, and the rule itself does not enforce that.)

**Read what it grants: full root inside that one container.** The wrapper takes any script, including
`/system/bin/sh -c …`; it is not a narrow read permission. What keeps the host out of reach is the
wrapper, which hardcodes the container path and name — not the sudoers line itself (a trailing `*`
there would also match extra `-P`/`-n` flags). Inside the container it is root. Verify with
`sudo -n wd-root 'id' | grep -c 'uid=0'`.

App-private data is also visible from the host, but only to root:
`~/.local/share/waydroid/data/data/<pkg>/` is `drwx------`, owned by the app uid.

## Finding the activity to start

`am start` needs a concrete component, which is not guessable:

```bash
$ADB shell "cmd package resolve-activity --brief com.quok.screwJam | tail -1"
# com.quok.screwJam/com.rollic.elephantsdk.ElephantActivity
$ADB shell "am start -n com.quok.screwJam/com.rollic.elephantsdk.ElephantActivity"
$ADB shell "dumpsys window | grep -m1 mCurrentFocus"
```

## Display, letterboxing and tap coordinates

The guest reports the host panel's resolution because it inherits it (a 4K panel gives `3840x2160`). Many games then render
letterboxed: in the reference target the playfield occupied **x 1290..2260** of a 3840-wide
screenshot. Consequences:

- `screencap` returns the full display, so taps use display coordinates directly — but restrict
  computer vision to the window rect, or HUD coins and shop icons register as game objects.
- Read the window rect once per activity:
  `dumpsys window windows | grep -A40 '<Activity>}'` → `display=[x1,y1][x2,y2]`.
- Changing to a phone-like size (`wm size 1280x720`) makes some games letterbox differently and
  moves the shop/ad buttons; the reference rig kept the native size and worked with the letterbox.

## Inventory and identity limits

```
settings get secure advertising_id     -> null
pm list packages | grep vending        -> com.android.vending present but unauthenticated
```

With `advertising_id = null` Google answers with lowest-tier inventory, and Play-sign-in games
open `com.google.android.gms … addaccount.ErrorActivity` and exit. This is the single biggest
reason a capture run yields little: it is **not** a supply problem. Before concluding "the game
has no ads", check the identity.

## Failure modes seen on this device

| symptom | cause | fix |
| --- | --- | --- |
| `Session: STOPPED`, black screen, adb offline | session lifetime | `session stop` + `session start`, then `adb connect` |
| app start → `SecurityException: Package <pkg> is currently frozen` | newly installed package frozen | session restart releases it; `set-inactive` does not |
| black frame, focus on `com.android.documentsui` | file picker holds focus | `pm disable-user --user 0 com.android.documentsui`; undo with `pm enable com.android.documentsui` |
| taps land but nothing happens | wrong coordinate space (window vs display) | compare `screencap` size with `wm size` |
| `Exiting empty application process` in logcat | arm64 Unity title that will not run under the bridge | pick another target |
| `adb root` fails | not supported in Waydroid | use `lxc-attach` |
| `pm clear` on the target wipes the WebView cache and the SDK's `files/al`, `files/bm` (both 0 B afterwards) | `pm clear` is a full data reset | clear only when you want that; otherwise expect an empty cache channel until the next impression |
| no traffic although the proxy is set | host firewall blocks the container bridge | `$ADB shell 'ping -c1 192.168.240.1'`, then open port 8080 on the host |

## Acceptance gate

```bash
/usr/bin/python3 /usr/sbin/waydroid status | grep -cE 'Session:|Container:'   # 2
$ADB devices | grep -c "$SERIAL"                                              # 1
$ADB shell 'settings get global http_proxy'                                   # 192.168.240.1:8080
H=$(openssl x509 -inform PEM -subject_hash_old -in $HOME/playables/adcapture/mitmconf/mitmproxy-ca-cert.pem | head -1)
$ADB shell "ls /system/etc/security/cacerts/$H.0" | grep -c cacerts            # 1
sudo -n wd-root 'export PATH=/system/bin:/system/xbin; id' | grep -c 'uid=0'   # 1
$ADB shell "mount | grep ' /system ' | grep -c '(ro'"                          # 1  (system left read-only)
```

Six green lines and the device is ready to capture. Skip any of them and later symptoms get
misread: a missing CA looks like "no ad traffic", a stale proxy looks like "network dead".

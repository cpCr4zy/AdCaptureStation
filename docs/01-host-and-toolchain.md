# 01 — Host and toolchain

Everything below is what the reference rig runs. Versions matter only where they change
behaviour; those are marked.

## Host

| item | reference value | why it matters |
| --- | --- | --- |
| OS | Arch-based Linux (the reference rig ran CachyOS), kernel 7.3.x | Waydroid needs binder; Arch-based distributions ship `binder_linux` |
| session | Wayland, `WAYLAND_DISPLAY=wayland-1` | Waydroid is a Wayland client; a headless X only host needs Xvfb |
| user | unprivileged, uid 1000 | everything except one `lxc-attach` call runs unprivileged |
| RAM/CPU/disk | 8 GB+ / 4 cores+ / 10 GB free | Waydroid image ~5 GB, captures 100–700 MB |

Verify:

```bash
uname -r                                   # 7.3.x — anything with binder_linux works
echo $WAYLAND_DISPLAY                      # wayland-1 (non-empty)
lsmod | grep -c binder                     # >= 1
```

If `binder` is 0, Waydroid cannot start. Load it and make it persistent:

```bash
sudo modprobe binder_linux
echo binder_linux | sudo tee /etc/modules-load.d/waydroid.conf
lsmod | grep -c binder                     # re-check: >= 1
```

## Python environments (two, deliberately separate)

The bot needs OpenCV/numpy; mitmproxy pulls its own dependency set and pins its own
interpreter. Mixing them causes import errors that look like "mitmproxy is broken".

```bash
# bot + harvesters + converter — needs the 3.14 interpreter
python3.14 -m venv $HOME/playables/botvenv
$HOME/playables/botvenv/bin/pip install -r config/requirements-botvenv.txt

# mitmproxy — needs the 3.13 interpreter
python3.13 -m venv $HOME/playables/mitmvenv
$HOME/playables/mitmvenv/bin/python -m pip install -r config/requirements-mitmvenv.txt
```

Both lock files are `pip freeze` output from the reference rig (`config/requirements-*.txt`),
so the rebuild gets the same versions instead of "latest of everything". Newer versions are
allowed but must pass the acceptance gate.

Reference versions:

```
botvenv    Python 3.14.9   numpy 2.5.5   opencv-python-headless 5.1.0.95
                           pillow 13.0.0  requests 2.34.2  protobuf 7.36.2
                           cryptography 50.0.2
mitmvenv   Python 3.13.13  mitmproxy 12.3.1  (OpenSSL 4.0.3)
```

Verify — both must print a version and exit 0:

```bash
$HOME/playables/botvenv/bin/python -V          # Python 3.14.9
$HOME/playables/mitmvenv/bin/python -V        # Python 3.13.13
$HOME/playables/botvenv/bin/python -c "import cv2, numpy, requests; print(cv2.__version__)"
$HOME/playables/mitmvenv/bin/mitmdump --version | head -3
```

The gallery/converter scripts (`unpack_playable.py`, `make_index.py`, `build_gallery.py`,
`rebuild_manifest.py`, `fix_game_names.py`) are **stdlib-only** except `fix_game_names.py`, which
needs `requests`: any Python ≥ 3.11 works for them, and the `python3 scripts/…` form in the docs is
fine.

## Android platform tools

```bash
mkdir -p ~/Android/Sdk && cd ~/Android/Sdk
# either via sdkmanager or a distro package; the reference uses the SDK zip
sdkmanager "platform-tools" "build-tools;35.0.0"    # build-tools is needed for apksigner (09)
~/Android/Sdk/platform-tools/adb version      # Android Debug Bridge 1.0.41 / 37.0.1
ls ~/Android/Sdk/build-tools/*/apksigner      # present
```

The full path is used everywhere on purpose: `adb` is often absent from `PATH` in
non-interactive shells, and a script that says `adb: command not found` while the device is
fine wastes a debugging cycle.

## Optional analysis tools

| tool | when |
| --- | --- |
| `jadx` | target is pure Java/Kotlin ad code. **Check `.so` first**: `unzip -l apk \| grep 'lib/'` — zero entries means no native code, so Ghidra has nothing to chew on |
| `Ghidra` (`support/analyzeHeadless`) | only if an ad SDK in the target ships `.so` and you need the signing routine |
| `unzip`, `zip`, `curl`, `openssl`, `java` | always; present on any Arch install |

**jadx pitfall (measured):** multi-dex ad apps make it die with `OutOfMemoryError` and leave
whole packages undecompiled. Split first, decompile one dex:

```bash
unzip -q app.apk 'classes*.dex'
grep -c -a '<marker>' classes*.dex          # find the dex that holds what you need
JAVA_OPTS=-Xmx4g jadx -j 2 classes12.dex    # only that one; -Xmx12g needs a 16 GB host
```

## Directory layout the scripts assume

```
$HOME/playables/
    AdCaptureStation/   this documentation (README.md + docs/) + scripts/ + config/ (read-only reference)
    adcapture/          working dir: bot, harvesters, addons, logs, mitmconf/
    botvenv/            Python env for bot + harvesters
    mitmvenv/           Python env for mitmproxy
    captured/           the gallery
        index.html      generated, never hand-edited
        playable/       runnable copies (payload + MRAID shim + metadata comment)
        converter/      unpack_playable.py, make_index.py, README, findings
        manifest.jsonl  capture record (derived index — rebuildable from playable-meta comments)
        misc/           capture tree, invisible from the gallery (see 06.3)
            raw/  gma/  variants/  projects/  wv/
```

Nothing enforces this layout; every script has the base path as a module-level constant and
accepts `CAPTURED_DIR` (converter) or is edited in place (bot, harvesters). Change paths in
the scripts, not by symlinks — a harvester writing to a new `raw/` because someone moved a
directory is a silent failure mode that shows up days later.

## Acceptance gate for this stage

```bash
$HOME/playables/botvenv/bin/python -c "import cv2,numpy,requests,base64,zipfile;print('bot env ok')"
$HOME/playables/mitmvenv/bin/mitmdump --version | head -1
~/Android/Sdk/platform-tools/adb version | head -1
```

Three clean lines = toolchain done. If `mitmdump` is missing from `PATH` but
`$HOME/playables/mitmvenv/bin/mitmdump` exists, that is expected: the rig calls it by
full path.

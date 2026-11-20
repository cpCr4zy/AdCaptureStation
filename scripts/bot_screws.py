"""Autonomous Screw Jam ad-impression farmer.

Goal: keep the ad rotation turning so fresh playable creatives land in the mitm
capture, without a human in the loop.

Loop:
  1. grab a screenshot over adb,
  2. if an ad activity owns the screen -> close it (X taps, BACK, finally
     force-stop + relaunch, progress is saved per level),
  3. otherwise find screw heads (Hough circles, radius 24-40 px + chroma check)
     and tap them one by one,
  4. when nothing is left to tap, press the bright button in the middle of the
     screen (level-complete claim / "GET IT" popup),
  5. every HARVEST_EVERY seconds run the AppLovin harvester and gallery builder.

Usage:
    python3 bot_screws.py --minutes 180
"""
import argparse
import os

HOME = os.path.expanduser("~")

def _guest_serial():
    """The guest address is assigned by DHCP: read it from waydroid, or take $SERIAL."""
    try:
        import subprocess as _sp
        out = _sp.run(["waydroid", "status"], capture_output=True, text=True).stdout
        m = re.search(r"IP address:\s*([0-9.]+)", out)
        return f"{m.group(1)}:5555" if m else ""
    except Exception:
        return ""

import re
import subprocess
import sys
import time
from datetime import datetime

import cv2
import numpy as np

ADB = os.path.join(HOME, "Android/Sdk/platform-tools/adb")
DEV = os.environ.get("SERIAL") or _guest_serial()
PKG = "com.quok.screwJam"
ACT = "com.quok.screwJam/com.rollic.elephantsdk.ElephantActivity"
LOG = os.path.join(HOME, "playables/adcapture/run3h.log")
CAPDIR = os.path.join(HOME, "playables/adcapture")
HARVEST_EVERY = 600          # seconds
TAP_DELAY = 1.9              # Unity drops faster input
AD_WORDS = ("adactivity", "fullscreenactivity", "inmobi", "vungle", "unityads",
            "applovin", "ironsource", "admob", "adcolony", "chartboost")


def log(msg):
    line = f"{datetime.now():%H:%M:%S} {msg}"
    print(line, flush=True)
    with open(LOG, "a") as fh:
        fh.write(line + "\n")


def adb(*args, timeout=60):
    return subprocess.run([ADB, "-s", DEV, *args], capture_output=True, text=True, timeout=timeout)


def shell(cmd, timeout=60):
    return adb("shell", cmd, timeout=timeout).stdout


ORIGIN = [0, 0]          # display offset of the app window
SCALE = [1.0, 1.0]       # screenshot px -> display px


def window_frame(pkg_activity):
    """Return (x1, y1, x2, y2) of the app window on the physical display."""
    out = shell("dumpsys window windows")
    lines = out.splitlines()
    for i, line in enumerate(lines):
        if pkg_activity in line and line.strip().startswith("Window #"):
            for follow in lines[i:i + 40]:
                m = re.search(r"display=\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]", follow)
                if m:
                    return tuple(int(v) for v in m.groups())
    return None


DISPLAY = [0, 0]
DEAD = []        # coordinates that never react to taps


def display_size():
    if DISPLAY[0]:
        return tuple(DISPLAY)
    out = shell("wm size")
    m = re.search(r"(\d+)x(\d+)", out)
    if m:
        DISPLAY[0], DISPLAY[1] = int(m.group(1)), int(m.group(2))
    else:
        DISPLAY[0], DISPLAY[1] = 3810, 2130
    return tuple(DISPLAY)


def set_mapping(shot_w, shot_h):
    """screencap may return the whole display or just the app window."""
    dw, dh = display_size()
    if abs(shot_w - dw) <= 8 and abs(shot_h - dh) <= 8:
        ORIGIN[0], ORIGIN[1] = 0, 0
        SCALE[0] = SCALE[1] = 1.0
        return
    fr = window_frame("ElephantActivity")
    if not fr:
        return
    x1, y1, x2, y2 = fr
    w, h = x2 - x1, y2 - y1
    ORIGIN[0], ORIGIN[1] = x1, y1
    SCALE[0] = w / shot_w if shot_w else 1.0
    SCALE[1] = h / shot_h if shot_h else 1.0


def tap(x, y):
    dx = ORIGIN[0] + x * SCALE[0]
    dy = ORIGIN[1] + y * SCALE[1]
    adb("shell", f"input tap {int(dx)} {int(dy)}")


def swipe(x1, y1, x2, y2, ms=400):
    """Scroll gesture in screenshot coordinates (same mapping as tap)."""
    for v in (x1, y1, x2, y2):
        assert v >= 0
    dx1 = ORIGIN[0] + x1 * SCALE[0]
    dy1 = ORIGIN[1] + y1 * SCALE[1]
    dx2 = ORIGIN[0] + x2 * SCALE[0]
    dy2 = ORIGIN[1] + y2 * SCALE[1]
    adb("shell", f"input swipe {int(dx1)} {int(dy1)} {int(dx2)} {int(dy2)} {ms}")


def screenshot():
    """Waydroid's exec-out mangles binary PNG, so go through the sdcard."""
    tmp = "/data/local/tmp/bot.png"
    local = os.path.join(CAPDIR, "_bot_shot.png")
    adb("shell", f"screencap -p {tmp}", timeout=60)
    r = adb("pull", tmp, local, timeout=60)
    if r.returncode != 0 or not os.path.exists(local) or os.path.getsize(local) < 5000:
        return None
    img = cv2.imread(local, cv2.IMREAD_COLOR)
    return img


def focus():
    out = shell("dumpsys window | grep -m1 mCurrentFocus")
    return out.strip()


def is_ad(focus_line):
    low = focus_line.lower()
    return any(w in low for w in AD_WORDS)


def find_screws(img):
    rx1, ry1, rx2, ry2 = play_rect(img)
    h, w = img.shape[:2]
    crop = img[ry1:ry2, rx1:rx2]
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    gray = cv2.medianBlur(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY), 3)
    cw = max(1, rx2 - rx1)
    min_r, max_r = int(cw * 0.025), int(cw * 0.042)
    circles = cv2.HoughCircles(gray, cv2.HOUGH_GRADIENT, dp=1.2, minDist=int(cw * 0.06),
                               param1=110, param2=30, minRadius=min_r, maxRadius=max_r)
    found = []
    if circles is None:
        return found
    ph = ry2 - ry1
    for cx_, cy_, r in np.round(circles[0]).astype(int):
        # skip the toolbox row and the 5-slot queue above the play field
        if not (ph * 0.30 < cy_ < ph * 0.98):
            continue
        patch = hsv[max(0, cy_ - 7):cy_ + 7, max(0, cx_ - 7):cx_ + 7]
        if patch.size == 0:
            continue
        bright = patch[:, :, 2] > 90
        sat = patch[:, :, 1][bright]
        if bright.sum() < 40 or (sat.size and float(np.median(sat)) < 90):
            continue
        hues = patch[:, :, 0][bright].astype(np.float32)
        if hues.size < 40:
            continue
        rad = np.deg2rad(hues * 2.0)
        hue_deg = np.rad2deg(np.arctan2(np.sin(rad).mean(), np.cos(rad).mean())) % 360.0
        found.append((int(cx_ + rx1), int(cy_ + ry1), float(hue_deg / 2.0)))
    # dedupe near-duplicates
    out = []
    for x, y, hue in sorted(found):
        if all(abs(x - ox) > 35 or abs(y - oy) > 35 for ox, oy, _ in out):
            out.append((x, y, hue))
    # drop coordinates that already proved to be UI, not screws
    return [t for t in out if all(abs(t[0] - dx) > 45 or abs(t[1] - dy) > 45 for dx, dy in DEAD)]


def find_bright_button(img):
    """Large bright rounded rect in the middle of the screen: claim / GET IT."""
    h, w = img.shape[:2]
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    mask = ((hsv[:, :, 2] > 205) & (hsv[:, :, 1] < 70)).astype(np.uint8) * 255
    mask[: int(h * 0.40), :] = 0
    mask[int(h * 0.88):, :] = 0
    mask[:, : int(w * 0.14)] = 0
    mask[:, int(w * 0.86):] = 0
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best = None
    for c in contours:
        x, y, bw, bh = cv2.boundingRect(c)
        if bw < w * 0.10 or bh < h * 0.03 or bw > w * 0.5:
            continue
        if bw / max(bh, 1) < 1.6:
            continue
        area = bw * bh
        if best is None or area > best[0]:
            best = (area, x + bw // 2, y + bh // 2)
    return (best[1], best[2]) if best else None


def content_rect(img):
    """Bounding box of non-black pixels: the letterboxed portrait app area."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    cols = np.where(gray.max(axis=0) > 40)[0]
    rows = np.where(gray.max(axis=1) > 40)[0]
    if len(cols) < 50 or len(rows) < 50:
        return None
    return int(cols[0]), int(rows[0]), int(cols[-1]) + 1, int(rows[-1]) + 1


def play_rect(img):
    """Tappable game area: letterbox content bounds intersect the app window."""
    h, w = img.shape[:2]
    cr = content_rect(img)
    if cr:
        x1, y1, x2, y2 = cr
    else:
        fr = window_frame("ElephantActivity")
        if not fr:
            return 0, 0, w, h
        x1, y1, x2, y2 = fr
    if x2 - x1 < 100 or y2 - y1 < 100:
        return 0, 0, w, h
    # the last ~9% of the window is the banner slot: never tap there
    return max(0, x1), max(0, y1), min(w, x2), int(y2 - (y2 - y1) * 0.09)


def find_toolbox_hue(img, prefer=None):
    """Hue of the frame of the toolbox that is in play (top-centre of the game)."""
    x1, y1, x2, y2 = play_rect(img)
    w, h = x2 - x1, y2 - y1
    if w < 50 or h < 50:
        return None
    sub = img[y1:y2, x1:x2]
    hsv = cv2.cvtColor(sub, cv2.COLOR_BGR2HSV)
    band = np.zeros((h, w), np.uint8)
    band[int(h * 0.07):int(h * 0.20), int(w * 0.25):int(w * 0.72)] = 1
    sat = ((hsv[:, :, 1] > 140) & (hsv[:, :, 2] > 120) & (band == 1))
    mask = (sat.astype(np.uint8)) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    n, lab, stats, cent = cv2.connectedComponentsWithStats(mask)
    cands = []
    for i in range(1, n):
        bx, by, bw, bh, area = stats[i]
        if area < 1500 or bw < w * 0.10 or bh < h * 0.02:
            continue
        if bw / max(bh, 1) < 1.4:          # the toolbox is a wide box
            continue
        hues = hsv[:, :, 0][lab == i].astype(np.float32) * 2.0         # cv hue -> degrees
        rad = np.deg2rad(hues)
        mean = np.rad2deg(np.arctan2(np.sin(rad).mean(), np.cos(rad).mean())) % 360.0
        cands.append((float(cent[i][0]), float(area), float(mean / 2.0)))
    if not cands:
        return None
    if prefer is not None and len(cands) > 1:
        # the next box slides in from the right while the current one is still in play,
        # so "right-most" flips the target mid-board: stay with the colour we were using
        near = [c for c in cands if hue_close(c[2], prefer, 8)]
        if near:
            return max(near, key=lambda c: c[1])[2]
    return max(cands, key=lambda c: (c[0], c[1]))[2]


def hue_close(a, b, tol=12):
    """OpenCV hue runs 0..180 and wraps there; tolerances are in those units (2 per degree)."""
    d = abs(a - b)
    d = min(d, 180 - d)
    return d <= tol


def shop_like(img):
    """Shop / offer screens paint the play area blue; levels never do."""
    x1, y1, x2, y2 = play_rect(img)
    h = y2 - y1
    if h < 100:
        return False
    sub = img[y1 + int(h * 0.35):y2, x1:x2]
    hsv = cv2.cvtColor(sub, cv2.COLOR_BGR2HSV)
    blue = ((hsv[:, :, 0] > 100) & (hsv[:, :, 0] < 130) &
            (hsv[:, :, 1] > 120) & (hsv[:, :, 2] > 110))
    return float(blue.mean()) > 0.25


def find_close_button(img):
    """White square with a blue X in the upper-right of the game window.

    Shop, offer and bundle overlays all carry one; tapping it is the only
    reliable way out without guessing at purchase buttons.
    """
    x1, y1, x2, y2 = play_rect(img)
    w, h = x2 - x1, y2 - y1
    if w < 100 or h < 100:
        return None
    sub = img[y1:y1 + int(h * 0.45), x1 + int(w * 0.45):x2]
    hsv = cv2.cvtColor(sub, cv2.COLOR_BGR2HSV)
    white = ((hsv[:, :, 2] > 200) & (hsv[:, :, 1] < 45)).astype(np.uint8) * 255
    white = cv2.morphologyEx(white, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    contours, _ = cv2.findContours(white, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    sh, sw = sub.shape[:2]
    for c in contours:
        bx, by, bw, bh = cv2.boundingRect(c)
        if not (sw * 0.05 < bw < sw * 0.25 and sh * 0.03 < bh < sh * 0.25):
            continue
        if not (0.7 < bw / max(bh, 1) < 1.4):
            continue
        patch_hsv = hsv[by:by + bh, bx:bx + bw]
        blue = ((patch_hsv[:, :, 0] > 95) & (patch_hsv[:, :, 0] < 135) & (patch_hsv[:, :, 1] > 110))
        if blue.sum() < (bw * bh) * 0.03:      # the X itself
            continue
        return (x1 + int(w * 0.45) + bx + bw // 2, y1 + by + bh // 2)
    return None


def find_red_button(img):
    """The 'OUT' button of the out-of-space dialog (red, wide, centred)."""
    h, w = img.shape[:2]
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    red = (((hsv[:, :, 0] < 10) | (hsv[:, :, 0] > 172)) & (hsv[:, :, 1] > 150) & (hsv[:, :, 2] > 150))
    mask = red.astype(np.uint8) * 255
    mask[: int(h * 0.20), :] = 0
    mask[int(h * 0.80):, :] = 0
    mask[:, : int(w * 0.25)] = 0
    mask[:, int(w * 0.75):] = 0
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best = None
    for c in contours:
        x, y, bw, bh = cv2.boundingRect(c)
        if bw < w * 0.08 or bh < h * 0.02 or bw > w * 0.45:
            continue
        if bw / max(bh, 1) < 2.2:
            continue
        if best is None or bw * bh > best[0]:
            best = (bw * bh, x + bw // 2, y + bh // 2)
    return (best[1], best[2]) if best else None


TEMPLATE = os.path.join(CAPDIR, "tpl_keep.png")


def find_keep_template(img):
    """Template match for the green 'KEEP PLAYING' (watch-ad) button."""
    if not os.path.exists(TEMPLATE):
        return None
    tpl = cv2.imread(TEMPLATE)
    if tpl is None or tpl.shape[0] > img.shape[0] or tpl.shape[1] > img.shape[1]:
        return None
    res = cv2.matchTemplate(img, tpl, cv2.TM_CCOEFF_NORMED)
    _, mx, _, loc = cv2.minMaxLoc(res)
    if mx < 0.90:          # 0.75 matched the tan board by accident
        return None
    return loc[0] + tpl.shape[1] // 2, loc[1] + tpl.shape[0] // 2


DENY = []          # tap points that opened the shop instead of an ad
CLOSE_DENY = []    # "close" points that close nothing


def find_green_button(img):
    """The 'KEEP PLAYING' (watch-ad) button of the out-of-space dialog."""
    h, w = img.shape[:2]
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    green = ((hsv[:, :, 0] > 35) & (hsv[:, :, 0] < 85) & (hsv[:, :, 1] > 120) & (hsv[:, :, 2] > 120))
    mask = green.astype(np.uint8) * 255
    mask[: int(h * 0.35), :] = 0
    mask[int(h * 0.75):, :] = 0
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best = None
    for c in contours:
        x, y, bw, bh = cv2.boundingRect(c)
        if bw < w * 0.06 or bh < h * 0.015 or bw > w * 0.40:
            continue
        if bw / max(bh, 1) < 1.8:
            continue
        if best is None or x + bw > best[1] + best[3]:   # the ad button is the right-most
            best = (bw * bh, x, y, bw, bh)
    return (best[1] + best[3] // 2, best[2] + best[4] // 2) if best else None


def close_ad(w, h, rect=None):
    """Try to leave the ad; last resort is force-stop + relaunch.

    The creative renders inside the app window (x 1290..2260 on this device), so the
    close corners must come from that rectangle - tapping 0.035*w lands in the black
    letterbox and the ad never closes.
    """
    x1, y1, x2, y2 = rect or (0, 0, w, h)
    ww, hh = x2 - x1, y2 - y1
    for x, y in ((x1 + int(ww * 0.04), y1 + int(hh * 0.035)),
                 (x2 - int(ww * 0.04), y1 + int(hh * 0.04)),
                 (x1 + int(ww * 0.04), y1 + int(hh * 0.09))):
        tap(x, y)
        time.sleep(1.5)
        if not is_ad(focus()):
            return True
    adb("shell", "input keyevent 4")
    time.sleep(2)
    if not is_ad(focus()):
        return True
    adb("shell", f"am force-stop {PKG}")
    time.sleep(2)
    adb("shell", f"am start -n {ACT}")
    time.sleep(16)
    return False


def harvest():
    r = subprocess.run([sys.executable, os.path.join(CAPDIR, "harvest_applovin.py")],
                       capture_output=True, text=True, cwd=CAPDIR)
    for line in r.stdout.strip().splitlines():
        if "CENTURY" in line or "new variants" in line:
            log("  harvest: " + line.strip())
    subprocess.run([sys.executable, os.path.join(CAPDIR, "make_gallery.py")], capture_output=True, text=True, cwd=CAPDIR)
    n = sum(1 for _ in open(os.path.join(HOME, "playables/captured/manifest.jsonl")))
    log(f"  manifest rows: {n}")


def restart_app():
    """Force-stop and relaunch, then wait for the level to be on screen."""
    DEAD.clear()
    adb("shell", f"am force-stop {PKG}")
    time.sleep(2)
    adb("shell", f"am start -n {ACT}")
    for i in range(30):                  # this emulator needs 25-60 s to load
        time.sleep(3)
        img = screenshot()
        if img is None:
            continue
        h, w = img.shape[:2]
        set_mapping(w, h)
        if shop_like(img):
            adb("shell", "input keyevent 4")
            continue
        if find_toolbox_hue(img) is not None and len(find_screws(img)) >= 3:
            log(f"app restarted, level up after {(i + 1) * 3}s")
            return True
    log("app restarted, still not in a level")
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=int, default=180)
    ap.add_argument("--rush", action="store_true",
                    help="tap screws of any colour to fill the temp slots and force "
                         "the out-of-space dialog (and its rewarded ad) sooner")
    args = ap.parse_args()
    deadline = time.time() + args.minutes * 60
    last_harvest = 0.0
    idle = 0
    dark = 0
    bad = 0
    levels = 0
    last_tb = None
    grace_until = 0.0
    last_level_at = 0.0
    last_keep_tap = None
    stall = 0
    offlevel = 0
    prev = None
    log(f"=== run start: {args.minutes} min ===")

    while time.time() < deadline:
        img = screenshot()
        if img is None:
            log("screenshot failed; reconnecting adb")
            adb("connect", DEV, timeout=30)
            time.sleep(5)
            continue
        h, w = img.shape[:2]
        set_mapping(w, h)
        if time.time() - last_harvest > HARVEST_EVERY:
            log("running harvester")
            harvest()
            last_harvest = time.time()
        f = focus()

        keep = None if is_ad(f) else find_keep_template(img)
        if keep and any(abs(keep[0] - dx) < 50 and abs(keep[1] - dy) < 50 for dx, dy in DENY):
            keep = None
        if keep:
            log(f"out-of-space dialog -> watch-ad button at {keep}")
            tap(*keep)
            time.sleep(7)
            offlevel = 0
            continue

        if is_ad(f):
            log(f"ad on screen: {f.split('u0 ')[-1][:60]}")
            cv2.imwrite(os.path.join(CAPDIR, "ads", f"{int(time.time())}.png"), img)
            if close_ad(w, h, play_rect(img)):
                log("ad closed")
            else:
                log("ad survived -> force-stopped app")
            continue

        if "permissioncontroller" in f:
            log("permission dialog -> allow")
            tap(w // 2, int(h * 0.497))
            time.sleep(3)
            continue

        if "com.android.vending" in f:     # banner tap opened Play Store
            log("play store hijack -> back")
            adb("shell", "input keyevent 4")
            time.sleep(2)
            f2 = focus()
            if "com.android.vending" in f2:
                adb("shell", "am force-stop com.android.vending")
                time.sleep(2)
                restart_app()
            continue

        if float(img.mean()) < 45:        # splash / loading screen or a dark shop page
            if time.time() < grace_until:
                log("dark frame, but an ad is loading -> wait")
                time.sleep(3)
                continue
            dark += 1
            log(f"dark screen, waiting ({dark})")
            if dark == 2:
                # level-complete and transition screens wait for a tap, so a short dark
                # stretch is not a hang: poke the middle once before giving up
                tap(w // 2, h // 2)
            time.sleep(6)
            if dark >= 6:
                log("still dark -> back, then restart")
                adb("shell", "input keyevent 4")
                time.sleep(2)
                restart_app()
                dark = 0
            continue
        dark = 0

        if shop_like(img):
            if last_keep_tap is not None:
                DENY.append(last_keep_tap)
                log(f"that watch-ad point {last_keep_tap} opens the shop -> denied ({len(DENY)} total)")
                last_keep_tap = None
            offlevel += 1
            close_btn = find_close_button(img)
            if close_btn and any(abs(close_btn[0] - cx) < 40 and abs(close_btn[1] - cy) < 40
                                 for cx, cy in CLOSE_DENY):
                # the same point keeps "closing" nothing: it is a false positive, not a shop X
                close_btn = None
            if close_btn and offlevel >= 3:
                CLOSE_DENY.append(close_btn)
                log(f"close point {close_btn} does not work -> denied")
                close_btn = None
            if close_btn:
                # the shop is a panel over the game: its X keeps us in the game, while BACK
                # exits the app outright (verified: focus lands on the launcher)
                log(f"shop/offer screen -> close at {close_btn} ({offlevel})")
                tap(*close_btn)
                time.sleep(3)
                continue
            log(f"shop/offer screen without a close button -> back {offlevel}")
            adb("shell", "input keyevent 4")
            time.sleep(3)
            if offlevel >= 3:
                restart_app()
                offlevel = 0
            continue

        close_btn = find_close_button(img)
        if close_btn:
            log(f"overlay detected -> closing at {close_btn}")
            tap(*close_btn)
            time.sleep(3)
            offlevel = 0
            continue

        tb = find_toolbox_hue(img, last_tb)
        screws = find_screws(img)
        every_screw = list(screws)

        # out-of-space dialog: the green right-hand button plays a rewarded ad,
        # the red one is QUIT (it dumps us into the shop) - always prefer green
        out_btn = find_red_button(img)
        if keep is None and not is_ad(f):
            keep = find_green_button(img) or find_keep_template(img)
        if keep is not None:
            last_keep_tap = keep
            log(f"out-of-space dialog -> keep playing at {keep} (red at {out_btn})")
            tap(*keep)
            # the ad starts on a black screen: give it time instead of treating that as
            # a loading screen and pressing BACK, which cancels the load
            grace_until = time.time() + 25
            time.sleep(6)
            offlevel = 0
            continue
        if out_btn is not None and tb is None:
            # BACK here exits the whole app (verified: focus goes to the launcher), so the only
            # control that advances the game is QUIT - it returns to the map for the next level
            log(f"out-of-space dialog without a usable keep button -> quit at {out_btn}")
            tap(*out_btn)
            time.sleep(4)
            offlevel = 0
            continue

        # not a playable level (shop, level map, offer, ad endcard): never tap blind
        if tb is None or len(screws) < 3:
            claim = find_bright_button(img)
            if claim:
                log(f"reward/continue button at {claim}")
                tap(*claim)
                time.sleep(4)
                offlevel = 0
                continue
            offlevel += 1
            log(f"not in a level (toolbox {tb}, circles {len(screws)}) -> back {offlevel}")
            adb("shell", "input keyevent 4")
            time.sleep(3)
            if offlevel >= 3:
                restart_app()
                offlevel = 0
            continue
        offlevel = 0

        if len(screws) > 70:
            log(f"suspicious screen: {len(screws)} circles -> back")
            adb("shell", "input keyevent 4")
            time.sleep(3)
            continue

        match = [s for s in screws if hue_close(s[2], tb, 8)]
        if not match:
            match = [s for s in screws if hue_close(s[2], tb, 14)]
        screws = match                      # never tap a colour the box cannot take
        if not screws and args.rush:
            # board colour is exhausted: any screw still fills the temporary slots,
            # which is what opens the "out of space" dialog with the rewarded ad
            px1, py1, px2, py2 = play_rect(img)
            top = py1 + int((py2 - py1) * 0.14)
            bottom = py2 - int((py2 - py1) * 0.12)
            spare = [s for s in every_screw
                     if (s[0], s[1]) not in DEAD and px1 < s[0] < px2 and top < s[1] < bottom][:6]
            if spare:
                log(f"rush: tapping {len(spare)} foreign screws to fill temp slots")
                for x, y, _hue in spare:
                    tap(x, y)
                    time.sleep(TAP_DELAY)
                idle = 0
                prev = screenshot()
                continue

        if not screws:
            idle += 1
            log(f"no screw of the box colour left on screen (idle {idle})")
            time.sleep(3)                 # animation / next toolbox may follow
            if 2 <= idle < 6:
                # the conveyor is horizontal and moves only when dragged sideways;
                # a vertical drag is read by the game as an exit gesture and lands in the shop
                x1, y1, x2, y2 = play_rect(img)
                cy = y1 + int((y2 - y1) * 0.55)
                dx = int((x2 - x1) * 0.22)
                log("dragging conveyor sideways for more screws")
                swipe((x1 + x2) // 2 + dx, cy, (x1 + x2) // 2 - dx, cy, 450)
                time.sleep(2)
            if idle > 9:
                restart_app()
                idle = 0
            continue

        if last_tb is not None and not hue_close(tb, last_tb, 6) and time.time() - last_level_at > 25:
            # two boxes are on screen at once, so hue alone flips between frames:
            # only a change that persists for a while means a new board
            DEAD.clear()
            levels += 1
            last_level_at = time.time()
            log(f"board changed -> level {levels + 1}, dead points cleared")
        last_tb = tb

        buckets = {}
        for x, y, hue in screws:
            buckets.setdefault(int(hue // 30), []).append((x, y))
        log(f"level {levels+1}: {len(screws)} screws of hue {tb} in {len(buckets)} groups")
        ordered = [pt for pts in buckets.values() for pt in pts][:6]
        for x, y in ordered:
            tap(x, y)
            time.sleep(TAP_DELAY)
        after = screenshot()
        if prev is not None and after is not None:
            diff = np.abs(after.astype(np.int16) - prev.astype(np.int16)).max(axis=2)
            same = int((diff > 25).sum()) < 800
            if same:
                stall += 1
                DEAD.extend(ordered[:3])
                log(f"no screen change -> {len(DEAD)} dead points, stall {stall}")
                if stall >= 4:
                    restart_app()
                    DEAD.clear()
                    stall = 0
            else:
                stall = 0
        prev = after if after is not None else prev
        idle = 0

        if time.time() - last_harvest > HARVEST_EVERY:
            log("running harvester")
            harvest()
            last_harvest = time.time()

    log("=== run finished ===")
    harvest()


if __name__ == "__main__":
    main()

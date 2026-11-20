"""Diagnose why the bot soft-locks: compare what it thinks the box colour is with the screen."""
import sys

HOME = os.path.expanduser("~")

import cv2
import numpy as np

sys.path.insert(0, os.path.join(HOME, "playables/adcapture"))
import bot_screws as B  # noqa: E402


def main(path):
    img = cv2.imread(path)
    if img is None:
        raise SystemExit(f"cannot read {path}")
    h, w = img.shape[:2]
    B.set_mapping(w, h)
    tb = B.find_toolbox_hue(img)
    screws = B.find_screws(img)
    print(f"image {w}x{h}")
    print(f"toolbox hue: {tb}")
    print(f"screws found: {len(screws)}")
    hue_hist = {}
    for x, y, hue in screws:
        hue_hist.setdefault(int(hue // 15) * 15, []).append((x, y))
    for bucket, pts in sorted(hue_hist.items()):
        print(f"  hue {bucket:3d}-{bucket+14:3d}: {len(pts)} ({pts[0][0]},{pts[0][1]})")
    if tb is not None:
        match = [s for s in screws if B.hue_close(s[2], tb, 25)]
        print(f"screws matching toolbox within 25: {len(match)}")


if __name__ == "__main__":
    main(sys.argv[1])

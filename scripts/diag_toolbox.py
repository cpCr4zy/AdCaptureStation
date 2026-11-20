"""Why does the target colour flip mid-board? Print every toolbox candidate.

The picker used to take the right-most wide box, but two boxes are on screen at once
(the one in play and the next one sliding in), so the target jumped between them.
"""
import subprocess
import sys

HOME = os.path.expanduser("~")

import cv2
import numpy as np

sys.path.insert(0, os.path.join(HOME, "playables/adcapture"))
import bot_screws as B


def candidates(img):
    x1, y1, x2, y2 = B.play_rect(img)
    w, h = x2 - x1, y2 - y1
    sub = img[y1:y2, x1:x2]
    hsv = cv2.cvtColor(sub, cv2.COLOR_BGR2HSV)
    band = np.zeros((h, w), np.uint8)
    band[int(h * 0.07):int(h * 0.20), int(w * 0.25):int(w * 0.72)] = 1
    sat = ((hsv[:, :, 1] > 140) & (hsv[:, :, 2] > 120) & (band == 1))
    mask = cv2.morphologyEx(sat.astype(np.uint8) * 255, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    n, lab, stats, cent = cv2.connectedComponentsWithStats(mask)
    out = []
    for i in range(1, n):
        bx, by, bw, bh, area = stats[i]
        if area < 1500 or bw < w * 0.10 or bh < h * 0.02:
            continue
        hues = hsv[:, :, 0][lab == i].astype(np.float32) * 2.0
        rad = np.deg2rad(hues)
        deg = np.rad2deg(np.arctan2(np.sin(rad).mean(), np.cos(rad).mean())) % 360.0
        out.append({"hue_cv": round(deg / 2.0, 1), "area": int(area),
                    "cx_rel": round(float(cent[i][0]) / w, 3),
                    "cy_rel": round(float(cent[i][1]) / h, 3),
                    "w_rel": round(bw / w, 3), "ratio": round(bw / max(bh, 1), 1)})
    return sorted(out, key=lambda c: -c["area"])


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else None
    if path:
        img = cv2.imread(path)
    else:
        img = B.screenshot()
    if img is None:
        raise SystemExit("no screenshot")
    rect = B.play_rect(img)
    print("play_rect:", rect, "frame:", img.shape[1], "x", img.shape[0])
    for c in candidates(img):
        print("  ", c)
    print("chosen without prefer:", B.find_toolbox_hue(img))
    for prefer in (4.0, 102.0):
        print(f"chosen with prefer={prefer}:", B.find_toolbox_hue(img, prefer))


if __name__ == "__main__":
    main()

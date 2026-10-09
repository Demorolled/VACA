#!/usr/bin/env python3
"""Quick pixel-level sanity check of a Colab screenshot.

Counts colored (non-white/gray) pixels, finds distinct horizontal color bands
that could be progress bars, and reports whether the image looks busy or blank.
"""
import sys

from PIL import Image

path = sys.argv[1]
im = Image.open(path).convert("RGB")
w, h = im.size
px = im.load()

colored = 0
band_rows = {}
for y in range(0, h, 2):
    row_colors = set()
    for x in range(0, w, 4):
        r, g, b = px[x, y]
        # count pixels that are clearly not white/near-white or black text
        if abs(r - g) > 30 or abs(g - b) > 30 or (r + g + b) > 650:
            row_colors.add((r // 64, g // 64, b // 64))
            colored += 1
    if len(row_colors) >= 3:
        band_rows[y] = len(row_colors)

print(f"size: {w}x{h}")
print(f"colored-ish samples: {colored}")
print(f"rows with many distinct colors (possible progress bars / spinners): {len(band_rows)}")
if band_rows:
    ys = sorted(band_rows)
    print("  y-range:", ys[0], "-", ys[-1])

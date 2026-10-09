#!/usr/bin/env python3
"""Decode an XWD (X Window Dump) file to PNG using only PIL + struct.

XWD header is a fixed 100-byte block of CARD32 fields (see xwd(1)/X11
source). xwd writes the header in big-endian (protocol) order while the
byte_order field describes the *image data* order (0=LSBFirst, 1=MSBFirst).
24bpp TrueColor pixels are stored in 32-bit words (one pad byte per pixel).
"""
import struct
import sys
from PIL import Image

HDR_FIELDS = ('header_size', 'file_version', 'pixmap_format', 'pixmap_depth',
              'pixmap_width', 'pixmap_height', 'xoffset', 'byte_order',
              'bitmap_unit', 'bitmap_bit_order', 'bitmap_pad',
              'bits_per_pixel', 'bytes_per_line', 'visual_class', 'red_mask',
              'green_mask', 'blue_mask', 'bits_per_rgb', 'colormap_entries',
              'ncolors', 'window_width', 'window_height', 'window_x',
              'window_y', 'window_border_width')


def xwd_to_image(path: str) -> Image.Image:
    with open(path, 'rb') as f:
        data = f.read()
    if len(data) < 100:
        raise ValueError('file too small to be XWD')

    def parse(endian):
        return dict(zip(HDR_FIELDS, struct.unpack(endian + '25I', data[:100])))

    h = parse('>')  # xwd writes the header big-endian (X11 protocol order)
    if not (100 <= h['pixmap_width'] <= 8000 and
            100 <= h['pixmap_height'] <= 8000 and h['ncolors'] < 4096):
        h = parse('<')
    w, hgt = h['pixmap_width'], h['pixmap_height']
    bpl = h['bytes_per_line']
    ncolors = h['ncolors']
    print(f'XWD: {w}x{hgt} depth={h["pixmap_depth"]} '
          f'bpp={h["bits_per_pixel"]} bpl={bpl} ncolors={ncolors} '
          f'byte_order={h["byte_order"]} '
          f'rm={h["red_mask"]:#x} gm={h["green_mask"]:#x} bm={h["blue_mask"]:#x}',
          file=sys.stderr)
    offset = h['header_size'] + ncolors * 12  # colormap: 3 CARD32 per entry
    img = Image.new('RGB', (w, hgt))
    px = img.load()
    # Standard TrueColor 24bpp-in-32bit: R in the high byte.
    r_hi = (h['red_mask'] == 0xFF0000 and h['green_mask'] == 0xFF00 and
            h['blue_mask'] == 0xFF)
    little = h['byte_order'] == 0
    for y in range(hgt):
        start = offset + y * bpl
        line = data[start:start + bpl]
        for x in range(w):
            b0 = line[x * 4]
            b1 = line[x * 4 + 1]
            b2 = line[x * 4 + 2]
            if little:
                b, g, r = b0, b1, b2
            else:
                r, g, b = b0, b1, b2
            if not r_hi:
                r, g, b = b, g, r
            px[x, y] = (r, g, b)
    return img


if __name__ == '__main__':
    src, dst = sys.argv[1], sys.argv[2]
    img = xwd_to_image(src)
    img.save(dst)
    print(f'wrote {dst} {img.size}')

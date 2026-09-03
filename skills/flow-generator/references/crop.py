#!/usr/bin/env python3
"""Cut a graphic out of a REFERENCE image and, optionally, key its backdrop away.

Why this ships: a reference screenshot often contains the only copy of a graphic the format
cannot express -- a multicolour or gradient icon, an illustration, a decorative surface. The
ladder in media.md used to jump straight from "a file you were given" to "draw it yourself",
and a graphic you drew is your approximation of someone's design wearing a finished look. Their
own pixels beat it, so this rung sits above that one.

    crop.py ref.png out.png --box 872,540,930,712              # plain crop
    crop.py ref.png out.png --box 872,540,930,712 --key        # + knock the backdrop out
    crop.py ref.png out.png --box ... --key --fit 120x120      # + check it against the drawn box

CROP A GRAPHIC, NEVER A REGION CONTAINING TEXT OR DATA. Baked words cannot be translated, cannot
carry a variable, and if they are app data -- a server name, an IP, a price -- they are a picture
of one moment pretending to be live. Measured: an agent cropped a whole server-list card and
shipped five labels and an IP address as a bitmap, and nothing objected. If the region is mostly
text it is a composition, not an asset: build it, and crop only the graphic inside it.

Writes `out.png` (RGBA) and, with --key, `out.contact.png` -- the result over black, white and
mid grey. LOOK AT THE CONTACT SHEET. It is the check, not a courtesy: the one failure this tool
cannot detect for you is a graphic that CONTAINS the backdrop colour, and the contact sheet shows
it instantly (measured: a white flag on a white card comes back as its red parts alone).

Pure stdlib, PNG in / PNG out, 8-bit non-interlaced -- macOS screenshots and Chrome captures
qualify, a JPEG reference does not. Reuses montage.py's decoder.

Exit codes: 0 wrote it, 1 refused (read the message), 2 unreadable input or usage.
"""
import os
import struct
import sys
import zlib
from collections import deque

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from montage import read_png  # noqa: E402

# The backdrop must actually BE a backdrop. Measured on real references: a flat card reads 4-12,
# a crumpled-paper texture reads 144, and a box cropped tight enough to clip the graphic reads
# 173-241 because the border is sampling ink rather than backdrop. Those last two are different
# problems with the same number, so the refusal says both.
UNIFORM_MAX = 24

# Alpha ramps across the anti-aliased band, expressed as a FRACTION of how far this crop's ink
# actually sits from its backdrop rather than as an absolute channel distance. Absolute numbers
# cannot serve both a low-contrast edge (cream to orange, 196 apart) and a high-contrast one
# (white to black, 250): a fixed band wide enough for the first leaves a 50% blend on the second
# outside it entirely, opaque and still carrying its rim of backdrop.
T_IN_FRAC, T_OUT_FRAC = 0.06, 0.55

# Everything was backdrop. A uniform crop has deviation 0, so it sails through the flatness guard
# and then keys away to nothing -- an empty PNG that binds fine and draws nothing.
MAX_REMOVED = 0.97

# The box is in POINTS and the asset scales into it, so a 1x crop is soft on a 2x/3x device --
# the same reason media.md says to draw at 2-3x.
MIN_SCALE = 2.0


def chan_dist(p, k):
    return max(abs(p[0] - k[0]), abs(p[1] - k[1]), abs(p[2] - k[2]))


def crop_box(rows, nch, box):
    x0, y0, x1, y1 = box
    return [[[r[x * nch], r[x * nch + 1], r[x * nch + 2], 255] for x in range(x0, x1)]
            for r in (rows[y] for y in range(y0, y1))]


def border_stats(px):
    """-> (key colour, max deviation) over the 1px border. The backdrop, if there is one."""
    h, w = len(px), len(px[0])
    edge = ([px[0][x] for x in range(w)] + [px[h - 1][x] for x in range(w)]
            + [px[y][0] for y in range(h)] + [px[y][w - 1] for y in range(h)])
    key = [sum(p[i] for p in edge) / len(edge) for i in range(3)]
    return key, max(chan_dist(p, key) for p in edge)


def ink_span(px, key):
    """How far this crop's ink sits from its backdrop, at the 95th percentile.

    A percentile rather than the max, so one stray pixel cannot stretch the band.
    """
    d = sorted(chan_dist(p, key) for row in px for p in row)
    return d[int(len(d) * 0.95)] or 1


def key_backdrop(px, key):
    """Flood the backdrop inward from the border. Soft alpha across the AA band, unpremultiplied.

    Flooding rather than thresholding is what protects a graphic's INTERIOR: the white stripes
    inside a US flag survive because they are enclosed, while a white field that touches the
    silhouette's edge does not -- the flood walks straight through it. That asymmetry is real and
    is the whole reason the contact sheet exists.

    Unpremultiplying is what removes the halo. An edge pixel is a blend of ink and backdrop; give
    it partial alpha without recovering the ink and it keeps a rim of the backdrop, invisible over
    a similar colour and obvious over its opposite. Recovery is APPROXIMATE and cannot be exact --
    a flat composite does not record what the ink under a blend was, so a 50% edge comes back
    close to the ink rather than on it. Close is the difference between a visible rim and none.
    """
    span = ink_span(px, key)
    t_in, t_out = T_IN_FRAC * span, T_OUT_FRAC * span
    h, w = len(px), len(px[0])
    seen = [[False] * w for _ in range(h)]
    q = deque()
    for x in range(w):
        for y in (0, h - 1):
            if not seen[y][x] and chan_dist(px[y][x], key) <= t_out:
                seen[y][x] = True
                q.append((x, y))
    for y in range(h):
        for x in (0, w - 1):
            if not seen[y][x] and chan_dist(px[y][x], key) <= t_out:
                seen[y][x] = True
                q.append((x, y))
    while q:
        x, y = q.popleft()
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < w and 0 <= ny < h and not seen[ny][nx] \
                    and chan_dist(px[ny][nx], key) <= t_out:
                seen[ny][nx] = True
                q.append((nx, ny))
    removed = 0
    for y in range(h):
        for x in range(w):
            if not seen[y][x]:
                continue
            p = px[y][x]
            d = chan_dist(p, key)
            # Clamped explicitly. The flood only admits pixels with d <= t_out, so this is
            # in range today by an invariant enforced somewhere else entirely -- and when a
            # negative test broke that invariant, the symptom was a ValueError deep in the PNG
            # writer that reads like a corrupt image rather than a logic error.
            a = 0 if d <= t_in else max(0, min(255, int(255 * (d - t_in) / (t_out - t_in))))
            if a == 0:
                p[0] = p[1] = p[2] = 0
                removed += 1
            else:
                f = a / 255.0
                for i in range(3):
                    p[i] = max(0, min(255, int((p[i] - key[i] * (1 - f)) / f)))
            p[3] = a
    return removed / float(w * h)


def over(px, bg):
    return [[[int(p[i] * (p[3] / 255.0) + bg[i] * (1 - p[3] / 255.0)) for i in range(3)] + [255]
             for p in row] for row in px]


def contact(px):
    blocks = [px, over(px, (0, 0, 0)), over(px, (255, 255, 255)), over(px, (128, 128, 128))]
    g, mag = 12, [255, 0, 255, 255]
    h = len(px)
    w = sum(len(b[0]) for b in blocks) + g * (len(blocks) - 1)
    out = [[list(mag) for _ in range(w)] for _ in range(h)]
    x = 0
    for b in blocks:
        for y, row in enumerate(b):
            for i, p in enumerate(row):
                out[y][x + i] = p
        x += len(b[0]) + g
    return out


def write_rgba(path, px):
    h, w = len(px), len(px[0])
    raw = b''.join(b'\x00' + bytes(v for p in row for v in p) for row in px)

    def chunk(tag, data):
        body = tag + data
        return struct.pack('>I', len(data)) + body + struct.pack('>I', zlib.crc32(body) & 0xffffffff)

    png = (b'\x89PNG\r\n\x1a\n'
           + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0))
           + chunk(b'IDAT', zlib.compress(raw, 9))
           + chunk(b'IEND', b''))
    with open(path, 'wb') as fh:
        fh.write(png)


def run(src, dst, box, do_key=False, fit=None):
    """-> (exit code, [lines]). Split out from main so the tests can drive it in-process."""
    notes = []
    try:
        w, h, nch, rows = read_png(src)
    except Exception as exc:                                  # noqa: BLE001 - message is the point
        return 2, [f'cannot read {src}: {exc}']
    x0, y0, x1, y1 = box
    if not (0 <= x0 < x1 <= w and 0 <= y0 < y1 <= h):
        return 2, [f'--box {x0},{y0},{x1},{y1} is outside the {w}x{h} image']
    px = crop_box(rows, nch, box)
    cw, ch = x1 - x0, y1 - y0
    key, dev = border_stats(px)
    notes.append(f'crop {cw}x{ch} from {src}')

    if do_key:
        notes.append(f'backdrop ({key[0]:.0f},{key[1]:.0f},{key[2]:.0f}) max deviation {dev:.0f}')
        if dev > UNIFORM_MAX:
            return 1, notes + [
                f'REFUSED: the border is not a flat backdrop ({dev:.0f} > {UNIFORM_MAX}).',
                'Two different causes, same number -- check which one you have:',
                '  * the box clips the graphic, so the border is sampling ink. Widen it until',
                '    there is clean backdrop on all four sides, then run again.',
                '  * the backdrop really is textured or a gradient. It cannot be keyed: there is',
                '    no single colour to remove and no alpha to recover from a flat screenshot.',
                '    Ship a styled empty image and put the asset on the ask list.']
        removed = key_backdrop(px, key)
        if removed > MAX_REMOVED:
            return 1, notes + [
                f'REFUSED: {removed * 100:.0f}% of the crop was removed as backdrop -- there is',
                'no graphic in this box, only backdrop. Check the coordinates against the',
                'reference; --box is x0,y0,x1,y1 in the SOURCE image, and a reference with a',
                'device frame needs its screen bounds located first (preview.md).']
        notes.append(f'keyed: {removed * 100:.0f}% of the crop removed as backdrop')
        notes.append(f'LOOK AT {dst[:-4] + ".contact.png"} before you bind this. If the graphic')
        notes.append('  contains the backdrop colour, that part of it is now missing -- a white')
        notes.append('  mark on a white card comes back as its coloured parts alone. Nothing here')
        notes.append('  can tell you that; the contact sheet shows it at a glance.')

    if fit:
        fw, fh = fit
        scale = min(cw / float(fw), ch / float(fh))
        if scale < MIN_SCALE:
            notes.append(f'WARNING: {cw}x{ch} into a {fw}x{fh} pt box is {scale:.1f}x -- the box is')
            notes.append(f'  in points, so this is soft on a 2x/3x device. Want {MIN_SCALE:.0f}x+.')
            notes.append('  Ask for a higher-resolution export rather than upscaling this.')

    write_rgba(dst, px)
    notes.append(f'wrote {dst}')
    if do_key:
        cpath = dst[:-4] + '.contact.png' if dst.endswith('.png') else dst + '.contact.png'
        write_rgba(cpath, contact(px))
        notes.append(f'wrote {cpath} (raw | over black | over white | over grey)')
    return 0, notes


def main(argv):
    if len(argv) < 3:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    src, dst, args = argv[0], argv[1], argv[2:]
    box = fit = None
    do_key = False
    i = 0
    while i < len(args):
        if args[i] == '--key':
            do_key = True
        elif args[i] == '--box' and i + 1 < len(args):
            i += 1
            try:
                box = tuple(int(v) for v in args[i].split(','))
            except ValueError:
                print('--box wants x0,y0,x1,y1', file=sys.stderr)
                return 2
            if len(box) != 4:
                print('--box wants x0,y0,x1,y1', file=sys.stderr)
                return 2
        elif args[i] == '--fit' and i + 1 < len(args):
            i += 1
            try:
                fit = tuple(int(v) for v in args[i].lower().split('x'))
            except ValueError:
                print('--fit wants WxH', file=sys.stderr)
                return 2
            if len(fit) != 2:
                print('--fit wants WxH', file=sys.stderr)
                return 2
        else:
            print(f'unknown argument: {args[i]}', file=sys.stderr)
            return 2
        i += 1
    if box is None:
        print('--box x0,y0,x1,y1 is required', file=sys.stderr)
        return 2
    code, lines = run(src, dst, box, do_key, fit)
    for line in lines:
        print(line, file=sys.stderr if code else sys.stdout)
    return code


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))

#!/usr/bin/env python3
"""Measure a flow render, instead of eyeballing it.

Why this exists: "the connector line looks too narrow" sent a whole session's worth of edits
at an element that was exactly the right size. The same screenshot, measured, said the widths
were correct (38 against a 46 chip) and that the real defect was a **14px break** before the
next chip — a gradient fading out onto the page colour. One is a hunch, the other is a bug
report. Reach for this whenever a judgement about a render is about position or size.

Stdlib only (no Pillow): 8-bit non-interlaced PNG, which is what headless Chrome writes.

    # is a column continuous? (connectors, timelines, rails, dividers)
    render-measure.py shot.png --column 23:68
    render-measure.py shot.png --column 23:68 --rows 300:700

    # how wide is a thing, actually? (chips, cards, buttons)
    render-measure.py shot.png --row 343
    render-measure.py shot.png --row 343 --cols 0:120

    # comparing against a reference screenshot at a different scale
    render-measure.py ref.png --column 50:121 --scale 602:390

`--column` reports painted vertical runs and the GAPS between them; zero gaps is what
"connected" means. `--row` reports painted horizontal runs, i.e. widths. Both decide "painted"
by distance from a sampled background pixel, so pick `--bg` inside the page, not on a card.
"""
import argparse, collections, struct, sys, zlib

# Share of one colour above which a PNG is not a render. Reused verbatim from
# `tests/render-check.py`, where it was calibrated against real paywall renders; the page it
# exists to reject is Chrome's own error screen, which measured 99.7% there. Re-measured
# 2026-08-26 on five DNS-error screenshots from a GREEN round: 97.7-98.0% one colour with
# 217-228 distinct colours -- so a colour COUNT cannot catch this and the share can.
MAX_DOMINANT_SHARE = 0.95
# ...but flatness ALONE cannot separate the two classes, and shipping it alone was a real
# false-positive source: four agents in one GREEN round (2026-08-28) had good renders renamed
# `NOT-A-RENDER-*`. Re-measured over 15 real renders and 4 error pages, the ranges OVERLAP --
# real renders run 0.502-0.991 one colour and error pages 0.976-1.000, so a sparse light signup
# screen (0.991) is FLATTER than the DNS-error page the guard exists to catch (0.976).
#
# What does separate them is WHERE the ink sits. An error page is one clump of text in the
# middle of an empty viewport; an app screen distributes content down the frame. `ink span` is
# the vertical extent from the first inked row to the last, over the height:
#
#     error pages   n=4   span 0.000-0.332      (blank page is 0.000)
#     real renders  n=15  span 0.211-1.000
#
# Those overlap too -- a one-section carousel render is legitimately 0.211 -- so NEITHER axis
# works alone and the gate needs BOTH: flag only what is very flat AND confined to a band.
# Against that rule the full set is 19/19 correct, with the nearest real render 0.057 clear on
# flatness (0.893 where 0.95 is needed) and 0.155 clear on span (0.655 where < 0.50 is needed).
MIN_INK_SPAN = 0.50
# A pixel counts as ink at this Manhattan distance from the dominant colour -- above
# antialiasing, below any real content.
INK_DELTA = 60


def read_png(path):
    data = open(path, 'rb').read()
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        sys.exit(f'{path}: not a PNG')
    pos, idat, w = 8, b'', None
    while pos < len(data):
        ln = struct.unpack('>I', data[pos:pos + 4])[0]
        typ, body = data[pos + 4:pos + 8], data[pos + 8:pos + 8 + ln]
        pos += 12 + ln
        if typ == b'IHDR':
            w, h, depth, ctype, _, _, interlace = struct.unpack('>IIBBBBB', body[:13])
            if depth != 8:
                sys.exit(f'{path}: {depth}-bit PNG; only 8-bit is supported')
            if interlace:
                sys.exit(f'{path}: interlaced PNG is not supported')
        elif typ == b'IDAT':
            idat += body
        elif typ == b'IEND':
            break
    if w is None:
        sys.exit(f'{path}: no IHDR')
    chans = {0: 1, 2: 3, 4: 2, 6: 4}[ctype]
    raw, stride = zlib.decompress(idat), w * chans
    out, prev, pos = bytearray(), bytearray(stride), 0
    for _ in range(h):
        f = raw[pos]; pos += 1
        line = bytearray(raw[pos:pos + stride]); pos += stride
        for x in range(stride):
            a = line[x - chans] if x >= chans else 0
            b = prev[x]
            c = prev[x - chans] if x >= chans else 0
            if f == 1:   line[x] = (line[x] + a) & 255
            elif f == 2: line[x] = (line[x] + b) & 255
            elif f == 3: line[x] = (line[x] + (a + b) // 2) & 255
            elif f == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[x] = (line[x] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        out += line; prev = line
    return w, h, chans, bytes(out)


def runs_of(on):
    """Contiguous runs from a sorted list of coordinates. Tolerates 1px antialiasing holes."""
    if not on:
        return []
    out, start, prev = [], on[0], on[0]
    for v in on[1:]:
        if v > prev + 2:
            out.append((start, prev, prev - start + 1))
            start = v
        prev = v
    out.append((start, prev, prev - start + 1))
    return out


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument('png')
    ap.add_argument('--sanity', action='store_true',
                    help='is this a render at all? exits 1 on a flat page (a Chrome error '
                         'screen screenshots perfectly and is mostly one colour)')
    ap.add_argument('--column', metavar='X0:X1', help='strip to scan downward, for continuity')
    ap.add_argument('--row', type=int, metavar='Y', help='scanline to measure widths on')
    ap.add_argument('--rows', metavar='Y0:Y1', help='limit --column to these rows')
    ap.add_argument('--cols', metavar='X0:X1', help='limit --row to these columns')
    ap.add_argument('--bg', metavar='X,Y', help='pixel to sample the background from')
    ap.add_argument('--threshold', type=int, default=10,
                    help='channel-sum distance from bg that counts as painted (default 10)')
    ap.add_argument('--scale', metavar='IMGW:PTS',
                    help='also print points, dividing by (image width / device points)')
    a = ap.parse_args()
    if a.sanity:
        if a.column or a.row:
            ap.error('--sanity takes no other measurement')
    elif (a.column is None) == (a.row is None):
        ap.error('pass exactly one of --column or --row')

    w, h, chans, buf = read_png(a.png)
    if a.sanity:
        # Every 3rd pixel: 20x cheaper and the share does not move meaningfully.
        counts = collections.Counter()
        for y in range(0, h, 3):
            row = y * w * chans
            for x in range(0, w, 3):
                i = row + x * chans
                counts[buf[i:i + 3]] += 1
        total = sum(counts.values()) or 1
        bg, n = counts.most_common(1)[0]
        dom = n / total
        # The span pass runs only for an image that is already suspiciously flat, so the
        # common case still costs one pass over the pixels.
        span = None
        if dom > MAX_DOMINANT_SHARE:
            first = last = None
            for y in range(0, h, 3):          # same subsampling as the colour pass above
                row, hit = y * w * chans, 0
                for x in range(0, w, 3):
                    i = row + x * chans
                    if (abs(buf[i] - bg[0]) + abs(buf[i + 1] - bg[1])
                            + abs(buf[i + 2] - bg[2])) > INK_DELTA:
                        hit += 1
                        if hit >= 3:
                            break
                if hit >= 3:
                    first = y if first is None else first
                    last = y
            span = 0.0 if first is None else (last - first + 3) / h
        flat = span is not None and span < MIN_INK_SPAN
        detail = '' if span is None else f', ink spans {span:.0%} of the height'
        verdict = 'FLAT — this is not a render' if flat else 'looks drawn'
        print(f'{a.png}  {w}x{h}  {len(counts)} colours, {dom:.1%} one colour'
              f'{detail} — {verdict}')
        if flat:
            print('  Mostly one colour AND all the content in one band: that is the shape of an '
                  'error page, not a screen. A screenshot of one is a valid PNG — open the URL '
                  'in a real browser before blaming the config.')
            return 1
        return 0
    px = lambda x, y: tuple(buf[(y * w + x) * chans:(y * w + x) * chans + 3])
    span = lambda s, hi: (lambda p: (max(0, int(p[0])), min(hi, int(p[1]))))(s.split(':'))

    bx, by = (int(v) for v in a.bg.split(',')) if a.bg else (w // 2, min(h - 1, 8))
    bg = px(bx, by)
    div = None
    if a.scale:
        iw, pts = (float(v) for v in a.scale.split(':'))
        div = iw / pts
    fmt = (lambda n: f'{n} ({n / div:.0f}pt)') if div else (lambda n: str(n))

    print(f'{a.png}  {w}x{h}   background {bg} sampled at ({bx},{by})'
          + (f'   scale {div:.3f} px/pt' if div else ''))

    hit = lambda x, y: sum(abs(p - q) for p, q in zip(px(x, y), bg)) > a.threshold
    if a.column:
        x0, x1 = span(a.column, w)
        y0, y1 = span(a.rows, h) if a.rows else (0, h)
        rs = runs_of([y for y in range(y0, y1) if any(hit(x, y) for x in range(x0, x1))])
        print(f'  painted vertical runs in x {x0}:{x1}  (start, end, height)')
        for r in rs:
            print(f'    {r[0]:5d} {r[1]:5d}   height {fmt(r[2])}')
        gaps = [rs[i + 1][0] - rs[i][1] - 1 for i in range(len(rs) - 1)]
        print(f'  gaps: {gaps if gaps else "none — the column is continuous"}')
        if gaps and max(gaps) <= 2:
            print('  (all gaps <= 2px: likely antialiasing, not a break)')
    else:
        y = a.row
        x0, x1 = span(a.cols, w) if a.cols else (0, w)
        rs = runs_of([x for x in range(x0, x1) if hit(x, y)])
        print(f'  painted horizontal runs on y={y}  (start, end, width)')
        for r in rs:
            print(f'    {r[0]:5d} {r[1]:5d}   width  {fmt(r[2])}')
        if not rs:
            print('    none — nothing painted on this scanline')


if __name__ == '__main__':
    sys.exit(main() or 0)

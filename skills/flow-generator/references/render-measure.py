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
import argparse, struct, sys, zlib


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
    if (a.column is None) == (a.row is None):
        ap.error('pass exactly one of --column or --row')

    w, h, chans, buf = read_png(a.png)
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
    main()

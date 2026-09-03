#!/usr/bin/env python3
"""Calibration for `render-measure.py --sanity`, the guard `shoot.sh` gates renders on.

Repo-only. Runs the shipped script as a subprocess -- never imports it, so nothing writes a
`__pycache__` into `references/`.

The images are SYNTHESISED here rather than checked in, for the same reason
`tests/render-baseline/` is gitignored: PNG bytes from a real browser are machine-specific, and
a binary fixture nobody can regenerate rots. Each one reproduces the SHAPE of a class measured
on real samples on 2026-08-28:

    error page   flat, ink in one band, and only TEXT-width runs  -> must FAIL (exit 1)
    blank page   one colour, no ink at all                        -> must FAIL
    sparse app   mostly one colour, ink spread down the frame     -> must PASS (exit 0)
    banded app   ink in ONE band but not flat enough              -> must PASS
    dense app    neither flat nor banded                          -> must PASS
    card screen  flat AND banded, but a card edge runs the width  -> must PASS

The last one is the 2026-08-28 report: a correct render of a single reviews carousel was
renamed `NOT-A-RENDER-*`. It is the case the previous two-axis guard could not have got right,
because on those two axes the real render sits BETWEEN two error pages (dom 0.969 / span 0.287,
against conn-refused 0.976 / 0.263 and dns-error 0.972 / 0.333). The third axis -- the longest
CONTIGUOUS run of ink in a row -- separates them 0.139 vs 0.646, because glyphs have gaps
between them and a card edge does not.

Note the error-page fixture below draws TEXT-WIDTH runs. It used to draw solid 250px bars,
which no real error page produces (measured: 0.090-0.139 of the width), and the third axis
correctly began accepting it -- an unfaithful fixture caught by the check it was meant to test.

Usage: python3 tests/test-render-sanity.py       # 0 all pass, 1 a case regressed
"""
import os, struct, subprocess, sys, tempfile, zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RM = os.path.join(ROOT, 'skills', 'flow-generator', 'references', 'render-measure.py')
W, H = 430, 900
BG, INK = (255, 255, 255), (32, 33, 36)

fails = []


def png(path, rows):
    """`rows(y)` returns a list of x-ranges to ink on that row."""
    raw = bytearray()
    for y in range(H):
        raw.append(0)
        line = bytearray()
        spans = rows(y)
        for x in range(W):
            c = INK if any(a <= x < b for a, b in spans) else BG
            line += bytes(c)
        raw += line
    comp = zlib.compress(bytes(raw), 6)

    def chunk(typ, body):
        return (struct.pack('>I', len(body)) + typ + body
                + struct.pack('>I', zlib.crc32(typ + body) & 0xffffffff))

    with open(path, 'wb') as fh:
        fh.write(b'\x89PNG\r\n\x1a\n')
        fh.write(chunk(b'IHDR', struct.pack('>IIBBBBB', W, H, 8, 2, 0, 0, 0)))
        fh.write(chunk(b'IDAT', comp))
        fh.write(chunk(b'IEND', b''))


def case(name, rows, want_fail):
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, 'x.png')
        png(p, rows)
        rc = subprocess.run([sys.executable, RM, '--sanity', p],
                            capture_output=True, text=True).returncode
    got_fail = rc == 1
    ok = got_fail == want_fail
    verb = 'rejected' if want_fail else 'accepted'
    print(f"  {'ok  ' if ok else 'FAIL'}  {name} -> must be {verb}")
    if not ok:
        fails.append(f'{name}: wanted {"exit 1" if want_fail else "exit 0"}, got exit {rc}')


# An error page: one clump in the middle third, drawn as TEXT -- short glyph runs with gaps,
# plus a small solid icon. Longest contiguous run ~45px (0.105 of the width), matching the
# 0.090-0.139 measured on four real Chrome error pages.
def error_page(y):
    if 300 <= y <= 344:                       # the icon: the widest solid thing on the page
        return [(90, 135)]
    if 360 <= y <= 420 and (y // 6) % 2 == 0:  # lines of text
        return [(x, x + 9) for x in range(90, 330, 14)]
    return []
case('error page — flat, one band, only text-width runs', error_page, True)

case('blank page — one colour, no ink at all', lambda y: [], True)

# a sparse signup screen: heading, a field outline, a bottom row -- flat but SPREAD
def sparse(y):
    if 110 <= y <= 140: return [(40, 300)]          # heading
    if 170 <= y <= 172 or 218 <= y <= 220: return [(30, 400)]   # field border
    if 170 <= y <= 220: return [(30, 32), (398, 400)]
    if 780 <= y <= 792: return [(120, 310)]         # legal row near the bottom
    return []
case('sparse app screen — flat but ink spread down the frame', sparse, False)

# a one-section carousel: ink confined to a band, but NOT flat enough to trip the gate
def banded(y):
    return [(20, 410)] if 180 <= y <= 360 else []
case('banded app screen — one section, not flat enough', banded, False)

# a dense paywall: neither flat nor banded
case('dense app screen — neither flat nor banded',
     lambda y: [(10, 420)] if 40 <= y <= 860 else [], False)

# THE REPORTED BUG (2026-08-28): one card on a white frame. Flat, and its ink is confined to a
# band -- so the old two-axis gate rejected it -- but the card's top and bottom edges run
# unbroken across most of the width, which no page made of text can do.
def one_card(y):
    if y in (200, 380):        return [(30, 400)]      # card top / bottom edge
    if 200 < y < 380:          return [(30, 32), (398, 400)]   # card sides
    if 120 <= y <= 145:        return [(x, x + 9) for x in range(40, 260, 14)]  # heading text
    return []
case('one card on a white frame — flat AND banded, but drawn edges', one_card, False)

# KNOWN LIMITATION, asserted so it stays visible rather than forgotten: a screen made only of
# text is not distinguishable from an error page by any of the three axes -- measured, a real
# heading-only render scores a 0.042 longest run and a real terms screen 0.062, BELOW the
# 0.090-0.139 of the error pages, because Chrome's error page has a solid icon and button. No
# threshold separates them; they are the same image. `shoot.sh` covers this case a different
# way, by probing the render host before it launches Chrome at all. If someone later makes this
# case pass, that is an improvement -- update this assertion and the note in render-measure.py.
case('KNOWN LIMITATION: a text-only app screen is still rejected',
     lambda y: [(x, x + 9) for x in range(40, 300, 14)] if 120 <= y <= 200 and (y // 5) % 2 == 0
     else [], True)

print()
if fails:
    print(f'{len(fails)} FAILED')
    for f in fails:
        print('  -', f)
    sys.exit(1)
print('all checks passed')

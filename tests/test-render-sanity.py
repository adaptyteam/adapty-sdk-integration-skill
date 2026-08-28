#!/usr/bin/env python3
"""Calibration for `render-measure.py --sanity`, the guard `shoot.sh` gates renders on.

Repo-only. Runs the shipped script as a subprocess -- never imports it, so nothing writes a
`__pycache__` into `references/`.

The images are SYNTHESISED here rather than checked in, for the same reason
`tests/render-baseline/` is gitignored: PNG bytes from a real browser are machine-specific, and
a binary fixture nobody can regenerate rots. Each one reproduces the SHAPE of a class measured
on real samples on 2026-08-28:

    error page   mostly one colour, all ink in one central band   -> must FAIL (exit 1)
    blank page   one colour, no ink at all                        -> must FAIL
    sparse app   mostly one colour, ink spread down the frame     -> must PASS (exit 0)
    banded app   ink in ONE band but not flat enough              -> must PASS
    dense app    neither flat nor banded                          -> must PASS

The last two are the false positives the previous single-axis guard produced: four agents in
one GREEN round had good renders renamed `NOT-A-RENDER-*`, because a sparse light signup screen
measured 99.1% one colour where the DNS-error page it exists to catch measured 97.6%.

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


# an error page: one clump of text lines in the middle third
case('error page — flat, ink in one central band',
     lambda y: [(90, 340)] if 300 <= y <= 420 and (y // 6) % 2 == 0 else [], True)

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

print()
if fails:
    print(f'{len(fails)} FAILED')
    for f in fails:
        print('  -', f)
    sys.exit(1)
print('all checks passed')

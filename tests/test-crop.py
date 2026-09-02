#!/usr/bin/env python3
"""Both directions for references/crop.py -- what it refuses and what it gets right.

Fixtures are SYNTHESIZED rather than checked in, for the same reason tests/render-baseline/ is
gitignored: a browser's or a screenshot's bytes are machine-specific and a fixture nobody can
regenerate rots. The numbers the cases assert against, though, come from real references --
see the comments naming them.

    python3 tests/test-crop.py
"""
import os
import sys
import tempfile

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                '..', 'skills', 'flow-generator', 'references'))
import crop  # noqa: E402

FAILS = []


def check(name, cond, detail=''):
    if cond:
        print(f'  ok   {name}')
    else:
        print(f'  FAIL {name} {detail}')
        FAILS.append(name)


def png(path, rows):
    crop.write_rgba(path, rows)


def solid(w, h, rgb):
    return [[[rgb[0], rgb[1], rgb[2], 255] for _ in range(w)] for _ in range(h)]


def noisy(w, h, rgb, amp):
    out = solid(w, h, rgb)
    for y in range(h):
        for x in range(w):
            d = ((x * 37 + y * 101) % (2 * amp + 1)) - amp
            for i in range(3):
                out[y][x][i] = max(0, min(255, rgb[i] + d))
    return out


def rect(px, x0, y0, x1, y1, rgb):
    for y in range(y0, y1):
        for x in range(x0, x1):
            px[y][x] = [rgb[0], rgb[1], rgb[2], 255]


def opaque_at(px, x, y):
    return px[y][x][3] > 200


def transparent_at(px, x, y):
    return px[y][x][3] < 20


tmp = tempfile.mkdtemp(prefix='crop-test-')
P = lambda n: os.path.join(tmp, n)  # noqa: E731

print('REFUSES')

# The crumpled-paper backdrop on a real Black Friday reference measured max deviation 144.
# Nothing can be keyed off it: no single colour to remove, and no alpha to recover.
src = noisy(60, 60, (24, 25, 27), 40)
rect(src, 20, 20, 40, 40, (255, 140, 0))
png(P('textured.png'), src)
code, out = crop.run(P('textured.png'), P('o1.png'), (0, 0, 60, 60), do_key=True)
check('textured backdrop refuses', code == 1, f'code={code}')
check('  ...and names the textured cause', any('textured or a gradient' in ln for ln in out))

# A box cropped tight enough to clip the graphic samples INK on its border. Measured 173 and 241
# on two real crops from the [LK] Paywalls sheet. Same number as a real texture, different fix,
# so the refusal has to name both.
src = solid(40, 40, (244, 226, 196))
rect(src, 5, 0, 40, 40, (255, 140, 0))          # ink on three of the four edges
png(P('tight.png'), src)
code, out = crop.run(P('tight.png'), P('o2.png'), (0, 0, 40, 40), do_key=True)
check('tight box refuses', code == 1, f'code={code}')
check('  ...and offers "widen it" first', any('Widen it' in ln for ln in out))

png(P('ok.png'), solid(40, 40, (250, 250, 250)))
code, _ = crop.run(P('ok.png'), P('o3.png'), (0, 0, 80, 80))
check('box outside the image is usage error', code == 2, f'code={code}')
code, _ = crop.run(P('nope.png'), P('o4.png'), (0, 0, 4, 4))
check('unreadable source is usage error', code == 2, f'code={code}')

# A uniform crop has border deviation 0, so it passes the flatness guard and then keys away to
# nothing. Found by a bad fixture in this very suite: the refusal below is what it bought.
png(P('empty.png'), solid(40, 40, (244, 226, 196)))
code, out = crop.run(P('empty.png'), P('o4b.png'), (0, 0, 40, 40), do_key=True)
check('all-backdrop crop refuses', code == 1, f'code={code}')
check('  ...and points at the coordinates', any('Check the coordinates' in ln for ln in out))

print('ACCEPTS')

# The positive case, from screen 2 of the [LK] Paywalls sheet: multicolour icons on a flat cream
# card, keyed clean and composited over black, white and purple with no halo.
src = solid(60, 60, (244, 226, 196))
rect(src, 20, 20, 40, 40, (255, 140, 0))
png(P('flat.png'), src)
code, out = crop.run(P('flat.png'), P('o5.png'), (0, 0, 60, 60), do_key=True)
check('flat backdrop keys', code == 0, f'code={code}')
res = crop.read_png(P('o5.png'))
kept = [[list(p) for p in r] for r in
        [[[res[3][y][x * res[2] + i] for i in range(4)] for x in range(res[0])]
         for y in range(res[1])]]
check('  backdrop is transparent', transparent_at(kept, 2, 2))
check('  graphic is opaque', opaque_at(kept, 30, 30))
check('  graphic keeps its colour', kept[30][30][:3] == [255, 140, 0], kept[30][30][:3])
check('  contact sheet is written', os.path.exists(P('o5.contact.png')))
check('  ...and the run says to look at it', any('LOOK AT' in ln for ln in out))

# A plain crop asks nothing of the backdrop, so a texture is fine without --key.
code, _ = crop.run(P('textured.png'), P('o6.png'), (0, 0, 60, 60))
check('plain crop over a texture is fine', code == 0, f'code={code}')

# Interior survives: the white stripes inside a US flag came back intact on the real sheet,
# because the flood is CONNECTIVITY-based and cannot reach an enclosed region.
src = solid(60, 60, (250, 250, 250))
rect(src, 15, 15, 45, 45, (200, 30, 40))
rect(src, 25, 25, 35, 35, (250, 250, 250))      # key colour, fully enclosed
png(P('ring.png'), src)
code, _ = crop.run(P('ring.png'), P('o7.png'), (0, 0, 60, 60), do_key=True)
r = crop.read_png(P('o7.png'))
ring = [[[r[3][y][x * r[2] + i] for i in range(4)] for x in range(r[0])] for y in range(r[1])]
check('enclosed key-coloured interior survives', code == 0 and opaque_at(ring, 30, 30))

# KNOWN LIMITATION, measured on the real sheet: Finland, Canada and France lost their white
# fields because the white touches the silhouette's edge, so the flood walks through it. Nothing
# in this tool detects that -- the contact sheet is the check. Pinned so that "fixing" the flood
# to be smarter turns this red and sends the next person to this comment.
src = solid(60, 60, (250, 250, 250))
rect(src, 15, 15, 45, 45, (200, 30, 40))
rect(src, 25, 0, 35, 45, (250, 250, 250))       # key-coloured channel out to the border
png(P('bleed.png'), src)
code, _ = crop.run(P('bleed.png'), P('o8.png'), (0, 0, 60, 60), do_key=True)
r = crop.read_png(P('o8.png'))
bl = [[[r[3][y][x * r[2] + i] for i in range(4)] for x in range(r[0])] for y in range(r[1])]
check('KNOWN LIMITATION: edge-touching key colour is eaten', code == 0 and transparent_at(bl, 30, 30))

# Unpremultiply: a half-blended edge pixel must come back as INK, not as the blend. Without this
# every cutout carries a rim of its old backdrop -- invisible over a similar colour, obvious
# over its opposite, which is exactly what the contact sheet's black panel exposes.
src = solid(60, 60, (250, 250, 250))
rect(src, 20, 20, 40, 40, (0, 0, 0))
for y in range(20, 40):
    src[y][19] = [125, 125, 125, 255]           # 50% blend of ink and backdrop
png(P('aa.png'), src)
crop.run(P('aa.png'), P('o9.png'), (0, 0, 60, 60), do_key=True)
r = crop.read_png(P('o9.png'))
aa = [[[r[3][y][x * r[2] + i] for i in range(4)] for x in range(r[0])] for y in range(r[1])]
edge = aa[30][19]
check('AA edge gets partial alpha', 20 < edge[3] < 250, f'alpha={edge[3]}')
# Recovery is APPROXIMATE and cannot be exact -- a flat composite does not record what the ink
# under a blend was. What must hold is the direction: the recovered colour moves toward the ink
# and away from the backdrop, which is the difference between a visible rim and none.
check('  ...and is unpremultiplied toward ink', max(edge[:3]) < 125, f'rgb={edge[:3]}')
check('  ...and composites darker than the raw blend',
      int(edge[0] * edge[3] / 255.0) < 125, f'over black={int(edge[0] * edge[3] / 255.0)}')

print('RESOLUTION')
code, out = crop.run(P('flat.png'), P('o10.png'), (0, 0, 60, 60), fit=(60, 60))
check('1x crop warns', code == 0 and any('soft on a 2x/3x' in ln for ln in out))
code, out = crop.run(P('flat.png'), P('o11.png'), (0, 0, 60, 60), fit=(20, 20))
check('3x crop is quiet', code == 0 and not any('soft on a 2x/3x' in ln for ln in out))

print()
if FAILS:
    print(f'{len(FAILS)} FAILED: {", ".join(FAILS)}')
    sys.exit(1)
print('all crop checks passed')

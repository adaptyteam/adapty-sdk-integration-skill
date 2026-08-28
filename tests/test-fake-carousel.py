#!/usr/bin/env python3
"""Calibration for the fake-carousel checks in `references/verify-config.py`.

Repo-only, like everything under `tests/`. It runs the shipped script as a subprocess --
never imports it, so nothing writes a `__pycache__` into `references/`, which the
copy-install path would ship.

Why this file exists. A first anti-fake guard shipped in 2026-08 and a user reported the
skill still faking the element. Rebuilding `tests/fixtures/reviews-carousel.json` as the
fakes an agent would plausibly write measured **1 of 7 caught**: the check keyed on one
shape only -- three or more leaf `stack`s, both axes fixed and EQUAL, at most 12pt, rounded.
Every miss below is an ordinary authoring choice, not an exotic one, which is the whole
lesson: a guard calibrated against a single remembered shape tests the memory, not the trap.

Both directions are asserted, and they matter equally. A check that misses its defect buys
nothing over shipping the fake; a check that fires on a real export gets ignored within a
day, and then it misses its defect too.

    FIRES   -- an injected fake must be reported, matching a fragment
    SILENT  -- every real export, tracked and raw, must stay clean

Usage: python3 tests/test-fake-carousel.py     # 0 all pass, 1 a case regressed
"""
import copy, glob, json, os, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERIFY = os.path.join(ROOT, 'skills', 'flow-generator', 'references', 'verify-config.py')
AUDIT = os.path.join(ROOT, 'skills', 'flow-audit', 'references', 'audit-flow.py')
CORPUS = os.path.join(ROOT, 'tests', 'fixtures')
RAW = os.path.join(ROOT, 'tests', 'fixtures-raw')
CAROUSEL = os.path.join(CORPUS, 'reviews-carousel.json')

FAKE = 'FAKE CAROUSEL'
OVERFLOW = 'swipeable row hand-built as a static one'

fails = []


def run(doc):
    """(error lines, warning lines) the shipped script prints for `doc`."""
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, 'c.json')
        json.dump(doc, open(p, 'w'))
        r = subprocess.run([sys.executable, VERIFY, p], capture_output=True, text=True)
    if 'Traceback' in r.stderr:
        raise AssertionError(f'verify-config.py crashed:\n{r.stderr}')
    errs = [l.split('ERROR:', 1)[1].strip() for l in r.stdout.splitlines() if 'ERROR:' in l]
    warns = [l.split('warning:', 1)[1].strip() for l in r.stdout.splitlines() if 'warning:' in l]
    return errs, warns


def fires(name, doc, fragment, level='error'):
    errs, warns = run(doc)
    lines = errs if level == 'error' else warns
    if not any(fragment in l for l in lines):
        fails.append(f'{name}: expected a {level} containing {fragment!r}, '
                     f'got errors={errs!r} warnings={warns!r}')
        print(f'  FAIL  {name}')
    else:
        print(f'  ok    {name}')


def silent(name, doc):
    errs, warns = run(doc)
    hits = [l for l in errs + warns if FAKE in l or OVERFLOW in l]
    if hits:
        fails.append(f'{name}: expected no fake-carousel finding, got {hits!r}')
        print(f'  FAIL  {name}')
    else:
        print(f'  ok    {name}')


# ------------------------------------------------------------------ building the fakes
def dot(i, w=8, h=8, r=4):
    return {'id': f'el_dot{i}', 'type': 'stack', 'states': [], 'props': {
        'position': {'type': 'relative'},
        'width': {'type': 'fixed', 'value': w},
        'height': {'type': 'fixed', 'value': h},
        'borderRadius': {'tl': r, 'tr': r, 'bl': r, 'br': r},
        'fill': [{'type': 'color', 'color': {'type': 'color-style', 'colorId': 'muted'}}]}}


def icon_dot(i, name='Circle', size=8):
    return {'id': f'el_dot{i}', 'type': 'icon', 'states': [], 'props': {
        'position': {'type': 'relative'},
        'icon': {'type': 'phosphor', 'name': name, 'size': size, 'weight': 'fill',
                 'color': {'type': 'color-style', 'colorId': 'muted'}}}}


def text_dots(s='● ○ ○'):
    return {'id': 'el_dottext', 'type': 'text', 'states': [], 'props': {
        'position': {'type': 'relative'},
        'width': {'type': 'hug'}, 'height': {'type': 'hug'},
        'layout': 'auto-height',
        'content': {'_localizable': True, 'values': {'en': [
            {'type': 'paragraph', 'content': [{'type': 'text', 'text': s}]}]}}}}


def fake(dots=(), *, keep_slides=1, card_w=None, gap=12):
    """`reviews-carousel.json` with the carousel replaced by a static row + hand-built dots."""
    d = json.load(open(CAROUSEL))
    d = d.get('config', d)
    s = d['screens'][0]
    m, h = s['elements']['map'], s['elements']['hierarchy']
    car = next(c for c in h['children'] if m.get(c['id'], {}).get('type') == 'carousel')
    slides = car['children'][:keep_slides]
    del m[car['id']]

    row = {'id': 'el_fakerow', 'type': 'stack', 'states': [], 'props': {
        'position': {'type': 'relative'},
        'width': {'type': 'fill'}, 'height': {'type': 'fixed', 'value': 150},
        'layout': {'direction': 'horizontal', 'distribution': {'type': 'gap', 'gap': gap}}}}
    m['el_fakerow'] = row
    if card_w is not None:                      # equal fixed-width cards, the peek shape
        for c in slides:
            m[c['id']]['props']['width'] = {'type': 'fixed', 'value': card_w}

    kids = [{'id': 'el_fakerow', 'children': slides}]
    if dots:
        strip = {'id': 'el_dotrow', 'type': 'stack', 'states': [], 'props': {
            'position': {'type': 'relative'},
            'width': {'type': 'hug'}, 'height': {'type': 'hug'},
            'layout': {'direction': 'horizontal', 'distribution': {'type': 'gap', 'gap': 6}}}}
        m['el_dotrow'] = strip
        for dd in dots:
            m[dd['id']] = dd
        kids.append({'id': 'el_dotrow', 'children': [{'id': dd['id']} for dd in dots]})
    h['children'] = [c for c in h['children'] if c['id'] != car['id']] + kids
    return d


# ---------------------------------------------------------------- SILENT: the real corpus
print('SILENT on every real export (the false-positive half):')
for path in sorted(glob.glob(os.path.join(CORPUS, '*.json'))):
    silent(f'tracked {os.path.basename(path)}', json.load(open(path)))
for path in sorted(glob.glob(os.path.join(RAW, '*.json'))):
    silent(f'raw {os.path.basename(path)}', json.load(open(path)))

# The element the whole check is about must not trip it. `reviews-carousel.json` is a REAL
# carousel drawing its own dots and containing no dot `stack` at all -- if this ever fires,
# the guard has started punishing the shape it exists to recommend.
silent('a real `carousel` (the recommended shape)', json.load(open(CAROUSEL)))

# ---------------------------------------------------- SILENT: the near misses that are legal
# Five `Star` icons in a row is a rating, not an indicator -- `ue-review` ships exactly this,
# so keying on small icons WITHOUT a name filter would fire on every review card in the corpus.
silent('a five-star rating row (small icons, not dot-shaped)',
       fake([icon_dot(i, name='Star', size=24) for i in range(5)]))
# A row of two ordinary cards that FITS the viewport is an ordinary layout.
silent('two 180pt cards side by side (fits the viewport)', fake(keep_slides=2, card_w=180))

# ------------------------------------------------------- FIRES: one injected fake each
print('\nFIRES on an injected fake (the false-negative half):')

fires('three identical 8x8 rounded dot stacks (the only shape the old check caught)',
      fake([dot(i) for i in range(3)]), FAKE)
fires('an ACTIVE dot drawn as a wider pill (20x8) beside two round ones',
      fake([dot(0, w=20, h=8), dot(1), dot(2)]), FAKE)
fires('dots drawn as small phosphor `Circle` icons',
      fake([icon_dot(i) for i in range(3)]), FAKE)
fires('dots drawn as one text node of bullet glyphs',
      fake([text_dots()]), FAKE)
fires('14pt dots, one size over the old <=12 cap',
      fake([dot(i, w=14, h=14, r=7) for i in range(3)]), FAKE)
fires('a TWO-slide carousel, so only two dots (the old check needed three)',
      fake([dot(i) for i in range(2)]), FAKE)
fires('no dots at all: three 300pt cards in a row wider than the screen',
      fake(keep_slides=3, card_w=300), OVERFLOW, level='warning')

# `DotOutline` is the inactive dot in phosphor's own set, so the name filter must carry it.
fires('inactive dots drawn as `DotOutline` icons',
      fake([icon_dot(i, name='DotOutline') for i in range(3)]), FAKE)

# ------------------------------------------------------------------ the crash this cost once
# `props.layout` is a bare STRING ('auto-height') on a text element. Assuming a dict crashed
# the checker on every real config -- and a crash reads as a broken document, not a broken
# check, so it is asserted here rather than left to the corpus pass.
_d = fake([dot(i) for i in range(3)])
_d['screens'][0]['elements']['map']['el_dottext'] = text_dots()
_d['screens'][0]['elements']['hierarchy']['children'].append({'id': 'el_dottext'})
fires('a text element (props.layout is a string) does not crash the walk', _d, FAKE)

# ------------------------------------------------- the same trap, through `flow-audit`
# `flow-audit` is a separate skill with its own copy of the rule (each skill directory has
# to be self-contained). It was blind to this entirely until 2026-08-28, so the read-only
# auditor certified fake sliders as production-ready. Asserted here rather than in
# `test-audit-flow.py` so one file owns the trap in both directions and both skills.
print('\nthe same fakes, through `flow-audit`:')


def audits(name, doc, expect=True):
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, 'c.json')
        json.dump(doc, open(p, 'w'))
        r = subprocess.run([sys.executable, AUDIT, p], capture_output=True, text=True)
    if 'Traceback' in r.stderr:
        fails.append(f'{name}: audit-flow.py crashed:\n{r.stderr}')
        print(f'  FAIL  {name}')
        return
    hit = 'frozen slide' in r.stdout or 'swipeable row' in r.stdout
    if hit is not expect:
        fails.append(f'{name}: expected fired={expect}, got {hit}')
        print(f'  FAIL  {name}')
    else:
        print(f'  ok    {name}')


audits('three round dot stacks', fake([dot(i) for i in range(3)]))
audits('an active pill beside two dots', fake([dot(0, w=20, h=8), dot(1), dot(2)]))
audits('phosphor `Circle` icon dots', fake([icon_dot(i) for i in range(3)]))
audits('a text node of bullet glyphs', fake([text_dots()]))
audits('three 300pt cards wider than the screen', fake(keep_slides=3, card_w=300))
audits('a real carousel is NOT flagged', json.load(open(CAROUSEL)), expect=False)
for _p in sorted(glob.glob(os.path.join(CORPUS, '*.json'))):
    audits(f'silent on {os.path.basename(_p)}', json.load(open(_p)), expect=False)

print()
if fails:
    print(f'{len(fails)} FAILED')
    for f in fails:
        print('  -', f)
    sys.exit(1)
print('all checks passed')

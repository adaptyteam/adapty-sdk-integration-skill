#!/usr/bin/env python3
"""Calibration for the text-legibility check in `references/verify-config.py`.

Repo-only. Runs the shipped script as a subprocess -- never imports it, so nothing writes a
`__pycache__` into `references/`.

What it checks and what it deliberately does NOT. This is not an accessibility audit: WCAG AA
wants 4.5 (3.0 large) and **13% of the text in real builder exports is already below 4.5**, so
enforcing AA would mean second-guessing a designer's palette on every real flow. The check asks
the narrower construction question -- *can this text be told apart from its own background at
all* -- and the corpus shows the two questions are cleanly separable: the lowest deliberate
value measured is **1.89** (amber stars on a light card) and the next one down is **1.08**
(near-white on white). The threshold sits in that empty gap at 1.5.

Both appearance variants are checked because `config preview` draws LIGHT ONLY. A half-finished
dark palette is invisible to every other gate this repo has.

Why authored configs need it and real exports do not: measured across the corpus, **all 11
genuine exports bind the screen fill to a theme token or an image**, so background and text move
together between variants. Only a hand-authored screen hardcodes `fill: #FFFFFF` under a
dark-capable theme -- and then the text token goes near-white in dark while the background does
not. `flowkit` authors exactly that kind of screen.

    FIRES   -- same-colour text on fill, and the dark-only variant of it
    SILENT  -- all 11 genuine exports, deliberate low-contrast accents, unresolvable backgrounds

KNOWN FINDING, asserted rather than suppressed: `timeline-anchored.json` fires (6 elements,
dark). It is the corpus's one hybrid -- a real export screen with a *borrowed* theme, already
excluded from census counts in CLAUDE.md -- and it hardcodes its screen fill, which none of the
11 genuine exports do. The fixture is left exactly as it is: its provenance is mixed, and
editing evidence to quiet a checker is how a corpus stops being evidence. Pinning the finding
here turns it from ambient noise into an expectation.

Usage: python3 tests/test-legibility.py     # 0 all pass, 1 a case regressed
"""
import copy, glob, json, os, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERIFY = os.path.join(ROOT, 'skills', 'flow-generator', 'references', 'verify-config.py')
CORPUS = os.path.join(ROOT, 'tests', 'fixtures')
RAW = os.path.join(ROOT, 'tests', 'fixtures-raw')

MARKER = 'effectively invisible'
HYBRID = 'timeline-anchored.json'

fails = []


def run(doc):
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, 'c.json')
        json.dump(doc, open(path, 'w'))
        result = subprocess.run([sys.executable, VERIFY, path], capture_output=True, text=True)
    if 'Traceback' in result.stderr:
        raise AssertionError(f'verify-config.py crashed:\n{result.stderr}')
    return [line.strip() for line in result.stdout.splitlines() if MARKER in line]


def fires(name, doc, fragment):
    hits = run(doc)
    if not any(fragment in line for line in hits):
        fails.append(f'{name}: expected a finding containing {fragment!r}, got {hits!r}')
        print(f'  FAIL  {name}')
    else:
        print(f'  ok    {name}')


def silent(name, doc):
    hits = run(doc)
    if hits:
        fails.append(f'{name}: expected no legibility finding, got {hits!r}')
        print(f'  FAIL  {name}')
    else:
        print(f'  ok    {name}')


# --------------------------------------------------------------------- a one-card screen
def flow(*, screen_fill, card_fill, text_color, tokens):
    """A screen -> card -> text chain. Any argument may be a token ref or a literal hex."""
    text = {'id': 'el_txt', 'type': 'text', 'states': [], 'props': {
        'width': {'type': 'fill'}, 'height': {'type': 'hug'}, 'align': 'left',
        'layout': 'auto-height', 'decoration': 'none', 'position': {'type': 'relative'},
        'font': {'preset': 'body'}, 'color': text_color,
        'content': {'_localizable': True, 'values': {'en': [
            {'type': 'paragraph', 'content': [{'type': 'text', 'text': 'Unlock everything'}]}]}}}}
    card = {'id': 'el_card', 'type': 'stack', 'states': [], 'props': {
        'width': {'type': 'fill'}, 'height': {'type': 'hug'},
        'position': {'type': 'relative'},
        'layout': {'direction': 'vertical', 'distribution': {'type': 'gap', 'gap': 8}}}}
    if card_fill is not None:
        card['props']['fill'] = card_fill
    return {
        'schemaVersion': 10, 'defaultLocale': 'en',
        'locales': [{'id': 'en', 'code': 'en', 'name': 'English'}],
        'theme': {'colors': tokens, 'typography': []},
        '_meta': {'screens': {}, 'icons': [], 'fonts': []},
        'screens': [{'id': 'scr_1', 'caption': 'Paywall', 'selectableGroups': [],
                     'props': {'safeArea': True, 'scrollable': False,
                               'padding': {'top': 8, 'left': 16, 'right': 16, 'bottom': 8},
                               'fill': screen_fill,
                               'layout': {'alignH': 'start', 'alignV': 'start',
                                          'direction': 'vertical',
                                          'distribution': {'type': 'gap', 'gap': 8}}},
                     'elements': {
                         'map': {'el_card': card, 'el_txt': text},
                         'hierarchy': {'id': 'root', 'children': [
                             {'id': 'el_card', 'children': [{'id': 'el_txt', 'children': []}]}]}}}]}


def hexc(h, **kw):
    return dict({'type': 'hex', 'hex': h}, **kw)


def tok(i, **kw):
    return dict({'type': 'color-style', 'colorId': i}, **kw)


def colorfill(c):
    return [{'type': 'color', 'color': c}]


def gradfill(*colors, angle=90):
    """A gradient fill, v10 one-layer array form, stops spread evenly."""
    n = max(1, len(colors) - 1)
    return [{'type': 'gradient', 'angle': angle,
             'stops': [{'color': c, 'position': round(100 * i / n)}
                       for i, c in enumerate(colors)]}]


PLAIN = [{'id': 'ink', 'light': {'hex': '#111114'}},
         {'id': 'paper', 'light': {'hex': '#FFFFFF'}}]
# A full light/dark palette, as 5 of the 7 tracked fixtures carry.
DUAL = [{'id': 'ink', 'light': {'hex': '#111114'}, 'dark': {'hex': '#F5F5F7'}},
        {'id': 'paper', 'light': {'hex': '#FFFFFF'}, 'dark': {'hex': '#0E0E12'}}]

# ------------------------------------------------------------------------------- FIRES
print('FIRES on text that cannot be told from its background:')

fires('white text on a white card — the recolour-the-fill-not-the-text defect',
      flow(screen_fill=colorfill(hexc('#FFFFFF')), card_fill=colorfill(hexc('#FFFFFF')),
           text_color=hexc('#FFFFFF'), tokens=PLAIN),
      'light mode')

fires('text inherits the SCREEN fill when no ancestor sets one',
      flow(screen_fill=colorfill(hexc('#101014')), card_fill=None,
           text_color=hexc('#131318'), tokens=PLAIN),
      'light mode')

# The whole reason both variants are walked.
fires('dark-only: themed text over a HARDCODED background — invisible to preview',
      flow(screen_fill=colorfill(hexc('#FFFFFF')), card_fill=None,
           text_color=tok('ink'), tokens=DUAL),
      'dark mode')

fires('a token that carries its OWN opacity fades the text out',
      flow(screen_fill=colorfill(hexc('#FFFFFF')), card_fill=None,
           text_color=tok('ink', opacity=3), tokens=PLAIN),
      'light mode')

fires('an 8-digit hex alpha is honoured too',
      flow(screen_fill=colorfill(hexc('#FFFFFF')), card_fill=None,
           text_color=hexc('#11111408'), tokens=PLAIN),
      'light mode')

# v9 spells a fill as a bare object; the check must read both forms.
fires('the v9 object fill form, not just the v10 array',
      flow(screen_fill={'type': 'color', 'color': hexc('#FFFFFF')}, card_fill=None,
           text_color=hexc('#FEFEFE'), tokens=PLAIN),
      'light mode')

# ------------------------------------------------------------------------------- SILENT
print('\nSILENT where a finding would be noise:')

silent('a deliberate amber accent on a light card (1.89) is a design choice, not a defect',
       flow(screen_fill=colorfill(hexc('#F4F6FA')), card_fill=None,
            text_color=hexc('#F5A524'), tokens=PLAIN))

silent('muted grey on near-white (3.01), which real builder output ships',
       flow(screen_fill=colorfill(hexc('#E7E7EB')), card_fill=None,
            text_color=hexc('#84848B'), tokens=PLAIN))

silent('ordinary body text',
       flow(screen_fill=colorfill(hexc('#FFFFFF')), card_fill=None,
            text_color=tok('ink'), tokens=PLAIN))

# Unresolvable backgrounds must SKIP. A whole-document checker that guessed what shows through
# would be inventing findings about the designer's own scrim.
silent('an IMAGE screen fill is unresolvable — skip, never guess',
       flow(screen_fill={'type': 'image', 'color': hexc('#FFFFFF'),
                         'image': {'id': '1', 'url': 'https://example.invalid/a.png'}},
            card_fill=None, text_color=hexc('#FFFFFF'), tokens=PLAIN))

silent('a TRANSLUCENT scrim does not establish a background',
       flow(screen_fill={'type': 'image', 'color': hexc('#FFFFFF'),
                         'image': {'id': '1', 'url': 'https://example.invalid/a.png'}},
            card_fill=colorfill(hexc('#FFFFFF', opacity=20)),
            text_color=hexc('#FFFFFF'), tokens=PLAIN))

# The exact vpn-timer-draft shape: the 20% comes from the TOKEN, not the reference. Reading only
# the token's hex turns a scrim into an opaque white card and invents a 1.0 pair.
silent('a token declared at opacity 20 is a scrim, not an opaque card',
       flow(screen_fill={'type': 'image', 'color': hexc('#FFFFFF'),
                         'image': {'id': '1', 'url': 'https://example.invalid/a.png'}},
            card_fill=colorfill(tok('scrim')), text_color=tok('paper'),
            tokens=PLAIN + [{'id': 'scrim', 'light': {'hex': '#FFFFFF', 'opacity': 20}}]))

silent('a multi-layer fill is unresolvable — the tint may not reach the device at all',
       flow(screen_fill=[{'type': 'color', 'color': hexc('#FFFFFF')},
                         {'type': 'color', 'color': hexc('#FFFFFF', opacity=50)}],
            card_fill=None, text_color=hexc('#FFFFFF'), tokens=PLAIN))

silent('a colorId that resolves to nothing is skipped, not scored',
       flow(screen_fill=colorfill(hexc('#FFFFFF')), card_fill=None,
            text_color=tok('does-not-exist'), tokens=PLAIN))

# ------------------------------------------------------------- SILENT on real builder output
# --------------------------------------------------------------- gradient backgrounds
# The regression this section exists for: a gradient used to resolve to NOTHING, so the walk
# fell through to the screen fill and reported near-black-on-black for black text on a bright
# foil button. Six independent agent runs hit it, all diagnosed it as a false positive, and two
# changed their design to route around a checker that was wrong.
print('\nGradient backgrounds:')

silent('black text on a bright foil gradient — the false positive this fixed',
       flow(screen_fill=colorfill(hexc('#08080A')),
            card_fill=gradfill(hexc('#A8E6CF'), hexc('#C9A7F5'), hexc('#E3AACC')),
            text_color=hexc('#0B0B0B'), tokens=PLAIN))

silent('white text on a dark gradient',
       flow(screen_fill=colorfill(hexc('#FFFFFF')),
            card_fill=gradfill(hexc('#101828'), hexc('#1F2A44')),
            text_color=hexc('#F5F5F7'), tokens=PLAIN))

# The worst stop is the finding: text that survives one end and vanishes at the other is text
# that vanishes. A mean would have averaged this into looking fine.
fires('white text over a gradient that ends in white — worst stop wins',
      flow(screen_fill=colorfill(hexc('#08080A')),
           card_fill=gradfill(hexc('#101828'), hexc('#FFFFFF')),
           text_color=hexc('#FDFDFD'), tokens=PLAIN),
      'gradient stops')

fires('black text on a gradient that is dark throughout',
      flow(screen_fill=colorfill(hexc('#FFFFFF')),
           card_fill=gradfill(hexc('#0A0A0A'), hexc('#151515')),
           text_color=hexc('#050505'), tokens=PLAIN),
      'effectively invisible')

# Same rule solids follow, and not hypothetical: a real export gradient runs one stop at
# opacity 100 and the next at 26. What shows through a scrim is the designer's business.
silent('a translucent gradient stop makes the fill unresolvable, exactly like a translucent solid',
       flow(screen_fill=colorfill(hexc('#08080A')),
            card_fill=gradfill(hexc('#FFFFFF', opacity=100), hexc('#FFFFFF', opacity=26)),
            text_color=hexc('#FAFAFA'), tokens=PLAIN))

silent('a gradient through a theme token resolves like any other token',
       flow(screen_fill=colorfill(hexc('#08080A')),
            card_fill=gradfill(tok('paper'), tok('paper')),
            text_color=tok('ink'), tokens=PLAIN))

# A multi-LAYER fill stays unresolvable whether or not a gradient is in it -- 0 of the real
# exports contain one, and the one this project shipped reached a device with the tint missing.
silent('a multi-layer fill is still unresolvable',
       flow(screen_fill=colorfill(hexc('#08080A')),
            card_fill=[{'type': 'color', 'color': hexc('#FFFFFF')},
                       {'type': 'gradient', 'angle': 90,
                        'stops': [{'color': hexc('#FFFFFF'), 'position': 0},
                                  {'color': hexc('#EEEEEE'), 'position': 100}]}],
            text_color=hexc('#FCFCFC'), tokens=PLAIN))

# Text deliberately LEGIBLE against the screen fill: the only way this can fire is if an empty
# stop list were treated as establishing some background of its own. (First written with
# near-black text on a near-black screen, which fired for the honest reason -- the fall-through
# worked -- and tested nothing.)
silent('a gradient with no stops establishes nothing and the walk falls through',
       flow(screen_fill=colorfill(hexc('#08080A')),
            card_fill=[{'type': 'gradient', 'angle': 90, 'stops': []}],
            text_color=hexc('#F2F2F5'), tokens=PLAIN))

fires('a gradient SCREEN fill is resolved too, not just an element fill',
      flow(screen_fill=gradfill(hexc('#000000'), hexc('#061532')),
           card_fill=None, text_color=hexc('#04040A'), tokens=PLAIN),
      'effectively invisible')

_paths = sorted(glob.glob(os.path.join(CORPUS, '*.json'))) + \
         sorted(glob.glob(os.path.join(RAW, '*.json')))
_genuine = [p for p in _paths if os.path.basename(p) != HYBRID]
print(f'\nSILENT on genuine builder exports ({len(_genuine)} configs'
      f'{" — RAW ABSENT, tracked only" if not os.path.isdir(RAW) else ""}):')
for _p in _genuine:
    silent(os.path.basename(_p), json.load(open(_p)))

# ------------------------------------------------------------------------- the known finding
print('\nThe one hybrid fixture, asserted rather than suppressed:')
_hyb = os.path.join(CORPUS, HYBRID)
if not os.path.exists(_hyb):
    print(f'  SKIP  {HYBRID} not present')
else:
    _hits = run(json.load(open(_hyb)))
    if len(_hits) == 6 and all('dark mode' in h for h in _hits):
        print(f'  ok    {HYBRID}: 6 dark-mode findings (hardcoded screen fill + borrowed '
              f'dark-capable theme)')
    else:
        fails.append(f'{HYBRID}: expected exactly 6 dark-mode findings, got {len(_hits)}: {_hits!r}')
        print(f'  FAIL  {HYBRID}: expected 6 dark-mode findings, got {len(_hits)}')

    # Its light rendering is fine, which is why no render check ever caught this.
    _light = copy.deepcopy(json.load(open(_hyb)))
    for _t in _light['theme']['colors']:
        _t.pop('dark', None)
    silent(f'{HYBRID} with the dark variants dropped — light alone is clean', _light)

print()
if fails:
    print(f'{len(fails)} FAILED')
    for f in fails:
        print('  -', f)
    sys.exit(1)
print('all checks passed')

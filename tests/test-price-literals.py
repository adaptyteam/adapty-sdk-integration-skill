#!/usr/bin/env python3
"""Calibration for the price/discount/duration literal checks in `references/verify-config.py`.

Repo-only. Runs the shipped script as a subprocess -- never imports it, so nothing writes a
`__pycache__` into `references/`.

Why this exists. This repo has already shipped the failure: `patterns.md` carried a retired rule
telling agents to write prices as plain text, and an agent following it produced a paywall that
rendered perfectly and showed a **fabricated price**. Nothing objects to that document -- it is
well formed, `flows config validate` passes it, and the render looks finished.

Two tiers, and the corpus is what forced the split:

  * **Placeholder** ("$X.XX") -- reported always. 0 of the 12 real configs contain one and
    nobody intends to ship it. This is the template stub an agent copies instead of binding.
  * **Real-looking price / discount / duration** -- reported only under `--baseline`, because
    real exports legitimately carry them: `vpn-timer-draft` has "$59.99 / year" and "Only $1.15
    / week", `onboarding-quiz-paywall` has "Save 75%", `onboarding-multilocale` has "Best value
    - 12 months". A human typed those knowing the offer. Only a literal the document ADDS is
    evidence of fabrication, so the comparison is a set difference over visible strings -- copy
    that merely moved between elements is not a finding.

Two regexes are corrected against the versions they were adapted from, and both corrections have
their own case below because both were found by running the originals over real exports:

  * "fees of 1.99%" matched as "99%" -- the percent lookbehind needs `.` and `,` in it.
  * "S$1.49", "US$50", "A$12.00" were all missed -- requiring a non-alphanumeric before the
    currency symbol drops every prefixed currency.

Usage: python3 tests/test-price-literals.py     # 0 all pass, 1 a case regressed
"""
import glob, json, os, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERIFY = os.path.join(ROOT, 'skills', 'flow-generator', 'references', 'verify-config.py')
CORPUS = os.path.join(ROOT, 'tests', 'fixtures')
RAW = os.path.join(ROOT, 'tests', 'fixtures-raw')

PLACEHOLDER = 'template placeholder'
ADDED = 'is a new hardcoded'

fails = []


def run(doc, baseline=None):
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, 'c.json')
        json.dump(doc, open(path, 'w'))
        cmd = [sys.executable, VERIFY]
        if baseline is not None:
            base = os.path.join(tmp, 'base.json')
            json.dump(baseline, open(base, 'w'))
            cmd += ['--baseline', base]
        result = subprocess.run(cmd + [path], capture_output=True, text=True)
    if 'Traceback' in result.stderr:
        raise AssertionError(f'verify-config.py crashed:\n{result.stderr}')
    return [l.strip() for l in result.stdout.splitlines()
            if PLACEHOLDER in l or ADDED in l]


def fires(name, doc, fragment, baseline=None):
    hits = run(doc, baseline)
    if not any(fragment in line for line in hits):
        fails.append(f'{name}: expected a finding containing {fragment!r}, got {hits!r}')
        print(f'  FAIL  {name}')
    else:
        print(f'  ok    {name}')


def silent(name, doc, baseline=None):
    hits = run(doc, baseline)
    if hits:
        fails.append(f'{name}: expected no price finding, got {hits!r}')
        print(f'  FAIL  {name}')
    else:
        print(f'  ok    {name}')


# ------------------------------------------------------------------ a one-text-element screen
def spans(*nodes):
    return [{'type': 'paragraph', 'content': list(nodes)}]


def txt(s):
    return {'type': 'text', 'text': s}


def var(vid):
    return {'type': 'variable', 'attrs': {'variableId': vid}}


def flow(*lines, bare=None):
    """One screen holding one text element per line. `bare` uses the catalog-template form
    (`content` as a plain string) instead of rich text."""
    emap, kids = {}, []
    for n, line in enumerate(lines):
        eid = f'el_t{n}'
        content = ({'_localizable': True, 'values': {'en': line}} if bare is None
                   else bare)
        emap[eid] = {'id': eid, 'type': 'text', 'states': [], 'props': {
            'width': {'type': 'fill'}, 'height': {'type': 'hug'}, 'align': 'left',
            'layout': 'auto-height', 'decoration': 'none',
            'position': {'type': 'relative'}, 'font': {'preset': 'body'},
            'color': {'type': 'hex', 'hex': '#111114'}, 'content': content}}
        kids.append({'id': eid, 'children': []})
    return {
        'schemaVersion': 10, 'defaultLocale': 'en',
        'locales': [{'id': 'en', 'code': 'en', 'name': 'English'}],
        'theme': {'colors': [], 'typography': []},
        '_meta': {'screens': {}, 'icons': [], 'fonts': []},
        'screens': [{'id': 'scr_1', 'caption': 'Paywall', 'selectableGroups': [],
                     'props': {'safeArea': True, 'scrollable': False,
                               'padding': {'top': 8, 'left': 16, 'right': 16, 'bottom': 8},
                               'fill': [{'type': 'color',
                                         'color': {'type': 'hex', 'hex': '#FFFFFF'}}],
                               'layout': {'alignH': 'start', 'alignV': 'start',
                                          'direction': 'vertical',
                                          'distribution': {'type': 'gap', 'gap': 8}}},
                     'elements': {'map': emap,
                                  'hierarchy': {'id': 'root', 'children': kids}}}]}


EMPTY = flow(spans(txt('Unlock everything')))

# ------------------------------------------------------- FIRES: the placeholder, always
print('FIRES on a template placeholder, with no baseline needed:')
fires('"$X.XX/mo" — the stub an agent copies instead of binding',
      flow(spans(txt('Just $X.XX/mo'))), '$X.XX')
fires('a bare "$X"', flow(spans(txt('From $X'))), '$X')
fires('a non-dollar placeholder', flow(spans(txt('€XX.XX per year'))), '€XX.XX')
fires('the catalog-template form, where content is a plain string',
      flow(spans(txt('ignored')), bare='Only $X.XX'), '$X.XX')

# ------------------------------------------------------- FIRES: new literals vs a baseline
print('\nFIRES on a literal this document ADDS (against a baseline):')
fires('a new price', flow(spans(txt('Just $59.99 / year'))), 'hardcoded price', baseline=EMPTY)
fires('a new discount', flow(spans(txt('Save 40%'))), 'hardcoded discount', baseline=EMPTY)
fires('a new trial duration', flow(spans(txt('7 days free'))), 'hardcoded duration',
      baseline=EMPTY)
# The correction: requiring a non-alphanumeric before the symbol misses every prefixed currency.
fires('a prefixed currency — "S$1.49" (the upstream regex missed this)',
      flow(spans(txt('minimum fee S$1.49'))), 'hardcoded price', baseline=EMPTY)
fires('"US$50" likewise', flow(spans(txt('worth US$50'))), 'hardcoded price', baseline=EMPTY)

# ------------------------------------------------------- SILENT: the noise cases
print('\nSILENT where a finding would be noise:')
silent('a real price with NO baseline — absolute checking would second-guess the designer',
       flow(spans(txt('Just $59.99 / year'))))
silent('"Save 75%" with no baseline', flow(spans(txt('Save 75%'))))
silent('"Best value — 12 months" is a plan label, not a trial claim',
       flow(spans(txt('Best value — 12 months'))))

# The correction: "fees of 1.99%" matched as "99%" under the upstream lookbehind. A decimal
# percentage is not a discount claim, and this is a real string in tabs-paywall.json.
silent('a decimal percentage — "fees of 1.99%" is not a "99%" discount',
       flow(spans(txt('Exchange commodities with fees of 1.99%'))), baseline=EMPTY)

silent('copy that BINDS its price has no literal to find',
       flow(spans(txt('Just '), var('prod.prod_price_per_year'), txt(' / year'))),
       baseline=EMPTY)
silent('unchanged copy against its own baseline',
       flow(spans(txt('Just $59.99 / year'))),
       baseline=flow(spans(txt('Just $59.99 / year'))))
silent('the same line MOVED to another element is not an addition',
       flow(spans(txt('Filler')), spans(txt('Just $59.99 / year'))),
       baseline=flow(spans(txt('Just $59.99 / year')), spans(txt('Filler'))))

# --------------------------------------------------- SILENT on the corpus, both modes
_paths = sorted(glob.glob(os.path.join(CORPUS, '*.json'))) + \
         sorted(glob.glob(os.path.join(RAW, '*.json')))
print(f'\nSILENT on the corpus with no baseline ({len(_paths)} configs'
      f'{" — RAW ABSENT, tracked only" if not os.path.isdir(RAW) else ""}):')
for _p in _paths:
    silent(os.path.basename(_p), json.load(open(_p)))

print('\nSILENT on each corpus config against ITSELF (a document never accuses itself):')
for _p in _paths:
    _d = json.load(open(_p))
    silent(os.path.basename(_p), _d, baseline=_d)

print()
if fails:
    print(f'{len(fails)} FAILED')
    for f in fails:
        print('  -', f)
    sys.exit(1)
print('all checks passed')

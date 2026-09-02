#!/usr/bin/env python3
"""Calibration for the id-charset, cross-screen-duplicate and locale-code checks in
`references/verify-config.py`.

Repo-only. Runs the shipped script as a subprocess -- never imports it, so nothing writes a
`__pycache__` into `references/`.

Why this file exists. An element id reaches the generated runtime script as an IDENTIFIER --
the same code path `flowkit.config()`'s condition-variable check already documents, where an
unresolved variable head is emitted bare and fails to compile. A character outside
`[A-Za-z0-9_]` therefore produces a syntactically broken script and the flow draws a BLACK
SCREEN on device, while every gate reachable from here stays green: `flows config validate`
passes a hyphenated id (`references/validate.md` already records that row), the schema types
ids as bare strings, and `config preview` renders the config rather than the transformer's
output, so it draws the screen correctly. Preview-vs-device, with no preview-side tell.

THE SCOPE IS THE FINDING. The rule as stated in the source this was adopted from covers screen
ids too. The corpus refutes that: measured across the 7 tracked and 5 raw fixtures, 4 of 36
screen ids are bare UUIDs -- hyphens included -- and each is the ENTRY screen of a flow whose
status is `published`; `comparison-paywall.json`'s only screen is one of them, and it is a real
export, not a sanitization artifact (the raw copy carries a UUID too, a different one). A check
that fires on real published builder output is worse than no check. Element ids carry no such
exception: 911 of 911 across the same 12 configs are clean, which is what the guard rests on.

The same reasoning sets the severity of the third family. Group ids, input `customId`s and
custom variable ids are the heads of `<customId>.value` and `<groupId>.selectedOptionId`, so
they land in the same script -- corpus-clean (0 off-charset in all 12), but with no reproduced
black screen behind them, so they warn where an element id errors.

The locale-code check is the same lesson a third time. `pt-br` is refused at publish with a
pattern violation on `/localizations/N/id` because the SDK's pattern is case-sensitive per
subtag -- but the obvious `^[a-z]{2}(-[A-Z]{2})?$` is WRONG, because a script subtag is four
letters in Title case and `sr-Latn` is a real code in a real export (`onboarding-multilocale`).
The pinned SILENT case for `sr-Latn` is what stops that regression.

    FIRES   -- a hyphenated / dotted / spaced element id; an id reused on two screens;
               an off-charset groupId, customId or variable id (warning); `pt-br`, `PT-BR`,
               `sr-latn`, `pt_BR`
    SILENT  -- all 12 real exports; a UUID SCREEN id; `en`, `sr-Latn`, `pt-BR`, `zh-Hans`,
               `zh-Hant-HK`, `fil`

Usage: python3 tests/test-id-hygiene.py    # 0 all pass, 1 a case regressed
"""
import glob, json, os, re, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERIFY = os.path.join(ROOT, 'skills', 'flow-generator', 'references', 'verify-config.py')
CORPUS = os.path.join(ROOT, 'tests', 'fixtures')
RAW = os.path.join(ROOT, 'tests', 'fixtures-raw')

# Every line this suite owns, and nothing else -- the fixtures legitimately produce other
# findings (`timeline-anchored.json` fires legibility, for one) and matching loosely would
# turn those into failures of this file.
MINE = re.compile(r'element id\(s\)|more than one screen|identifier\(s\) outside|locale code')

fails = []


def run(doc):
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, 'c.json')
        json.dump(doc, open(path, 'w'))
        result = subprocess.run([sys.executable, VERIFY, path], capture_output=True, text=True)
    if 'Traceback' in result.stderr or 'CHECKER ERROR' in result.stdout:
        raise AssertionError(f'verify-config.py crashed on this document:\n{result.stdout}\n'
                             f'{result.stderr}')
    return [ln.strip() for ln in result.stdout.splitlines() if MINE.search(ln)]


def fires(name, doc, fragment):
    hits = run(doc)
    if not any(fragment in ln for ln in hits):
        fails.append(f'{name}: expected a finding containing {fragment!r}, got {hits!r}')
        print(f'  FAIL  {name}')
    else:
        print(f'  ok    {name}')


def silent(name, doc):
    hits = run(doc)
    if hits:
        fails.append(f'{name}: expected no id/locale finding, got {hits!r}')
        print(f'  FAIL  {name}')
    else:
        print(f'  ok    {name}')


def text_el(eid, custom_id=None, group_id=None):
    props = {'width': {'type': 'fill'}, 'height': {'type': 'hug'}, 'align': 'left',
             'layout': 'auto-height', 'decoration': 'none',
             'position': {'type': 'relative'}, 'font': {'preset': 'body'},
             'color': {'type': 'hex', 'hex': '#111111'},
             'content': {'_localizable': True, 'values': {'en': [
                 {'type': 'paragraph', 'content': [{'type': 'text', 'text': 'Plan'}]}]}}}
    if custom_id:
        props['customId'] = custom_id
    if group_id:
        props['groupId'] = group_id
    return {'id': eid, 'type': 'text', 'states': [], 'props': props}


def doc(screens, locales=(('en', 'en', 'English'),), default='en'):
    return {
        'schemaVersion': 10, 'defaultLocale': default,
        'locales': [{'id': i, 'code': c, 'name': n} for i, c, n in locales],
        'theme': {'colors': [], 'typography': []},
        '_meta': {'screens': {}, 'icons': [], 'fonts': []},
        'screens': screens}


def screen(sid, elements, groups=()):
    return {'id': sid, 'caption': 'Screen', 'selectableGroups': list(groups),
            'props': {'safeArea': True, 'scrollable': False,
                      'padding': {'top': 8, 'left': 16, 'right': 16, 'bottom': 8},
                      'fill': {'type': 'color', 'color': {'type': 'hex', 'hex': '#FFFFFF'}},
                      'layout': {'alignH': 'start', 'alignV': 'start',
                                 'direction': 'vertical',
                                 'distribution': {'type': 'gap', 'gap': 8}}},
            'elements': {'map': {e['id']: e for e in elements},
                         'hierarchy': {'id': 'root', 'children': [
                             {'id': e['id'], 'children': []} for e in elements]}}}


# ------------------------------------------------------------------------- FIRES
print('FIRES on an element id that cannot be an identifier:')
for label, eid in (('a hyphen', 'el-hero'), ('a dot', 'el.hero'), ('a space', 'el hero'),
                   ('a colon', 'el:hero')):
    fires(f'element id with {label} ({eid})',
          doc([screen('scr_1', [text_el(eid)])]), 'outside [A-Za-z0-9_]')

print()
print('FIRES on an element id reused across screens:')
fires('the same id on two screens',
      doc([screen('scr_1', [text_el('el_cta')]), screen('scr_2', [text_el('el_cta')])]),
      'more than one screen')

print()
print('FIRES (warning) on the softer identifier family:')
fires('an off-charset customId',
      doc([screen('scr_1', [text_el('el_t', custom_id='user-name')])]),
      'customId user-name')
fires('an off-charset groupId',
      doc([screen('scr_1', [text_el('el_t', group_id='plan-picker')],
                  groups=[{'id': 'plan-picker', 'type': 'single_choice'}])]),
      'groupId plan-picker')
_v = doc([screen('scr_1', [text_el('el_t')])])
_v['variables'] = [{'id': 'promo-code', 'type': 'string'}]
fires('an off-charset variables[].id', _v, 'variables[].id promo-code')

print()
print('FIRES on a locale code the SDK pattern refuses:')
for bad in ('pt-br', 'PT-BR', 'sr-latn', 'sr-LATN', 'pt_BR', 'en-us'):
    fires(f'locale code {bad!r}',
          doc([screen('scr_1', [text_el('el_t')])],
              locales=(('en', 'en', 'English'), (bad, bad, 'Other'))),
          'locale code')

# ------------------------------------------------------------------------- SILENT
print()
print('SILENT on the real corpus:')
for path in sorted(glob.glob(os.path.join(CORPUS, '*.json'))
                   + glob.glob(os.path.join(RAW, '*.json'))):
    d = json.load(open(path))
    d = d.get('config', d) if 'screens' not in d else d
    if not isinstance(d, dict) or 'screens' not in d:
        continue
    silent(f'{os.path.basename(os.path.dirname(path))}/{os.path.basename(path)}', d)

print()
print('SILENT on the shapes the guard must not reach:')
silent('a UUID SCREEN id — 4 of 36 corpus screen ids look like this, on published flows',
       doc([screen('9fd7c4e1-2b3a-4c5d-8e6f-0a1b2c3d4e5f', [text_el('el_t')])]))
for good in ('en', 'fil', 'sr', 'sr-Latn', 'pt-BR', 'zh-Hans', 'zh-Hant-HK', 'es-419'):
    silent(f'locale code {good!r}',
           doc([screen('scr_1', [text_el('el_t')])],
               locales=(('en', 'en', 'English'), (good, good, 'Other'))))
silent('an id that is all underscores and digits',
       doc([screen('scr_1', [text_el('_el_001A')])]))
silent('the same id on ONE screen twice is unrepresentable in JSON — one element, no finding',
       doc([screen('scr_1', [text_el('el_t')])]))

print()
if fails:
    print(f'{len(fails)} FAILED')
    for f in fails:
        print('  -', f)
    sys.exit(1)
print('all checks passed')

#!/usr/bin/env python3
"""Calibration for the icon-declaration check in `references/verify-config.py`, and for the
top-level guarantee that the script never answers a document with a traceback.

Repo-only. Runs the shipped script as a subprocess -- never imports it, so nothing writes a
`__pycache__` into `references/`.

Why this file exists. The check read `i['name']` and `i['weight']` straight off dicts an author
wrote, so a `_meta.icons` entry missing `weight` killed the script with a bare
`KeyError: 'weight'`. That is the second instance of a class CLAUDE.md already records -- the
envelope `KeyError: 'theme'` -- and the damage is the same both times: a stack trace reads as
"your config is corrupt" when it means "one field is missing", so the reader looks in the wrong
place. Found 2026-09-02 by feeding the checker a config built without the field.

Severity was chosen by measuring, not by taste: across the corpus and the shipped catalog, **0 of
21 `_meta.icons` entries, 0 of 60 icon elements and 0 of 76 catalog templates** omit either field.
An absent one is malformed authored input, so it is reported rather than defaulted away.

The last section is the generalisation, and it matters more than the single line: every other
direct subscript in a 1700-line checker is a latent version of the same bug, so `main` now
converts any unexpected exception into a CHECKER ERROR at **exit 2** -- distinct from exit 1,
which means the document has findings.

    FIRES   -- an icons entry or an icon element missing name or weight
    SILENT  -- every real config, and well-formed declarations

Usage: python3 tests/test-icon-declarations.py     # 0 all pass, 1 a case regressed
"""
import glob, json, os, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERIFY = os.path.join(ROOT, 'skills', 'flow-generator', 'references', 'verify-config.py')
CORPUS = os.path.join(ROOT, 'tests', 'fixtures')
RAW = os.path.join(ROOT, 'tests', 'fixtures-raw')
fails = []
SVG = '<svg viewBox="0 0 256 256"><circle cx="128" cy="128" r="96"/></svg>'


def run(doc, expect_crash=False):
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, 'c.json')
        json.dump(doc, open(path, 'w'))
        r = subprocess.run([sys.executable, VERIFY, path], capture_output=True, text=True)
    if not expect_crash and 'Traceback (most recent call last)' in r.stderr:
        raise AssertionError(f'verify-config.py crashed instead of reporting:\n{r.stderr}')
    return r.returncode, [l for l in r.stdout.splitlines() if 'icon' in l.lower()]


def fires(name, doc, fragment):
    _, hits = run(doc)
    if any(fragment in l for l in hits):
        print(f'  ok    {name}')
    else:
        fails.append(f'{name}: expected {fragment!r}, got {hits!r}')
        print(f'  FAIL  {name}')


def silent(name, doc):
    _, hits = run(doc)
    bad = [l for l in hits if 'ERROR' in l]
    if bad:
        fails.append(f'{name}: expected no icon error, got {bad!r}')
        print(f'  FAIL  {name}')
    else:
        print(f'  ok    {name}')


def doc(meta_icons, el_icon):
    el = {'id': 'el_i', 'type': 'icon', 'states': [], 'props': {
        'icon': el_icon, 'position': {'type': 'relative'}}}
    return {
        'schemaVersion': 10, 'defaultLocale': 'en',
        'locales': [{'id': 'en', 'code': 'en', 'name': 'English'}],
        'theme': {'colors': [], 'typography': []},
        '_meta': {'screens': {}, 'icons': meta_icons, 'fonts': []},
        'screens': [{'id': 'scr_1', 'caption': 'P', 'selectableGroups': [],
                     'props': {'safeArea': True, 'scrollable': False,
                               'padding': {'top': 8, 'left': 8, 'right': 8, 'bottom': 8},
                               'fill': {'type': 'color', 'color': {'type': 'hex', 'hex': '#FFFFFF'}},
                               'layout': {'alignH': 'start', 'alignV': 'start',
                                          'direction': 'vertical',
                                          'distribution': {'type': 'gap', 'gap': 8}}},
                     'elements': {'map': {'el_i': el},
                                  'hierarchy': {'id': 'root',
                                                'children': [{'id': 'el_i', 'children': []}]}}}]}


GOOD_META = [{'id': 'X', 'name': 'X', 'weight': 'regular', 'type': 'custom', 'raw': SVG}]
GOOD_EL = {'name': 'X', 'weight': 'regular', 'size': 22, 'type': 'custom'}

print('REPORTS instead of crashing:')
# The exact input that produced `KeyError: 'weight'`.
fires('a _meta.icons entry with no weight', doc([{'id': 'X', 'name': 'X', 'type': 'custom',
                                                  'raw': SVG}], GOOD_EL), "has no 'weight'")
fires('a _meta.icons entry with no name', doc([{'id': 'X', 'weight': 'regular', 'type': 'custom',
                                                'raw': SVG}], GOOD_EL), "has no 'name'")
fires('a _meta.icons entry that is not a dict at all', doc(['X'], GOOD_EL), '_meta.icons[0]')
fires('an icon ELEMENT with no weight — the other half of the same line',
      doc(GOOD_META, {'name': 'X', 'size': 22, 'type': 'custom'}), 'icon.weight')
fires('an icon ELEMENT with no name',
      doc(GOOD_META, {'weight': 'regular', 'size': 22, 'type': 'custom'}), 'icon.name')

print('\nSILENT on well-formed declarations:')
silent('name + weight on both sides', doc(GOOD_META, GOOD_EL))
# Declared and used agree, with the element typed `phosphor` rather than `custom`. (First
# written as "no icons at all" with an EMPTY _meta.icons while the element still used one, which
# correctly tripped the pre-existing used-but-absent check and tested nothing about this one.)
silent('a phosphor element whose declaration matches',
       doc([{'id': 'X', 'name': 'X', 'weight': 'bold', 'type': 'custom', 'raw': SVG}],
           {'name': 'X', 'weight': 'bold', 'size': 22, 'type': 'phosphor'}))

print('\nSILENT on real configs (the severity rests on this: 0 of 21 entries omit a field):')
paths = sorted(glob.glob(os.path.join(CORPUS, '*.json'))) + \
        sorted(glob.glob(os.path.join(RAW, '*.json')))
for p in paths:
    silent(os.path.basename(p), json.load(open(p)))

print('\nThe generalisation — a checker must never answer a document with a traceback:')
src = open(VERIFY).read()
if 'CHECKER ERROR' in src and 'sys.exit(2)' in src:
    print('  ok    main() converts an unexpected exception into CHECKER ERROR at exit 2')
else:
    fails.append('the top-level exception guard is gone from verify-config.py')
    print('  FAIL  the top-level exception guard is gone from verify-config.py')

print()
if fails:
    print(f'{len(fails)} FAILED')
    for f in fails:
        print('  -', f)
    sys.exit(1)
print('all icon-declaration checks passed')

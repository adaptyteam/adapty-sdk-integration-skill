#!/usr/bin/env python3
"""Calibration for the unmapped-element-type check in `references/verify-config.py`.

Repo-only. Runs the shipped script as a subprocess -- never imports it, so nothing writes a
`__pycache__` into `references/`.

Why this file exists. The published schema at `schemastore.adaptybuilder.com/latest.json`
annotates 47 definitions with `"x-supported"` -- true when the transform service has a mapper
handler for that variant. The repo already read this flag for the 16 `IAction*` definitions
(`selectProduct` is the only false one) and never read it for elements, where six more sit:
`old-price`, `header`, and the four-member progress-bar family.

`old-price` is the one worth guarding. Every gate we can run is blind to it: the schema
declares it, `flows config validate` accepts it, and `config preview` reads the config directly
so it draws a struck price -- while a device shows nothing, which this repo measured the
expensive way and then explained with an untested hypothesis about `multiplier`. The missing
mapper handler is the simpler explanation and it was in a file we already fetch every session.

The list is short ON PURPOSE, and the progress-bar case is why: it carries the same
`x-supported: false` flag and appears in real exports (`onboarding-quiz-paywall` and
`vpn-timer-draft` -- 2 of the corpus's 7 distinct flows), because the transformer handles
progress bars in a registry pass the static extractor cannot see. A check keyed on the flag
alone would fire on real builder output. Evidence order holds -- a real export outranks a
schema annotation -- so the guard covers only the types where the flag and the corpus agree.

    FIRES   -- an `old-price` element on a screen
    SILENT  -- all 12 real exports, the progress-bar family, and `old-price` inside `components`

Usage: python3 tests/test-unmapped-elements.py    # 0 all pass, 1 a case regressed
"""
import copy, glob, json, os, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERIFY = os.path.join(ROOT, 'skills', 'flow-generator', 'references', 'verify-config.py')
CORPUS = os.path.join(ROOT, 'tests', 'fixtures')
RAW = os.path.join(ROOT, 'tests', 'fixtures-raw')

MARKER = 'x-supported'

fails = []


def run(doc):
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, 'c.json')
        json.dump(doc, open(path, 'w'))
        result = subprocess.run([sys.executable, VERIFY, path], capture_output=True, text=True)
    if 'Traceback' in result.stderr:
        raise AssertionError(f'verify-config.py crashed:\n{result.stderr}')
    return [line for line in result.stdout.splitlines() if MARKER in line]


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
        fails.append(f'{name}: expected no unmapped-type finding, got {hits!r}')
        print(f'  FAIL  {name}')
    else:
        print(f'  ok    {name}')


def screen_with(element):
    """One screen carrying `element` beside a plain text node."""
    label = {'id': 'el_t', 'type': 'text', 'states': [], 'props': {
        'width': {'type': 'fill'}, 'height': {'type': 'hug'}, 'align': 'left',
        'layout': 'auto-height', 'decoration': 'none', 'position': {'type': 'relative'},
        'font': {'preset': 'body'}, 'color': {'type': 'hex', 'hex': '#111111'},
        'content': {'_localizable': True, 'values': {'en': [
            {'type': 'paragraph', 'content': [{'type': 'text', 'text': 'Plan'}]}]}}}}
    return {
        'schemaVersion': 10, 'defaultLocale': 'en',
        'locales': [{'id': 'en', 'code': 'en', 'name': 'English'}],
        'theme': {'colors': [], 'typography': []},
        '_meta': {'screens': {}, 'icons': [], 'fonts': []},
        'screens': [{'id': 'scr_1', 'caption': 'Paywall', 'selectableGroups': [],
                     'props': {'safeArea': True, 'scrollable': False,
                               'padding': {'top': 8, 'left': 16, 'right': 16, 'bottom': 8},
                               'fill': {'type': 'color',
                                        'color': {'type': 'hex', 'hex': '#FFFFFF'}},
                               'layout': {'alignH': 'start', 'alignV': 'start',
                                          'direction': 'vertical',
                                          'distribution': {'type': 'gap', 'gap': 8}}},
                     'elements': {
            'map': {'el_t': label, element['id']: element},
            'hierarchy': {'id': 'root', 'children': [
                {'id': 'el_t', 'children': []}, {'id': element['id'], 'children': []}]}}}]}


def old_price(eid='el_op'):
    return {'id': eid, 'type': 'old-price', 'states': [], 'props': {
        'font': {'preset': 'body'}, 'color': {'type': 'hex', 'hex': '#888888'},
        'width': {'type': 'hug'}, 'height': {'type': 'hug'},
        'layout': 'auto-height', 'multiplier': 2, 'position': {'type': 'relative'}}}


def progress_bar(eid='el_pb'):
    return {'id': eid, 'type': 'progress-bar', 'states': [], 'props': {
        'width': {'type': 'fill'}, 'height': {'type': 'hug'},
        'position': {'type': 'relative'}}}


# ------------------------------------------------------------------------- FIRES
print('FIRES on an element the transform service has no mapper for:')
fires('an `old-price` element on a screen', screen_with(old_price()), 'old-price')

_two = screen_with(old_price())
_map = _two['screens'][0]['elements']['map']
_map['el_op2'] = old_price('el_op2')
_two['screens'][0]['elements']['hierarchy']['children'].append({'id': 'el_op2', 'children': []})
_hits = run(_two)
if len(_hits) == 2:
    print('  ok    reports each occurrence, not just the first')
else:
    fails.append(f'expected 2 findings for 2 old-price elements, got {_hits!r}')
    print('  FAIL  reports each occurrence, not just the first')

# ------------------------------------------------------------------------- SILENT
print('\nSILENT on real builder output:')

# The false negative that keeps the list short. Both of these are REAL exports.
silent('a `progress-bar` element — same flag, but 2 of 12 real exports carry it',
       screen_with(progress_bar()))

# `components` entries are the builder's own global blocks; vpn-timer-draft parks a
# progress-bar-loader in one. The check walks screens only, and this pins that.
_comp = screen_with(old_price())
_comp['screens'][0]['elements']['map'].pop('el_op')
_comp['screens'][0]['elements']['hierarchy']['children'] = [{'id': 'el_t', 'children': []}]
_comp['components'] = {'cmp_1': {
    'map': {'el_op': old_price()},
    'hierarchy': {'id': 'root', 'children': [{'id': 'el_op', 'children': []}]}}}
silent('an unmapped type inside `components` is not a screen finding', _comp)

silent('a screen with no unmapped type at all',
       screen_with({'id': 'el_d', 'type': 'divider', 'states': [], 'props': {
           'width': {'type': 'fill'}, 'height': {'type': 'fixed', 'value': 1},
           'position': {'type': 'relative'}}}))

_paths = sorted(glob.glob(os.path.join(CORPUS, '*.json'))) + \
         sorted(glob.glob(os.path.join(RAW, '*.json')))
print(f'\nSILENT on the tracked corpus ({len(_paths)} configs'
      f'{" — RAW ABSENT, tracked only" if not os.path.isdir(RAW) else ""}):')
for _p in _paths:
    silent(os.path.basename(_p), json.load(open(_p)))

# ------------------------------------------------------------------------- schema tie
# The list is the SCHEMA's, not ours. If the transformer gains an `old-price` mapper the flag
# flips to true and this guard becomes a false positive, so the suite has to notice. Same
# pattern as test-flowkit.py tying TIMER_UNITS to the ETimerToken enum. Cache-only: this suite
# stays offline, and `gates.sh` / validate-with-schema.mjs are what warm the cache.
print('\nThe constant tracks the published schema:')
_cache = os.path.join(tempfile.gettempdir(), 'adapty-flow.schema.json')
_defs = None
if os.path.exists(_cache):
    try:
        _defs = json.load(open(_cache)).get('$defs', {})
    except (ValueError, OSError):
        _defs = None
if not _defs:
    print('  SKIP  no cached schema at $TMPDIR/adapty-flow.schema.json')
else:
    _unsupported = {d.get('x-type-literal') for d in _defs.values()
                    if isinstance(d, dict) and d.get('x-supported') is False}
    _guarded = {'old-price'}
    if _guarded <= _unsupported:
        print(f'  ok    every guarded type is still "x-supported": false '
              f'(schema flags {len(_unsupported)} in total)')
    else:
        _stale = sorted(_guarded - _unsupported)
        fails.append(f'guarded type(s) {_stale} are no longer "x-supported": false — the '
                     f'transformer gained a mapper, so drop them from UNMAPPED_ELEMENT_TYPES')
        print('  FAIL  a guarded type is now supported')

print()
if fails:
    print(f'{len(fails)} FAILED')
    for f in fails:
        print('  -', f)
    sys.exit(1)
print('all checks passed')

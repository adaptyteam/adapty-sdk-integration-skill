#!/usr/bin/env python3
"""Calibration for the selection-invisible check in `references/verify-config.py`.

Repo-only. Runs the shipped script as a subprocess -- never imports it, so nothing writes a
`__pycache__` into `references/`.

Why this file exists. A paywall built with this skill shipped to a real user with two plan
cards that could not show their selection: the violet "selected" look was baked into the card
that started selected, and the muted look into the other. The group was real, so tapping did
change the selection -- and nothing on screen moved. The user's words were "it just blinks, and
nothing changes".

`patterns.md` has stated the rule in prose since the plan-card section was written ("Put the
selected LOOK in `propsByState`, never on whichever card starts selected") and it was read past
anyway, because the reference screenshot showed one card highlighted and copying a static image
literally bakes in the one frame it can show. A prose rule that was documented AND still
defeated is this repo's trigger for a mechanical guard.

Nothing else catches it, and that is the point: `flows config validate` returns valid (the
document is well formed), the schema check passes (both shapes are legal), and `config preview`
draws one frame in which the baked-in look and the state-driven look are pixel-identical.

    FIRES   -- a group whose members differ in their BASE props with no `propsByState.selected`
    SILENT  -- every real export, and the corrected form of the artifact that caused this

Usage: python3 tests/test-selected-state.py     # 0 all pass, 1 a case regressed
"""
import copy, glob, json, os, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERIFY = os.path.join(ROOT, 'skills', 'flow-generator', 'references', 'verify-config.py')
CORPUS = os.path.join(ROOT, 'tests', 'fixtures')
RAW = os.path.join(ROOT, 'tests', 'fixtures-raw')

BAKED = 'baked into one member'
INDISTINCT = 'cannot tell which one is selected'

fails = []


def run(doc):
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
    hits = [l for l in errs + warns if BAKED in l or INDISTINCT in l]
    if hits:
        fails.append(f'{name}: expected no selection finding, got {hits!r}')
        print(f'  FAIL  {name}')
    else:
        print(f'  ok    {name}')


# ------------------------------------------------------------------ a two-card plan picker
def picker(*, baked, state_on='member'):
    """A minimal product group.

    `baked=True` reproduces the shipped defect: the two cards differ in their base fill and
    nothing declares a selected state. `state_on` places the override where a real export puts
    it -- on the member itself, or (as the builder often does) only on a descendant.
    """
    def card(eid, fill_id, default):
        return {'id': eid, 'type': 'product', 'states': [], 'caption': eid,
                'props': {'width': {'type': 'fill'}, 'height': {'type': 'hug'},
                          'position': {'type': 'relative'},
                          'layout': {'direction': 'vertical',
                                     'distribution': {'type': 'gap', 'gap': 8}},
                          'groupId': 'plans', 'default': default,
                          'product': {'id': f'0000000-{eid}'},
                          'fill': [{'type': 'color',
                                    'color': {'type': 'color-style', 'colorId': fill_id}}]}}

    def label(eid, color_id):
        return {'id': eid, 'type': 'text', 'states': [], 'props': {
            'width': {'type': 'fill'}, 'height': {'type': 'hug'}, 'align': 'left',
            'layout': 'auto-height', 'decoration': 'none',
            'position': {'type': 'relative'}, 'font': {'preset': 'body'},
            'color': {'type': 'color-style', 'colorId': color_id},
            'content': {'_localizable': True, 'values': {'en': [
                {'type': 'paragraph', 'content': [{'type': 'text', 'text': eid}]}]}}}}

    on, off = ('planOn', 'planOff') if baked else ('planOff', 'planOff')
    m = {'el_A': card('el_A', on, True), 'el_B': card('el_B', off, False),
         'el_At': label('el_At', 'ink'), 'el_Bt': label('el_Bt', 'ink')}
    if not baked:
        sel = {'fill': [{'type': 'color',
                         'color': {'type': 'color-style', 'colorId': 'planOn'}}]}
        if state_on == 'member':
            for k in ('el_A', 'el_B'):
                m[k]['states'] = [{'id': 'selected', 'type': 'system'}]
                m[k]['propsByState'] = {'selected': sel}
        else:                       # only a DESCENDANT carries the override
            for k in ('el_At', 'el_Bt'):
                m[k]['propsByState'] = {'selected': {
                    'color': {'type': 'color-style', 'colorId': 'ink'}}}
    return {
        'schemaVersion': 10, 'defaultLocale': 'en',
        'locales': [{'id': 'en', 'code': 'en', 'name': 'English'}],
        'variables': [], 'components': [],
        'theme': {'colors': [{'id': c, 'light': {'hex': '#111111', 'opacity': 100},
                              'dark': {'hex': '#111111', 'opacity': 100}}
                             for c in ('planOn', 'planOff', 'ink')],
                  'typography': [{'id': 'body', 'size': 14, 'weight': 'regular'}]},
        '_meta': {'icons': [], 'fonts': [], 'screens': {}},
        'screens': [{'id': 'scr_p', 'caption': 'Plans',
                     'selectableGroups': [{'id': 'plans', 'type': 'product'}],
                     'props': {'scrollable': True},
                     'elements': {
                         'map': m,
                         'hierarchy': {'id': 'root', 'children': [
                             {'id': 'el_A', 'children': [{'id': 'el_At'}]},
                             {'id': 'el_B', 'children': [{'id': 'el_Bt'}]}]}}}]}


# ---------------------------------------------------------------- SILENT: the real corpus
print('SILENT on every real export (the false-positive half):')
for path in sorted(glob.glob(os.path.join(CORPUS, '*.json'))):
    silent(f'tracked {os.path.basename(path)}', json.load(open(path)))
for path in sorted(glob.glob(os.path.join(RAW, '*.json'))):
    silent(f'raw {os.path.basename(path)}', json.load(open(path)))

# ------------------------------------------------------- SILENT: both correct placements
silent('the override on the MEMBER (comparison-paywall does this)',
       picker(baked=False, state_on='member'))
silent('the override only on a DESCENDANT (the builder often does this)',
       picker(baked=False, state_on='descendant'))

# ------------------------------------------------------------------- FIRES: the real defect
print('\nFIRES on the shipped defect (the false-negative half):')
fires('two cards styled differently in their base props, no selected state anywhere',
      picker(baked=True), BAKED)

# A group whose members are identical AND have no selected state shows the user nothing. That
# is a weaker claim -- a radio dot with its own state is a legitimate way to mark selection --
# so it is a warning, not an error.
_flat = picker(baked=False)
for _k in ('el_A', 'el_B'):
    _flat['screens'][0]['elements']['map'][_k].pop('propsByState', None)
    _flat['screens'][0]['elements']['map'][_k]['states'] = []
fires('members identical with no selected state — nothing marks the selection',
      _flat, INDISTINCT, level='warning')

# A one-member group cannot have a selection defect; guards against firing on a single product.
_one = picker(baked=True)
_s = _one['screens'][0]
del _s['elements']['map']['el_B']
del _s['elements']['map']['el_Bt']
_s['elements']['hierarchy']['children'] = [_s['elements']['hierarchy']['children'][0]]
silent('a single-member group is not a selection defect', _one)

print()
if fails:
    print(f'{len(fails)} FAILED')
    for f in fails:
        print('  -', f)
    sys.exit(1)
print('all checks passed')

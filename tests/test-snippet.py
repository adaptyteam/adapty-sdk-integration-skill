#!/usr/bin/env python3
"""Calibration for `skills/flow-generator/references/snippet.py`.

Repo-only. Most cases run the shipped script as a subprocess. A few properties (object
identity across a mutation) cannot be observed through a subprocess boundary -- JSON
decoding a subprocess's stdout always mints fresh objects, so an alias-vs-copy bug is
invisible to a `json.loads(stdout)` assertion. Those cases import `snippet` in-process
instead, guarded by `sys.dont_write_bytecode = True` (matching tests/test-flowkit.py) so
nothing writes a `__pycache__` into `references/`, which the copy-install path would ship.

Usage: python3 tests/test-snippet.py      # 0 all pass, 1 a case regressed
"""
import json, os, re, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNIP = os.path.join(ROOT, 'skills', 'flow-generator', 'references', 'snippet.py')
VERIFY = os.path.join(ROOT, 'skills', 'flow-generator', 'references', 'verify-config.py')
# a skills dir installs by plain copy, so a __pycache__ under references/ would SHIP with it
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(ROOT, 'skills', 'flow-generator', 'references'))

import snippet as sn  # noqa: E402
CORPUS = os.path.join(ROOT, 'tests', 'fixtures')
QUIZ = os.path.join(CORPUS, 'onboarding-quiz-paywall.json')
COMP = os.path.join(CORPUS, 'comparison-paywall.json')
TABS = os.path.join(CORPUS, 'tabs-paywall.json')
VPN = os.path.join(CORPUS, 'vpn-timer-draft.json')
QUIZ_S0 = 'a4895438-9468-4f5c-9697-f22261a33e1d'
COMP_S0 = '21153886-cb07-453f-c6fc-4e2ccf8b64ab'

fails = []


def run(*args):
    """Return (rc, stdout, stderr) from the shipped script."""
    r = subprocess.run([sys.executable, SNIP, *args], capture_output=True, text=True)
    return r.returncode, r.stdout, r.stderr


def run_where(home_dir, cwd=None):
    """Like `run(\'where\')`, but with a CONTROLLED $HOME (and cwd) -- `where`\'s
    result depends on what the machine running this suite happens to have in the
    real home directory (an existing `~/adapty-flow-snippets/` wins per the
    documented precedence rule), so a hermetic test drives both explicitly rather
    than reading whatever is actually there."""
    env = dict(os.environ)
    env['HOME'] = home_dir
    r = subprocess.run([sys.executable, SNIP, 'where'], capture_output=True, text=True,
                       env=env, cwd=cwd or ROOT)
    return r.returncode, r.stdout, r.stderr


def case(label, got, want):
    ok = got == want
    print(f'{"pass" if ok else "FAIL"}  {label:58} {got!r}')
    if not ok:
        fails.append(f'{label}: wanted {want!r}, got {got!r}')


# --- Task 1: the script exists and reports usage -------------------------------
case('usage: no args exits 2', run()[0], 2)
case('usage: unknown subcommand exits 2', run('frobnicate')[0], 2)

# --- Task 2: the dependency scanner --------------------------------------------
def scan(config_path, *eids):
    rc, out, err = run('scan', '--config', config_path, *eids)
    assert rc == 0, f'scan failed: {err}'
    return json.loads(out)

# Screen 0 of the quiz, whole subtree via its root. `pb_dl05vuVs` is a root child,
# so the component must be reported as a dependency, not skipped as a missing element.
d = scan(QUIZ, 'root@' + QUIZ_S0)
case('scan: quiz s0 finds its component', d['components'], ['pb_dl05vuVs'])
case('scan: quiz s0 icon deps are (name, weight) pairs',
     all(isinstance(x, list) and len(x) == 2 for x in d['icons']), True)
case('scan: quiz s0 typography ids are known presets',
     set(d['typography']) <= {'h1', 'h2', 'h3', 'button-label', 'body', 'caption',
                              'small-label'}, True)
case('scan: quiz s0 reports no fonts (fixture has none)', d['fonts'], [])

# The paywall screen carries the products group and the price bindings.
pay = scan(QUIZ, 'root@' + json.load(open(QUIZ))['screens'][-1]['id'])
case('scan: quiz paywall finds the products group', 'products' in pay['groups'], True)

# `name.value` is produced by a text-input on the Quiz screen and consumed on three
# others, so a single-screen scan must report it as consumed.
case('scan: quiz paywall consumes name.value', 'name.value' in pay['consumes'], True)

comp = scan(COMP, 'root@' + COMP_S0)
case('scan: comparison uses typ_RPXzQ8BE', 'typ_RPXzQ8BE' in comp['typography'], True)
case('scan: comparison colors are clr_* ids',
     all(c.startswith('clr_') or c == 'accent' for c in comp['colors']), True)

# --- Regression: the transitive component merge must fold ALL nine keys --------
# `pb_dl05vuVs` (the progress-bar component) carries no groupId/product/variableId/
# token anywhere in the tracked corpus, so a merge that only folds colors/typography/
# fonts/icons is silent on it -- inject one of each to prove the merge actually
# reaches into a pulled-in component rather than relying on a fixture that happens
# to already exercise this path.
_quiz_a = json.load(open(QUIZ))
_root_a = _quiz_a.get('config', _quiz_a)
_comp_map = _root_a['components']['pb_dl05vuVs']['map']
_comp_eid = next(iter(_comp_map))
_comp_map[_comp_eid].setdefault('props', {})
_comp_map[_comp_eid]['props']['groupId'] = 'grp_injected_for_test'
_comp_map[_comp_eid]['props']['product'] = {'id': 'prod_injected_for_test'}
with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as fh:
    json.dump(_quiz_a, fh)
    _injected_path = fh.name
try:
    merged_d = scan(_injected_path, 'root@' + QUIZ_S0)
    case('scan: transitive component merge reports its groupId',
         'grp_injected_for_test' in merged_d['groups'], True)
    case('scan: transitive component merge reports its product',
         'prod_injected_for_test' in merged_d['products'], True)
finally:
    os.unlink(_injected_path)

# --- Regression: icons sort must not crash when a weight is missing ------------
# Two icon elements sharing a name where one has no `weight` reproduces the
# None-vs-str comparison that `sorted()` cannot make in Python 3.
_quiz_b = json.load(open(QUIZ))
_root_b = _quiz_b.get('config', _quiz_b)
_s0 = next(s for s in _root_b['screens'] if s['id'] == QUIZ_S0)
_checkcircle_eids = [eid for eid, el in _s0['elements']['map'].items()
                      if el.get('type') == 'icon'
                      and (el.get('props') or {}).get('icon', {}).get('name') == 'CheckCircle']
assert len(_checkcircle_eids) >= 2, \
    'fixture no longer has 2+ CheckCircle icons on screen 0 -- adjust the injection'
_s0['elements']['map'][_checkcircle_eids[0]]['props']['icon']['weight'] = None
with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as fh:
    json.dump(_quiz_b, fh)
    _weightless_path = fh.name
try:
    rc, out, err = run('scan', '--config', _weightless_path, 'root@' + QUIZ_S0)
    case('scan: icons with a missing weight do not crash the sort', rc, 0)
    if rc == 0:
        icon_d = json.loads(out)
        case('scan: the weightless icon is still reported',
             any(name == 'CheckCircle' and w is None for name, w in icon_d['icons']), True)
finally:
    os.unlink(_weightless_path)

# --- Task 3: extract, the file, inspect, list ----------------------------------
TMP = tempfile.mkdtemp(prefix='snippet-test-')

def extract(config_path, target_flag, target, name, extra=()):
    out = os.path.join(TMP, re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
                       + '.flow-snippet.json')
    rc, so, se = run('extract', '--config', config_path, target_flag, target,
                     '--name', name, '--out', out, *extra)
    assert rc in (0, 1), f'extract failed rc={rc}: {se}'
    return out, json.load(open(out)), so

p, s, _ = extract(QUIZ, '--screen', QUIZ_S0, 'Quiz welcome')
case('extract: kind is screen', s['kind'], 'screen')
case('extract: formatVersion', s['formatVersion'], 1)
case('extract: screen payload carries selectableGroups',
     'selectableGroups' in s['payload']['screen'], True)
case('extract: screen drags its component definition',
     list(s['dependencies']['components']), ['pb_dl05vuVs'])
case('extract: no flowProductId anywhere in the snippet',
     'flowProductId' in json.dumps(s), False)
case('extract: no _meta block rides along in the payload',
     '_meta' in json.dumps(s['payload']), False)

# A single element subtree.
first_el = json.load(open(QUIZ))['screens'][0]['elements']['hierarchy']['children'][1]['id']
p2, s2, _ = extract(QUIZ, '--element', first_el + '@' + QUIZ_S0, 'One block')
case('extract: kind is element', s2['kind'], 'element')
case('extract: element payload has rootId', s2['payload']['rootId'], first_el)
case('extract: every payload map key equals its element id',
     all(k == v['id'] for k, v in s2['payload']['map'].items()), True)

# Comparison's fonts are reachable ONLY through theme presets -- the transitive case.
p3, s3, _ = extract(COMP, '--screen', COMP_S0, 'Comparison table')
carried_fonts = {f['id'] for f in s3['dependencies']['fonts']}
case('extract: a carried preset drags its font (invariant 9 path 2)',
     len(carried_fonts) > 0, True)
case('extract: carried typography are full definitions',
     all(set(t) >= {'id', 'name', 'settings'} for t in s3['dependencies']['typography']),
     True)

# Theme kind: no payload at all.
p4, s4, _ = extract(COMP, '--theme', 'all', 'Comparison tokens')
case('extract: theme kind has null payload', s4['payload'], None)
case('extract: theme kind carries every colour the flow defines',
     len(s4['dependencies']['colors']),
     len(json.load(open(COMP))['theme']['colors']))

# inspect / list are read-only and must not need a config.
case('inspect: exits 0 on a good snippet', run('inspect', p3)[0], 0)
case('inspect: names the kind', 'screen' in run('inspect', p3)[1], True)
case('list: finds the four files just written',
     run('list', '--dir', TMP)[1].count('.flow-snippet.json'), 4)

# `where` resolves the storage folder so the agent never invents one. HERMETIC:
# driven with a CONTROLLED $HOME, because the real result depends on what the
# machine running this suite happens to have in the real home directory -- this
# repo's own repo root has no `adapty-flow-snippets/`, but a real $HOME can (and
# on the machine this was authored on, does: an earlier session in the same
# workspace created one, and the ORIGINAL version of this test read the real
# $HOME and went red for a reason invisible to the next reader). Both cases the
# documented precedence rule describes are exercised explicitly instead.
_home_empty = tempfile.mkdtemp(prefix='snippet-home-empty-')
rc, out, _e = run_where(_home_empty)
case('where: exits 0', rc, 0)
_where_lines = out.splitlines()
case('where: proposes a path under the repo root when neither the repo root '
     'nor $HOME has one yet',
     _where_lines[0], os.path.join(ROOT, 'adapty-flow-snippets'))
case('where: an absent folder is reported as proposed, not existing',
     _where_lines[1], 'proposed — ask before writing')

# The precedence case the real failure exposed and nothing covered: an EXISTING
# $HOME/adapty-flow-snippets/ wins over a repo root that has none -- the
# documented rule ("An existing folder wins: repo root, then $HOME").
_home_existing = tempfile.mkdtemp(prefix='snippet-home-existing-')
os.makedirs(os.path.join(_home_existing, 'adapty-flow-snippets'))
rc2, out2, _e2 = run_where(_home_existing)
_where_lines2 = out2.splitlines()
case('where: an existing $HOME folder wins when the repo root has none',
     _where_lines2[0], os.path.join(_home_existing, 'adapty-flow-snippets'))
case('where: an existing $HOME folder is reported as existing',
     _where_lines2[1], 'existing')

# The OTHER half of the same precedence rule, and the only scenario that
# actually exercises ordering (the two cases above each have only ONE of the
# two folders, so a plain repo-vs-home reorder cannot change their result --
# confirmed below by reverting the order and finding those two stay green).
# When BOTH exist, the documented rule says repo root wins. A temp folder is
# created directly under ROOT for this one case and removed in `finally` --
# never left behind, and never the real $HOME directory.
_home_also_existing = tempfile.mkdtemp(prefix='snippet-home-also-existing-')
os.makedirs(os.path.join(_home_also_existing, 'adapty-flow-snippets'))
_repo_snippet_dir = os.path.join(ROOT, 'adapty-flow-snippets')
_repo_dir_preexisted = os.path.isdir(_repo_snippet_dir)
if not _repo_dir_preexisted:
    os.makedirs(_repo_snippet_dir)
try:
    rc3, out3, _e3 = run_where(_home_also_existing)
    _where_lines3 = out3.splitlines()
    case('where: an existing REPO ROOT folder wins over an existing $HOME one '
         '(repo root, then $HOME)',
         _where_lines3[0], _repo_snippet_dir)
    case('where: the repo-root winner is reported as existing',
         _where_lines3[1], 'existing')
finally:
    if not _repo_dir_preexisted:
        os.rmdir(_repo_snippet_dir)

# --- Task 4: theme resolution --------------------------------------------------
def plan_json(config_path, snippet_path, screen, extra=()):
    rc, out, err = run('plan', '--config', config_path, '--snippet', snippet_path,
                       '--screen', screen, '--json', *extra)
    assert out.strip(), f'plan printed nothing (rc={rc}): {err}'
    return rc, json.loads(out)

# quiz screen 0 -> comparison. `p`'s own preset deps (button-label, caption, h1) all
# exist in comparison with DIFFERENT settings -> adopt; its colour deps split the
# same way (accent shared-but-different -> adopt, gray-200/white missing -> carry).
_rc, pl = plan_json(COMP, p, COMP_S0)          # p is the quiz-screen snippet, Task 3
adopted = {a['id'] for a in pl['adopt']}
case('theme: shared presets with different settings are adopted',
     {'h1', 'button-label'} & adopted == {'h1', 'button-label'}, True)
carried_colors = {c['id'] for c in pl['carry']['colors']}
case('theme: white is carried', 'white' in carried_colors, True)
case('theme: white is NOT also adopted', 'white' in adopted, False)
case('theme: accent (shared, different definition) is adopted, not reused',
     'accent' in adopted, True)

# Screen 0 alone never references `h3` -- it's a dependency of the QUIZ FLOW'S
# theme, not of this fragment. Extract the theme kind to reach it: six preset ids
# (h1 h2 body button-label caption small-label) are shared with DIFFERENT settings
# -> adopt, `h3` is missing from comparison entirely -> carry, ten of quiz's eleven
# colours are missing -> carry, `accent` is shared but differently defined -> adopt.
p5, _s5, _ = extract(QUIZ, '--theme', 'all', 'Quiz tokens')
_rc4, pl4 = plan_json(COMP, p5, COMP_S0)
carried_presets = {t['id'] for t in pl4['carry']['typography']}
case('theme: h3 is carried (comparison lacks it)', 'h3' in carried_presets, True)
case('theme: h3 is NOT also adopted',
     'h3' in {a['id'] for a in pl4['adopt']}, False)
case('theme: ten of quiz colours are carried into comparison',
     len(pl4['carry']['colors']), 10)

# comparison -> quiz. Its presets name fonts quiz does not have, so carrying a
# preset must carry the font: invariant 9's second reference path. But h1/h2/
# button-label/body/caption/small-label are all ADOPTED (quiz already has those
# ids), so their fonts (f1563063... and 80ccb8e9...) must NOT be dragged in dead --
# only typ_RPXzQ8BE is actually carried, and only its own font (c9c5360d...) with it.
_rc2, pl2 = plan_json(QUIZ, p3, QUIZ_S0)       # p3 is the comparison snippet
case('theme: typ_RPXzQ8BE is carried into quiz',
     'typ_RPXzQ8BE' in {t['id'] for t in pl2['carry']['typography']}, True)
case('theme: carrying that preset carries exactly its own font, no more',
     {f['id'] for f in pl2['carry']['fonts']},
     {'c9c5360d-44d1-4f97-3754-f1ab62af984c'})
case("theme: a font whose only referencing preset was ADOPTED is not carried",
     'f1563063-c255-4186-d4c1-0c373d590032' in {f['id'] for f in pl2['carry']['fonts']},
     False)
case("theme: nor is the font shared by two other adopted presets",
     '80ccb8e9-b1d3-45ba-6871-5e83b564af42' in {f['id'] for f in pl2['carry']['fonts']},
     False)

# Same flow, same theme: nothing to adopt, nothing to carry.
_rc3, pl3 = plan_json(QUIZ, p, QUIZ_S0)
case('theme: grafting into its own flow adopts nothing', pl3['adopt'], [])
case('theme: grafting into its own flow carries no colours',
     pl3['carry']['colors'], [])

# --- Task 5: id re-minting and reference rewriting ------------------------------
# Grafting a snippet back into its own flow collides on EVERY element id.
_rc, pl = plan_json(QUIZ, p2, QUIZ_S0)      # p2 = the one-element quiz snippet
case('ids: same-flow graft renames every element',
     set(pl['renames']['elements']) == set(json.load(open(p2))['payload']['map']), True)
case('ids: a minted id never starts with a digit',
     all(not v[:1].isdigit() for v in pl['renames']['elements'].values()), True)
case('ids: a minted id is not already taken',
     not (set(pl['renames']['elements'].values())
          & set(json.load(open(QUIZ))['screens'][0]['elements']['map'])), True)

# The `tabs` trap: a group named `tabs` must not rewrite an element `type: "tabs"`.
# Checked on the REWRITTEN PAYLOAD the plan carries, so this task needs no `graft`.
TABS_S0 = json.load(open(TABS))['screens'][0]['id']
tp, tsnip, _ = extract(TABS, '--screen', TABS_S0, 'Tabs screen')
_rc, tpl = plan_json(TABS, tp, TABS_S0)
tmap = tpl['_payload']['screen']['elements']['map']
case('ids: the tabs group was renamed', 'tabs' in tpl['renames']['groups'], True)
types = {e['type'] for e in tmap.values()}
case('ids: element type "tabs" survived the groupId rename', 'tabs' in types, True)
case('ids: no element type was renamed to tabs_2',
     any(str(t).endswith('_2') for t in types), False)
case('ids: the groupId itself WAS rewritten in props',
     any((e.get('props') or {}).get('groupId', '').endswith('_2')
         for e in tmap.values()), True)

# A screen grafted back into its own flow must not duplicate a screen id.
_rc, spl = plan_json(TABS, tp, TABS_S0)
case('ids: a colliding screen id is re-minted',
     spl['renames']['screens'].get(TABS_S0, '') not in ('', TABS_S0), True)
# The re-mint must actually be APPLIED to the payload, not merely recorded in
# `renames['screens']` -- that distinction is the whole bug `build_plan` closes.
# A test that only checked `renames['screens']` is populated (the case above)
# would still pass if the write-back line were deleted; this one would not.
case("ids: the re-minted screen id is WRITTEN onto the payload, not just recorded",
     spl['_payload']['screen']['id'], spl['renames']['screens'][TABS_S0])
case('ids: the payload screen id no longer collides with the original',
     spl['_payload']['screen']['id'] != TABS_S0, True)

# --- Task 5 fix: variableId rewrite must reach conditional branches --------------
# A `conditional` action's payload shape, confirmed against the real fixture: a case
# is `[predicate_dict, {"type": "const", "value": [...]}]`, not `{"actions": [...]}`,
# and `default` is a sibling action container read nowhere by the hand-rolled walk
# this replaced. Both hide a groupId head the same way a predicate's
# `left.variableId` does, and neither had a failing test before this block.
_synthetic_el = {
    'id': 'el_synth', 'type': 'text',
    'interactions': [{
        'id': 'int_synth', 'trigger': 'tap',
        'actions': [{
            'id': 'act_synth_cond', 'type': 'conditional',
            'payload': {
                'type': 'switch',
                'cases': [[
                    {'type': '&&', 'predicates': [{
                        'left': {'type': 'var', 'variableId': 'products.selectedProduct'},
                        'type': '==',
                        'right': {'type': 'const', 'value': 'prod-a'},
                    }]},
                    {'type': 'const', 'value': [{
                        'id': 'act_synth_case_purchase', 'type': 'purchase',
                        'payload': {'product': {'type': 'var',
                                               'variableId': 'products.selectedProduct'}},
                    }]},
                ]],
                'default': {'type': 'const', 'value': [{
                    'id': 'act_synth_default_purchase', 'type': 'purchase',
                    'payload': {'product': {'type': 'var',
                                           'variableId': 'products.selectedProduct'}},
                }]},
            },
        }],
    }],
}
_synthetic_snippet = {
    'formatVersion': 1, 'kind': 'element', 'name': 'Synthetic conditional',
    'description': '', 'savedAt': '2026-08-27',
    'source': {'app': None, 'flowName': None, 'screenId': None, 'schemaVersion': None},
    'intendedScope': 'same-app',
    'payload': {'rootId': 'el_synth', 'map': {'el_synth': _synthetic_el},
                'hierarchy': {'id': 'el_synth', 'children': []}},
    'dependencies': {'colors': [], 'typography': [], 'fonts': [], 'icons': [],
                     'variables': [], 'components': {},
                     'groups': [{'id': 'products', 'type': 'single_choice'}],
                     'products': [], 'media': [], 'consumes': ['products.selectedProduct'],
                     'producesInternally': [], 'navigateTargets': [],
                     'locales': [], 'defaultLocale': None},
}
_synthetic_path = os.path.join(TMP, 'synthetic-conditional.flow-snippet.json')
with open(_synthetic_path, 'w') as fh:
    json.dump(_synthetic_snippet, fh)

_rc, cpl = plan_json(QUIZ, _synthetic_path, QUIZ_S0)
new_gid = cpl['renames']['groups'].get('products')
case('ids: conditional test -- products group was renamed', bool(new_gid), True)
_cel = cpl['_payload']['map']['el_synth']
_cond_payload = _cel['interactions'][0]['actions'][0]['payload']
_pred_left = _cond_payload['cases'][0][0]['predicates'][0]['left']['variableId']
case('ids: predicate left.variableId head rewritten',
     _pred_left, f'{new_gid}.selectedProduct')
_case_purchase_vid = _cond_payload['cases'][0][1]['value'][0]['payload']['product']['variableId']
case("ids: variableId inside a case's executed action IS rewritten",
     _case_purchase_vid, f'{new_gid}.selectedProduct')
_default_purchase_vid = _cond_payload['default']['value'][0]['payload']['product']['variableId']
case("ids: variableId inside `default`'s executed action IS rewritten",
     _default_purchase_vid, f'{new_gid}.selectedProduct')

# --- Task 6: locales ------------------------------------------------------------
# Build a two-locale destination out of the quiz fixture: `en` plus `de`, where every
# localizable value has a German entry. The snippet is single-locale `en`.
dest2 = json.load(open(QUIZ))
dest2['locales'] = [{'id': 'en', 'code': 'en', 'name': 'English'},
                    {'id': 'de', 'code': 'de', 'name': 'German'}]
def add_de(o):
    if isinstance(o, dict):
        if o.get('_localizable') is True and isinstance(o.get('values'), dict) \
                and 'en' in o['values']:
            o['values']['de'] = o['values']['en']
        for v in o.values():
            add_de(v)
    elif isinstance(o, list):
        for v in o:
            add_de(v)
add_de(dest2)
DEST2 = os.path.join(TMP, 'quiz-en-de.json')
json.dump(dest2, open(DEST2, 'w'))

_rc, pl = plan_json(DEST2, p2, QUIZ_S0)
case('locales: de is reported as filled from the default', pl['locales']['filled'], ['de'])
case('locales: nothing dropped when the snippet has fewer', pl['locales']['dropped'], [])

# The fill must actually be in the payload, and must be a COPY -- an alias means
# editing one locale silently edits the other.
lv = []
def collect(o):
    if isinstance(o, dict):
        if o.get('_localizable') is True and isinstance(o.get('values'), dict):
            lv.append(o['values'])
        for v in o.values():
            collect(v)
    elif isinstance(o, list):
        for v in o:
            collect(v)
collect(pl['_payload'])
case('locales: every localizable value now carries de',
     all('de' in v for v in lv) if lv else None, True if lv else None)

# The subprocess assertion above cannot see object identity: `plan_json` parses
# `_payload` out of `json.loads(stdout)`, and JSON decoding always mints fresh
# objects regardless of what resolve_locales did -- so "the fill is a copy, not an
# alias" has to be checked IN-PROCESS, calling resolve_locales directly.
_snip_p2 = sn.read_snippet(p2)
_cfg_dest2 = sn.load(DEST2)
_payload_ip = json.loads(json.dumps(_snip_p2['payload']))
sn.resolve_locales(_snip_p2, _cfg_dest2, _payload_ip)

_lv_ip = []
def _collect_ip(o):
    if isinstance(o, dict):
        if o.get('_localizable') is True and isinstance(o.get('values'), dict):
            _lv_ip.append(o['values'])
        for v in o.values():
            _collect_ip(v)
    elif isinstance(o, list):
        for v in o:
            _collect_ip(v)
_collect_ip(_payload_ip)
case('locales (in-process): the fill is a copy, not an alias',
     all(v['de'] is not v['en'] for v in _lv_ip) if _lv_ip else None,
     True if _lv_ip else None)

# Invariant 11: after resolve_locales, every localizable `values` map carries
# EXACTLY the destination's declared locale set -- no more, no less.
_dest_locale_set = {l['id'] for l in _cfg_dest2['locales']}
case('locales (in-process): invariant 11 -- every values map matches the '
     'destination locale set exactly',
     all(set(v) == _dest_locale_set for v in _lv_ip) if _lv_ip else None,
     True if _lv_ip else None)

# The reverse: a two-locale snippet into a one-locale flow drops the extra.
p6, _s6, _ = extract(DEST2, '--element', first_el + '@' + QUIZ_S0, 'Bilingual block')
_rc, pl6 = plan_json(QUIZ, p6, QUIZ_S0)
case('locales: extra locale is dropped, not carried', pl6['locales']['dropped'], ['de'])

# --- Task 7: identity dependencies ----------------------------------------------
# The quiz paywall binds two products. Grafted onto a screen that declares none,
# each must surface as a blocker-level ask, never be silently declared.
PAY = json.load(open(QUIZ))['screens'][-1]['id']
pp, psnip, _ = extract(QUIZ, '--screen', PAY, 'Quiz paywall')
_rc, pl7 = plan_json(QUIZ, pp, QUIZ_S0)      # onto screen 0, which declares no products
prod_needs = [n for n in pl7['needs'] if 'product' in n['text']]
case('identity: undeclared products are reported', len(prod_needs) >= 1, True)
case('identity: product asks are blocker level',
     all(n['level'] == '!' for n in prod_needs), True)
# The information the dedup suppresses must not be LOST: the ask names the
# price-variable fallout explicitly, so the reader isn't left to guess it.
case('identity: an undeclared-product ask names the prod_price* fallout',
     all('prod_price*' in n['text'] for n in prod_needs), True)

# Fires, exactly: two products, both undeclared here -> exactly one ask each, and
# the fix's dedup means their `prod_price_per_month`/`prod_price_per_year`
# consumes must NOT also raise separate "no producer" asks for the same problem.
case('identity: exactly one ask per undeclared product, no more',
     len(prod_needs), 2)
case('identity: the total needs list is exactly the two product asks -- no '
     'per-price-variable duplicate for either product',
     len(pl7['needs']), 2)
case('identity: no "has no producer" ask survives for a product-relative price '
     'variable once its product is already asked about',
     any('has no producer' in n['text'] for n in pl7['needs']), False)

# A consumer with no producer: `name.value` is produced on the Quiz screen. Graft the
# paywall into `comparison`, where no text-input exists at all.
_rc, pl7b = plan_json(COMP, pp, COMP_S0)
case('identity: a stranded variable is reported',
     any('name.value' in n['text'] for n in pl7b['needs']), True)

# Cross-app rebinding through a catalog file.
CAT = os.path.join(TMP, 'catalog.json')
src_products = [p['id'] for p in json.load(open(pp))['dependencies']['products']]
json.dump([{'id': 'dest-uuid-1', 'title': 'Annual',
            'vendor_products': {'app_store': {'product_id': 'com.x.annual'}}}],
          open(CAT, 'w'))
# Re-extract with the SAME store id so a match exists.
case('identity: a catalog with no matching store id does not invent a rebind',
     plan_json(COMP, pp, COMP_S0, extra=('--catalog', CAT))[1]['rebinds'], {})

# A genuine positive match: extract with `--scope any-app` and an extract-time
# catalog naming the source products' store ids, then plan against a destination
# catalog that names the SAME store ids under different destination UUIDs. This is
# the only case in the suite that actually exercises the match arithmetic rather
# than falling through the scope check.
EXTRACT_CAT = os.path.join(TMP, 'extract-catalog.json')
json.dump([{'id': sp, 'vendor_products': {'app_store': {'product_id': f'com.x.{i}'}}}
           for i, sp in enumerate(src_products)],
          open(EXTRACT_CAT, 'w'))
pp_any, _s_any, _ = extract(QUIZ, '--screen', PAY, 'Quiz paywall any-app',
                             extra=('--scope', 'any-app', '--catalog', EXTRACT_CAT))
DEST_CAT = os.path.join(TMP, 'dest-catalog.json')
json.dump([{'id': f'dest-uuid-{i}', 'vendor_products':
            {'app_store': {'product_id': f'com.x.{i}'}}}
           for i in range(len(src_products))],
          open(DEST_CAT, 'w'))
_rc, pl7d = plan_json(COMP, pp_any, COMP_S0, extra=('--catalog', DEST_CAT))
case('identity: a matching store id rebinds to the destination catalog uuid',
     pl7d['rebinds'], {sp: f'dest-uuid-{i}' for i, sp in enumerate(src_products)})
case('identity: a successful any-app rebind raises no product ask',
     [n for n in pl7d['needs'] if 'product' in n['text']], [])

# `any-app` with NO catalog given at all: no match is possible, so every product
# is stripped and named as an ask -- never silently kept.
_rc, pl7e = plan_json(COMP, pp_any, COMP_S0)
case('identity: any-app with no --catalog strips every product and asks',
     len([n for n in pl7e['needs'] if 'product' in n['text']]), len(src_products))
case('identity: any-app with no --catalog invents no rebind', pl7e['rebinds'], {})
case('identity: a stripped-binding ask also names the prod_price* fallout',
     all('prod_price*' in n['text'] for n in pl7e['needs']
         if 'product' in n['text']), True)

# --- Task 7 fix: a malformed `--catalog` degrades instead of crashing ----------
# A catalog is user-supplied input to a shipped script. Well-formed JSON of the
# WRONG SHAPE must behave exactly like no catalog at all: strip the binding, ask,
# never raise. Each of these previously crashed with an AttributeError inside
# `store_ids` before the container/row validation was added.
BAD_CAT_STRING = os.path.join(TMP, 'catalog-bad-string.json')
json.dump("not-a-list", open(BAD_CAT_STRING, 'w'))
_rc, pl_bad1 = plan_json(COMP, pp_any, COMP_S0, extra=('--catalog', BAD_CAT_STRING))
case('identity: a bare JSON string catalog does not crash', _rc in (0, 1), True)
case('identity: a bare JSON string catalog invents no rebind', pl_bad1['rebinds'], {})
case('identity: a bare JSON string catalog still asks for every product',
     len([n for n in pl_bad1['needs'] if 'product' in n['text']]), len(src_products))

BAD_CAT_SCALARS = os.path.join(TMP, 'catalog-bad-scalars.json')
json.dump([1, 2, 'three'], open(BAD_CAT_SCALARS, 'w'))
_rc, pl_bad2 = plan_json(COMP, pp_any, COMP_S0, extra=('--catalog', BAD_CAT_SCALARS))
case('identity: a list-of-scalars catalog does not crash', _rc in (0, 1), True)
case('identity: a list-of-scalars catalog invents no rebind', pl_bad2['rebinds'], {})

BAD_CAT_DICT = os.path.join(TMP, 'catalog-bad-dict.json')
json.dump({'meta': 'no usable list here'}, open(BAD_CAT_DICT, 'w'))
_rc, pl_bad3 = plan_json(COMP, pp_any, COMP_S0, extra=('--catalog', BAD_CAT_DICT))
case('identity: a dict catalog with no usable list does not crash', _rc in (0, 1), True)
case('identity: a dict catalog with no usable list invents no rebind',
     pl_bad3['rebinds'], {})

BAD_CAT_EMPTY = os.path.join(TMP, 'catalog-empty.json')
json.dump([], open(BAD_CAT_EMPTY, 'w'))
_rc, pl_bad4 = plan_json(COMP, pp_any, COMP_S0, extra=('--catalog', BAD_CAT_EMPTY))
case('identity: an empty-list catalog does not crash', _rc in (0, 1), True)
case('identity: an empty-list catalog invents no rebind', pl_bad4['rebinds'], {})

# Partly malformed: one usable dict row plus one garbage entry -- the good row
# must still rebind rather than the whole catalog being discarded.
MIXED_CAT = os.path.join(TMP, 'catalog-mixed.json')
json.dump([{'id': 'dest-uuid-0',
            'vendor_products': {'app_store': {'product_id': 'com.x.0'}}},
           'a-garbage-string-row'],
          open(MIXED_CAT, 'w'))
_rc, pl_mixed = plan_json(COMP, pp_any, COMP_S0, extra=('--catalog', MIXED_CAT))
case('identity: a partly malformed catalog still rebinds the usable row',
     pl_mixed['rebinds'], {src_products[0]: 'dest-uuid-0'})
case('identity: a partly malformed catalog still asks for the row it could not '
     'match', len([n for n in pl_mixed['needs'] if 'product' in n['text']]), 1)

# Grafting a screen back into the SAME flow, onto the very screen that already
# declares both products, must raise NO needs at all -- the positive control for
# the undeclared-products case above, and the case that pinned the fix: a
# product's own `prod_price_per_month`/`prod_price_per_year` consumes must be
# satisfied by that product's declaration, never separately flagged as
# "no producer" once the product itself is correctly declared here.
rc_control, pl7c = plan_json(QUIZ, pp, PAY)
prod_needs_same = [n for n in pl7c['needs'] if 'is not declared on this screen' in n['text']]
case('identity: a screen grafted onto its own declaring screen has no product ask',
     prod_needs_same, [])
case('identity: a declared product\'s own price variables raise zero '
     '"has no producer" asks', [n for n in pl7c['needs']
                                if 'has no producer' in n['text']], [])
case('identity: plan exits 0 when the destination already declares everything',
     rc_control, 0)
case('identity: needs is exactly empty for a screen grafted onto its own '
     'declaring screen', pl7c['needs'], [])

# `p2` (Task 3's one-element snippet) has no products, no consumed variables and no
# navigate targets -- an independent, simpler zero-needs case.
rc_zero, pl7z = plan_json(QUIZ, p2, QUIZ_S0)
case('identity: plan exits 0 when needs is genuinely empty', rc_zero, 0)
case('identity: a needs-free plan reports an empty needs list', pl7z['needs'], [])

# Exit code: `needs` non-empty is a disclosure obligation, not a defect.
rc_undeclared, _pl7 = plan_json(QUIZ, pp, QUIZ_S0)
case('identity: plan exits 1 when a product ask is present', rc_undeclared, 1)

# `resolve_identity` never writes `_meta.screens` -- confirm the destination config
# on disk is untouched by a plan run that raised product asks.
_before = open(QUIZ).read()
plan_json(QUIZ, pp, QUIZ_S0)
case('identity: resolve_identity never mutates the config file on disk',
     open(QUIZ).read() == _before, True)

# Navigate targets: `p` (Quiz screen 0, extracted earlier for Task 3) navigates to
# `scr_oAPBHPa7`, which does not exist in `comparison` -- a stranded target, kept
# as-is rather than repointed.
_rc, pl7f = plan_json(COMP, p, COMP_S0)
nav_needs = [n for n in pl7f['needs'] if 'navigate target' in n['text']]
case('identity: a navigate target missing in the destination is reported',
     any('scr_oAPBHPa7' in n['text'] for n in nav_needs), True)
case('identity: navigate asks are blocker level',
     all(n['level'] == '!' for n in nav_needs), True)
# The payload itself is untouched -- inventing a destination is explicitly forbidden.
_nav_action = None
for e in pl7f['_payload']['screen']['elements']['map'].values():
    for ix in e.get('interactions') or []:
        for act in ix.get('actions') or []:
            if act.get('type') == 'navigate':
                _nav_action = act
case('identity: a stranded navigate target is left pointing at the original screen',
     (_nav_action or {}).get('payload', {}).get('screen'), 'scr_oAPBHPa7')

# The same screen grafted back into its OWN flow finds the target trivially (same
# config) -- the positive control for the stranded-navigate case above. Reuses
# `pl3` (Task 4: `plan_json(QUIZ, p, QUIZ_S0)`), the identical call.
case('identity: a navigate target present in the destination raises no ask',
     [n for n in pl3['needs'] if 'navigate target' in n['text']], [])

# The Task 7 fix ties a `<uuid>.prod_*` consume's head to `dep['products']`, never
# to `_producers_in`'s group handling -- so a `<groupId>.selectedProduct` consume
# (invariant 5's OTHER form, head is a selectable GROUP, never a product uuid)
# must still resolve exactly as it did before this fix: via `selectableGroups` on
# the destination, unaffected by whether any product is declared anywhere. Built
# in-process against minimal synthetic structures so this is independent of
# whichever fixture happens to declare a `products` group where.
_grp_dep = {'products': [], 'consumes': ['grp_x.selectedProduct'],
            'producesInternally': [], 'navigateTargets': [], 'media': []}
_grp_snip = {'dependencies': _grp_dep, 'intendedScope': 'same-app'}
_cfg_no_group = {'screens': [{'id': 'scr1', 'elements': {'map': {}},
                              'selectableGroups': []}],
                  '_meta': {'screens': {}}}
_res_nogroup = sn.resolve_identity(_grp_snip, _cfg_no_group, 'scr1', None)
case('identity (in-process): a group-path consume with no matching '
     'selectableGroup still asks',
     any('grp_x.selectedProduct' in n['text'] for n in _res_nogroup['needs']), True)

_cfg_with_group = {'screens': [{'id': 'scr1', 'elements': {'map': {}},
                                'selectableGroups': [{'id': 'grp_x',
                                                      'type': 'product'}]}],
                    '_meta': {'screens': {}}}
_res_withgroup = sn.resolve_identity(_grp_snip, _cfg_with_group, 'scr1', None)
case('identity (in-process): a group-path consume resolved via '
     'selectableGroups, not the product-declaration path, raises no ask',
     _res_withgroup['needs'], [])

# The placeholder-media ask is untested elsewhere: `?` level, never `!` -- it is an
# optional cleanup, not a publish blocker.
_media_snip = {'dependencies': {'products': [], 'consumes': [],
                                'producesInternally': [], 'navigateTargets': [],
                                'media': ['https://example.invalid/PLACEHOLDER.png']},
               'intendedScope': 'same-app'}
_cfg_min = {'screens': [{'id': 'scr1', 'elements': {'map': {}},
                         'selectableGroups': []}], '_meta': {'screens': {}}}
_res_media = sn.resolve_identity(_media_snip, _cfg_min, 'scr1', None)
case('identity (in-process): a placeholder asset raises exactly one ask',
     len(_res_media['needs']), 1)
case('identity (in-process): a placeholder asset asks at "?" level, not "!"',
     _res_media['needs'][0]['level'], '?')

# --- Task 8: the plan report ----------------------------------------------------
rc, out, _e = run('plan', '--config', QUIZ, '--snippet', p2, '--screen', QUIZ_S0)
case('plan: header names the snippet and the screen',
     out.startswith('GRAFT PLAN'), True)
case('plan: a clean plan exits 0', rc, 0)

rc2, out2, _e = run('plan', '--config', COMP, '--snippet', pp, '--screen', COMP_S0)
case('plan: a plan with asks exits 1', rc2, 1)
case('plan: asks appear under NEEDS YOU', 'NEEDS YOU' in out2, True)

# Review finding 1, round 2: `WILL ADOPT` must label the two sides ("here" /
# "snippet") on their own line(s) for a preset, with NO `<-`/arrow anywhere, and a
# field absent on one side must simply not appear there -- no `<-?` marker, which
# is what collided with the arrow notation in round 1. The test has to pin the
# actual rendered substrings on the actual lines, or a regression back to either
# the round-1 arrow form or the original generic message still passes.
_lines2 = out2.splitlines()

def _adopt_preset_block(lines, preset_id):
    i = next((i for i, l in enumerate(lines)
              if l.startswith('WILL ADOPT') and f'font.preset {preset_id}' in l), None)
    assert i is not None, f'no WILL ADOPT block for preset {preset_id!r} -- ' \
        'fixture pair no longer adopts it, pick another'
    return lines[i], lines[i + 1], lines[i + 2]

# `body`: differs in size, weight AND lineHeight -- exercises the ordinary case.
_dest_body = next(t for t in json.load(open(COMP))['theme']['typography']
                  if t['id'] == 'body')['settings']
_snip_body = next(t for t in json.load(open(QUIZ))['theme']['typography']
                  if t['id'] == 'body')['settings']
_body_hdr, _body_here, _body_snip = _adopt_preset_block(_lines2, 'body')
case('plan: WILL ADOPT (body) here-line is labelled "here" and shows the '
     'DESTINATION size/weight',
     _body_here.strip().startswith('here')
     and f'{_dest_body["size"]}/{_dest_body["weight"]}' in _body_here, True)
case('plan: WILL ADOPT (body) snippet-line is labelled "snippet" and shows the '
     'SNIPPET size/weight',
     _body_snip.strip().startswith('snippet')
     and f'{_snip_body["size"]}/{_snip_body["weight"]}' in _body_snip, True)
case('plan: WILL ADOPT (body) here-line carries the lineHeight the destination has',
     f'lineHeight {_dest_body["lineHeight"]}' in _body_here, True)
case('plan: WILL ADOPT (body) snippet-line carries NO lineHeight (the snippet has none)',
     'lineHeight' in _body_snip, False)

# `caption`: THE round-2 regression case -- identical size/weight on both sides,
# and the ONLY real difference (destination has lineHeight 16, snippet has none)
# was buried inside a mangled `lh 16<-?` token in round 1. This is the assertion
# that would have caught that defect.
_dest_caption = next(t for t in json.load(open(COMP))['theme']['typography']
                     if t['id'] == 'caption')['settings']
_snip_caption = next(t for t in json.load(open(QUIZ))['theme']['typography']
                     if t['id'] == 'caption')['settings']
assert _dest_caption.get('lineHeight') is not None and _snip_caption.get('lineHeight') is None, \
    'fixture no longer has this shape (dest has lineHeight, snippet does not) -- pick another'
_cap_hdr, _cap_here, _cap_snip = _adopt_preset_block(_lines2, 'caption')
case('plan: WILL ADOPT (caption) here-line shows the SAME size/weight as snippet '
     '-- not itself the difference',
     f'{_dest_caption["size"]}/{_dest_caption["weight"]}' in _cap_here
     and f'{_snip_caption["size"]}/{_snip_caption["weight"]}' in _cap_snip, True)
case('plan: WILL ADOPT (caption) here-line carries lineHeight 16 -- the actual difference',
     f'lineHeight {_dest_caption["lineHeight"]}' in _cap_here, True)
case('plan: WILL ADOPT (caption) snippet-line carries NO lineHeight at all '
     '(round-2 regression check)',
     'lineHeight' in _cap_snip, False)

# No arrow / absence-marker collision anywhere in the report -- the round-1 defect
# named directly: `render_plan` uses `->`/`<-` nowhere in this feature.
case('plan: no left-arrow character anywhere in the report', '←' in out2, False)
case('plan: no ASCII left-arrow anywhere in the report', '<-' in out2, False)

# A colorId adopt, checked separately (`p` into `comparison` adopts `accent`,
# never exercised by the `pp` pair above): one line, both sides labelled, no arrow.
_rc_color, out_color, _e = run('plan', '--config', COMP, '--snippet', p, '--screen', COMP_S0)
_dest_accent = next(c for c in json.load(open(COMP))['theme']['colors'] if c['id'] == 'accent')
_snip_accent = next(c for c in json.load(open(QUIZ))['theme']['colors'] if c['id'] == 'accent')
_accent_line = next((l for l in out_color.splitlines() if 'colorId accent' in l), '')
case('plan: WILL ADOPT (colorId accent) is one line labelled here/snippet, no arrow',
     'here' in _accent_line and 'snippet' in _accent_line and '←' not in _accent_line,
     True)
case('plan: WILL ADOPT (colorId accent) here shows the destination hex',
     _dest_accent['light']['hex'] in _accent_line, True)
_snip_accent_repr = _snip_accent['light']['hex'] + (
    ' / ' + _snip_accent['dark']['hex'] if 'dark' in _snip_accent else '')
case('plan: WILL ADOPT (colorId accent) snippet shows the snippet hex, dark variant included',
     _snip_accent_repr in _accent_line, True)

before = open(COMP).read()
run('plan', '--config', COMP, '--snippet', pp, '--screen', COMP_S0)
case('plan: destination file is byte-identical afterwards', open(COMP).read(), before)

# The snippet file gets the same guarantee -- `plan` reads it, never writes it.
before_snip = open(pp).read()
run('plan', '--config', COMP, '--snippet', pp, '--screen', COMP_S0)
case('plan: snippet file is byte-identical afterwards', open(pp).read(), before_snip)

# `--json` still carries `_payload` (the suite's only window onto the rewriter) and
# the new `adds`/`placement` keys build_plan adds, without breaking any Task 4-7
# assertion keyed on the dict's other fields.
_rcj, plj = plan_json(QUIZ, p2, QUIZ_S0)
case('plan --json: adds.elements matches the (possibly renamed) payload map keys',
     set(plj['adds']['elements']), set(plj['_payload']['map']))
case('plan --json: placement records screen/parent/index',
     plj['placement'], {'screen': QUIZ_S0, 'parent': None, 'index': None})

# The exact phrase a reader keys off of: NEEDS YOU lines are `  <level> <text>`.
_needs_lines = [l for l in out2.splitlines() if l.startswith('  !') or l.startswith('  ?')]
case('plan: every reported need appears as its own NEEDS YOU line',
     len(_needs_lines), len(plan_json(COMP, pp, COMP_S0)[1]['needs']))

# One line per RECOGNISABLE thing, not one line per element: a WILL ADD summary
# line, never a per-element listing, however many elements the paywall carries.
_will_add_lines = [l for l in out2.splitlines() if l.startswith('WILL ADD')]
case('plan: exactly one WILL ADD line regardless of element count',
     len(_will_add_lines), 1)
_pp_elcount = len(json.load(open(pp))['payload']['screen']['elements']['map'])
assert _pp_elcount > 1, 'fixture no longer has multiple elements -- pick a bigger one'
case('plan: the WILL ADD line names the actual element count',
     f'{_pp_elcount} elements' in _will_add_lines[0], True)

# Review finding 4: a carried/added GROUP's `type` must ride along -- `products`
# is a `product`-typed group declared on the quiz paywall screen, and a reader
# needs to know that (a `product` group and a `single_choice` group behave
# differently), not just that some group is being added.
_pp_group_types = {g['id']: g['type']
                   for g in json.load(open(pp))['dependencies']['groups']}
assert _pp_group_types.get('products') == 'product', \
    'fixture no longer declares products as a product-typed group -- pick another'
case('plan: WILL ADD names the group TYPE, not just its id',
     'group `products` (product)' in _will_add_lines[0], True)

# `build_plan` must not mutate the snippet dict it was handed -- checked in-process,
# since a subprocess round-trip through JSON would mint fresh objects either way and
# could not tell a real deep copy from a bug that skipped it.
_snip_ip = sn.read_snippet(p2)
_snip_ip_before = json.dumps(_snip_ip, sort_keys=True)
_cfg_ip = sn.load(QUIZ)
sn.build_plan(_snip_ip, _cfg_ip, QUIZ_S0, None, None, None)
case('build_plan (in-process): the snippet dict handed in is not mutated',
     json.dumps(_snip_ip, sort_keys=True), _snip_ip_before)

# Review finding 3: a `theme`-kind snippet takes no `--screen` -- it targets the
# flow, not a screen -- so the header must say that rather than rendering the
# placeholder `screen "None" (None)` a lookup-by-None produces. `p4` is Task 4's
# theme-kind snippet extracted from comparison.
_rc_theme, out_theme, _e = run('plan', '--config', COMP, '--snippet', p4, '--json')
_ = _rc_theme  # a theme-kind plan may legitimately carry needs; only the header is scoped here
_rc_theme2, out_theme2, _e = run('plan', '--config', COMP, '--snippet', p4)
_theme_header = out_theme2.splitlines()[0]
case('plan: a theme-kind plan header names the flow instead of a screen clause',
     _theme_header, f'GRAFT PLAN — {os.path.basename(p4)} → flow-wide theme (no screen)')
case('plan: a theme-kind plan header never renders the None placeholder',
     'None' in _theme_header, False)

# `graft` shares every flag with `plan` and, since Task 9, prints the same report
# THEN writes `--out` and exits per `pl['needs']` (1 if any, else 0) -- exit 1 here
# is a disclosure obligation, not a failed write.
_graft_out = os.path.join(TMP, 'graft-flags-check.json')
rc_g, out_g, _e = run('graft', '--config', QUIZ, '--snippet', p2, '--screen', QUIZ_S0,
                      '--out', _graft_out)
_, _pl_flags = plan_json(QUIZ, p2, QUIZ_S0)
case('graft: still prints the plan report (shared flags wired)',
     out_g.startswith('GRAFT PLAN'), True)
case('graft: exit code mirrors needs (1 if any, else 0), never the old exit 2',
     rc_g, 1 if _pl_flags['needs'] else 0)
case('graft: --out is actually written',
     os.path.exists(_graft_out), True)
case('graft: prints where it wrote and what to run next',
     'wrote:' in out_g and 'verify-config.py' in out_g, True)

# --- Task 9: graft and the oracle matrix ----------------------------------------
def graft(dest, snip_path, screen, tag, extra=()):
    out = os.path.join(TMP, f'grafted-{tag}.json')
    rc, so, se = run('graft', '--config', dest, '--snippet', snip_path,
                     '--screen', screen, '--out', out, *extra)
    assert os.path.exists(out), f'graft wrote nothing (rc={rc}): {se}'
    v = subprocess.run([sys.executable, VERIFY, out], capture_output=True, text=True)
    return out, rc, v.returncode, v.stdout


def graft_checked(dest, snip_path, screen, tag, extra=()):
    """Like `graft`, but ALSO captures the plan's `needs` (via `--json`, so we read
    the structured list rather than scraping the NEEDS YOU report text) alongside
    the written file and the checker's verdict."""
    out = os.path.join(TMP, f'grafted-{tag}.json')
    rc, so, se = run('graft', '--config', dest, '--snippet', snip_path,
                     '--screen', screen, '--out', out, '--json', *extra)
    assert os.path.exists(out), f'graft wrote nothing (rc={rc}): {se}'
    needs = json.loads(so.splitlines()[0])['needs']
    v = subprocess.run([sys.executable, VERIFY, out], capture_output=True, text=True)
    return out, rc, needs, v.returncode, v.stdout


# An identifier a verify-config.py ERROR and a plan `need` can share: a prefixed id
# (scr_/el_/clr_/int_/act_/typ_/pb_/g_...) or a bare UUID. Deliberately loose --
# false NEGATIVES (an id form neither pattern catches) fail a row closed, which is
# the safe direction for an oracle; false positives would need two unrelated
# defects to coin the exact same id string, which is not a realistic collision.
ID_RE = re.compile(
    r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'
    r'|\b[a-zA-Z]{1,5}_[A-Za-z0-9]+\b')


def error_lines(verify_stdout):
    return [l.strip() for l in verify_stdout.splitlines() if 'ERROR:' in l]


def undisclosed_errors(needs, verify_stdout):
    """THE ORACLE PROPERTY: a graft is verify-clean, OR every remaining
    `verify-config.py` ERROR corresponds to a defect the plan already disclosed in
    `NEEDS YOU` -- never a defect that snuck through unannounced. Returns the ERROR
    lines that have NO matching disclosure (the ones that fail a row); an ERROR
    with no extractable id at all is treated as undisclosed, never waved through."""
    need_text = ' '.join(n['text'] for n in needs)
    orphans = []
    for line in error_lines(verify_stdout):
        ids = ID_RE.findall(line)
        if ids and any(i in need_text for i in ids):
            continue
        orphans.append(line)
    return orphans


for tag, dest, snip, screen in (
        ('quiz-into-comp', COMP, p, COMP_S0),
        ('comp-into-quiz', QUIZ, p3, QUIZ_S0),
        ('quiz-into-self', QUIZ, p2, QUIZ_S0),
        ('theme-into-quiz', QUIZ, p4, QUIZ_S0),
        ('paywall-into-comp', COMP, pp, COMP_S0),
        ('tabs-into-self', TABS, tp, TABS_S0),
        ('locale-fill', DEST2, p2, QUIZ_S0),
        ('paywall-into-quiz-s0', QUIZ, pp, QUIZ_S0)):
    _o, _rc, _needs, vrc, vout = graft_checked(dest, snip, screen, tag)
    errs = error_lines(vout)
    orphans = undisclosed_errors(_needs, vout)
    if orphans:
        print(f'    orphan (undisclosed) ERROR(s) for {tag}: {orphans}')
    case(f'oracle: {tag} introduces no undisclosed breakage (orphan ERROR count)',
         len(orphans), 0)
    # `quiz-into-comp` is the row that actually exercises the disclosed-error path:
    # `p` carries a `navigate` to `scr_oAPBHPa7`, a sibling QUIZ screen this graft
    # does not bring along (locked in by Task 7, line ~607). verify-config.py
    # reports exactly that one ERROR, and the plan's own NEEDS YOU list names the
    # same screen id -- covered, not clean, and the oracle says so precisely.
    if tag == 'quiz-into-comp':
        case('oracle: quiz-into-comp has exactly one (disclosed) verify-config ERROR',
             len(errs), 1)
        case("oracle: quiz-into-comp's ERROR names the left-as-is target scr_oAPBHPa7",
             'scr_oAPBHPa7' in errs[0], True)

# --- Coordinator review, Finding 1 (Critical) + Finding 4 (Critical) ---------
# A cross-app SCREEN graft must rebind product ids in the WRITTEN file, not just
# promise to in the plan report (Finding 1), AND the price variables bound to
# those products must move with them (Finding 4) -- otherwise the card binds the
# right product while its price renders empty, this repo's plain-text-prices
# failure class. `pp_any` (extracted `--scope any-app` against `EXTRACT_CAT`,
# defined above) carries 2 source product uuids; `DEST_CAT` rebinds both to
# `dest-uuid-0`/`dest-uuid-1` by matching store id -- this is exactly the `screen`
# kind Finding 1's bug hid in, and exactly the rebind Finding 4's price variables
# ride along with.
def product_ids_in(o):
    """Every id at `product.id` anywhere in `o` -- a prop-bound `product` element
    AND a purchase action's `payload.product.id`, the same two paths `apply_plan`
    rebinds. Path-keyed reader matching the path-keyed writer -- NOT a value-keyed
    'any dict with a matching id' scan, the same discipline the fix itself keeps."""
    ids = []
    sn.walk(o, lambda d: ids.append(d['product']['id'])
            if isinstance(d.get('product'), dict)
            and isinstance(d['product'].get('id'), str) else None)
    return ids

def variable_ids_in(o):
    """Every `variableId` string anywhere in `o`, field-name-keyed like the writer
    (`_fix_variable_id` in `rewrite_ids`, and Finding 4's `rebind` closure) --
    never a value-keyed scan."""
    ids = []
    sn.walk(o, lambda d: ids.append(d['variableId'])
            if isinstance(d.get('variableId'), str) else None)
    return ids

def price_variable_heads(o):
    """The HEAD segment of every price-variable-form `variableId` in `o` -- the
    product-relative `<productUUID>.prod_*` form only (flow-schema.md invariant
    5), never the group-relative `<groupId>.selectedProduct.<field>` form, which
    is excluded by name (`.selectedProduct.` substring) rather than by shape,
    matching how `verify-config.py` itself tells the two forms apart."""
    return {v.split('.')[0] for v in variable_ids_in(o)
            if '.prod_' in v and '.selectedProduct.' not in v}

_rc_xa, pl_xa = plan_json(COMP, pp_any, COMP_S0, extra=('--catalog', DEST_CAT))
assert pl_xa['rebinds'], 'fixture stopped rebinding -- pick a catalog pair that matches'
_expect_dest_uuids = set(pl_xa['rebinds'].values())
_expect_src_uuids = set(pl_xa['rebinds'].keys())
_expect_group_rename = pl_xa['renames']['groups'].get('products', 'products')

o_xa, _rc_xa2, needs_xa, vrc_xa, vout_xa = graft_checked(
    COMP, pp_any, COMP_S0, 'cross-app-screen', extra=('--catalog', DEST_CAT))
gxa = json.load(open(o_xa))
# A `screen`-kind graft INSERTS a whole new screen -- it does not merge into
# `COMP_S0` -- so look up the freshly-inserted screen by the id the plan itself
# names (`_payload.screen.id`, post-rename), not by the destination screen the
# graft was anchored on.
_xa_screen_id = pl_xa['_payload']['screen']['id']
scr_xa = next(s for s in gxa['screens'] if s['id'] == _xa_screen_id)
written_ids_xa = set(product_ids_in(scr_xa))
case('graft: cross-app SCREEN rebind writes EXACTLY the destination product uuids',
     written_ids_xa, _expect_dest_uuids)
case('graft: cross-app SCREEN rebind leaves NO source-app product uuid behind',
     written_ids_xa & _expect_src_uuids, set())

# Finding 4: price-variable heads move WITH the product they price.
_price_heads_xa = price_variable_heads(scr_xa)
case('graft: every price-variable head is EXACTLY a destination product uuid',
     _price_heads_xa, _expect_dest_uuids)
case('graft: no price-variable head still names a source-app product uuid',
     _price_heads_xa & _expect_src_uuids, set())

# The other two variable forms are untouched by a product rebind: a
# `<groupId>.selectedProduct` head is a (possibly RENAMED) group id, never a
# product uuid, and a `<customId>.value` head is a text-input custom id. Both
# survive unrewritten -- `rebinds` contains only product uuids, so neither head
# is ever found in it.
_all_vids_xa = set(variable_ids_in(scr_xa))
case('graft: the group-relative selectedProduct variable is untouched by the '
     'product rebind', f'{_expect_group_rename}.selectedProduct' in _all_vids_xa, True)
case('graft: the text-input customId variable is untouched by the product rebind',
     'name.value' in _all_vids_xa, True)

# Finding 4 tightens this row from "clean OR every remaining ERROR is disclosed"
# to actually verify-clean: once price-variable heads move with their product,
# `verify-config.py`'s "price variable references a product bound nowhere" class
# has nothing left to report on this graft.
case('oracle: cross-app-screen is now fully verify-clean (0 ERRORs, not merely '
     '0 undisclosed)', error_lines(vout_xa), [])
_orphans_xa = undisclosed_errors(needs_xa, vout_xa)
case('oracle: cross-app-screen introduces no undisclosed breakage (orphan ERROR '
     'count)', len(_orphans_xa), 0)

# --- Coordinator review, Finding 2 (Important) --------------------------------
# The element-group-carry loop (`snippet.py:905-909`) was provably untested: both
# `--element` extractions in this suite (`p2`, `p6`) target an image with no
# `groupId`, so `dependencies.groups` is empty on every graft call that used them,
# and disabling the loop body left 153/153 green. `el_8rfwhBiXQL` on the Quiz
# paywall screen IS a `product`-typed group member -- extract and graft it into
# TABS, whose only declared group is `tabs` (`single_choice`), so `products`
# lands with NO id collision and the assertion stays about the carry, not renames.
pcard, _pcard_snip, _ = extract(QUIZ, '--element', 'el_8rfwhBiXQL@' + PAY, 'Plan card')
_pcard_groups = json.load(open(pcard))['dependencies']['groups']
assert (_pcard_groups and _pcard_groups[0]['id'] == 'products'
        and _pcard_groups[0]['type'] == 'product'), (
    'fixture no longer declares el_8rfwhBiXQL as a product-group member -- pick another')

o_gc, _rc_gc, needs_gc, vrc_gc, vout_gc = graft_checked(
    TABS, pcard, TABS_S0, 'group-carry-product-card')
orphans_gc = undisclosed_errors(needs_gc, vout_gc)
if orphans_gc:
    print(f'    orphan (undisclosed) ERROR(s) for group-carry-product-card: {orphans_gc}')
case('oracle: group-carry-product-card introduces no undisclosed breakage '
     '(orphan ERROR count)', len(orphans_gc), 0)
ggc = json.load(open(o_gc))
scr_gc = next(s for s in ggc['screens'] if s['id'] == TABS_S0)
_dest_groups = {g['id']: g for g in scr_gc.get('selectableGroups') or []}
case('graft: the carried group landed on the destination screen',
     'products' in _dest_groups, True)
case('graft: the carried group kept its TYPE (`product`)',
     _dest_groups.get('products', {}).get('type'), 'product')
case('graft: the destination flow\'s own pre-existing group (`tabs`) survived '
     'untouched', 'tabs' in _dest_groups and _dest_groups['tabs']['type'], 'single_choice')

# --- Coordinator review, Finding 3 (Minor) ------------------------------------
# The CLI-level "graft: never writes over the source config" test above only
# proves the destination FILE on disk was not overwritten; it says nothing about
# whether `apply_plan` mutated the in-memory `config` dict it was handed. Checked
# in-process, same reasoning as `build_plan`'s in-process test above: a subprocess
# round trip through JSON mints fresh objects either way and cannot distinguish a
# real deep copy from a bug that skipped it.
_cfg_ip3 = sn.load(COMP)
_cfg_ip3_before = json.dumps(_cfg_ip3, sort_keys=True)
_snip_ip3 = sn.read_snippet(p)
_pl_ip3 = sn.build_plan(_snip_ip3, _cfg_ip3, COMP_S0, None, None, None)
_out_ip3 = sn.apply_plan(_cfg_ip3, _snip_ip3, _pl_ip3)
case('apply_plan (in-process): the config dict handed in is not mutated',
     json.dumps(_cfg_ip3, sort_keys=True), _cfg_ip3_before)
case('apply_plan (in-process): a genuinely NEW object with real changes is returned',
     _out_ip3 is not _cfg_ip3 and json.dumps(_out_ip3, sort_keys=True) != _cfg_ip3_before,
     True)

# `_meta.screens` is builder-owned: a graft must never mint a flowProductId.
g7 = json.load(open(os.path.join(TMP, 'grafted-paywall-into-quiz-s0.json')))
case('graft: no flowProductId was minted on the destination screen',
     'flowProductId' in json.dumps((g7.get('_meta') or {}).get('screens', {})
                                   .get(QUIZ_S0, {})), False)

# The destination file itself is never touched.
before9 = open(COMP).read()
graft(COMP, p, COMP_S0, 'immutability')
case('graft: never writes over the source config', open(COMP).read(), before9)

# Carried definitions actually landed. `pp` (the "Quiz paywall" screen) is the
# snippet that actually depends on `h3` -- `p` ("Quiz welcome") does not, so this
# uses the same snip/dest pair as the `paywall-into-comp` oracle row above.
o, _rc, _v, _s = graft(COMP, pp, COMP_S0, 'carry-check')
gc = json.load(open(o))
case('graft: h3 landed in the destination theme',
     'h3' in {t['id'] for t in gc['theme']['typography']}, True)
case('graft: adopted ids were NOT duplicated',
     len({t['id'] for t in gc['theme']['typography']}) == len(gc['theme']['typography']),
     True)
case('graft: schemaVersion is unchanged',
     gc['schemaVersion'], json.load(open(COMP))['schemaVersion'])
case('graft: no top-level status or id was introduced',
     'status' in gc, 'status' in json.load(open(COMP)))

# --- Task 10 review fix: --at removed, --screen scoped to `element`, and `plan`
# validates the destination screen exactly like `graft` -------------------------

# `--at` was a documented but dead flag: `build_plan`/`apply_plan` only ever read
# `--index`, so `--at N` silently did nothing and the user believed it worked. A
# flag a shipped CLI accepts and ignores is worse than no flag -- removing it must
# make the CLI REJECT it outright, not merely fail to act on it.
rc_at_p, _o, e_at_p = run('plan', '--config', COMP, '--snippet', p4, '--at', '0')
case('plan: --at is rejected (removed, not silently accepted)', rc_at_p, 2)
case('plan: --at rejection names the flag as unrecognized',
     'unrecognized arguments' in e_at_p and '--at' in e_at_p, True)
_graft_at_out = os.path.join(TMP, 'graft-at-check.json')
rc_at_g, _o, e_at_g = run('graft', '--config', COMP, '--snippet', p4,
                          '--at', '0', '--out', _graft_at_out)
case('graft: --at is rejected (removed, not silently accepted)', rc_at_g, 2)
case('graft: --at rejection never writes --out', os.path.exists(_graft_at_out), False)

# A `component` snippet lands in top-level `components`; a `theme` snippet touches
# neither a screen nor `screens[]`. Neither needs a destination screen to resolve,
# so `--screen` must not be required for either -- only `element` attaches to one.
p_comp, s_comp, _ = extract(QUIZ, '--component', 'pb_dl05vuVs', 'Header component')
case('extract: kind is component', s_comp['kind'], 'component')

rc_comp_p, out_comp_p, e_comp_p = run('plan', '--config', COMP, '--snippet', p_comp)
case('plan: component-kind succeeds with no --screen (not a usage error)',
     rc_comp_p in (0, 1), True)
case('plan: component-kind header renders (no crash, no traceback)',
     out_comp_p.startswith('GRAFT PLAN'), True)
_comp_graft_out = os.path.join(TMP, 'graft-component-noscreen.json')
rc_comp_g, out_comp_g, e_comp_g = run('graft', '--config', COMP, '--snippet', p_comp,
                                      '--out', _comp_graft_out)
case('graft: component-kind succeeds with no --screen', rc_comp_g in (0, 1), True)
case('graft: component-kind with no --screen actually writes --out',
     os.path.exists(_comp_graft_out), True)
_v_comp = subprocess.run([sys.executable, VERIFY, _comp_graft_out],
                         capture_output=True, text=True)
case('graft: component-kind graft (no --screen) is verify-clean', _v_comp.returncode, 0)

rc_theme_p, out_theme_p, e_theme_p = run('plan', '--config', COMP, '--snippet', p4)
case('plan: theme-kind succeeds with no --screen (not a usage error)',
     rc_theme_p in (0, 1), True)
_theme_graft_out = os.path.join(TMP, 'graft-theme-noscreen.json')
rc_theme_g, out_theme_g, e_theme_g = run('graft', '--config', COMP, '--snippet', p4,
                                         '--out', _theme_graft_out)
case('graft: theme-kind succeeds with no --screen', rc_theme_g in (0, 1), True)
case('graft: theme-kind with no --screen actually writes --out',
     os.path.exists(_theme_graft_out), True)

# `plan` must fail exactly the way `graft` does on a screen that is not there --
# the whole discipline of this feature is "read the plan first", and a plan that
# happily describes a graft `graft` will then refuse teaches the user the plan is
# not worth reading. Same message, same exit code -- 2, a usage error, never 1
# (which is reserved for "the graft is possible and here is what you must know").
_NO_SCREEN = 'NO-SUCH-SCREEN'
rc_bad_p, out_bad_p, e_bad_p = run('plan', '--config', COMP, '--snippet', p2,
                                   '--screen', _NO_SCREEN)
_bad_graft_out = os.path.join(TMP, 'graft-bad-screen.json')
rc_bad_g, out_bad_g, e_bad_g = run('graft', '--config', COMP, '--snippet', p2,
                                   '--screen', _NO_SCREEN, '--out', _bad_graft_out)
case('plan: a nonexistent --screen exits 2, matching graft', rc_bad_p, 2)
case('plan: a nonexistent --screen is a usage error, never a NEEDS YOU disclosure',
     rc_bad_p != 1, True)
case('plan: a nonexistent --screen never prints a plan',
     out_bad_p.startswith('GRAFT PLAN'), False)
case('plan and graft: identical exit code on a bad --screen', rc_bad_p, rc_bad_g)
case('plan and graft: identical error message on a bad --screen',
     e_bad_p.strip(), e_bad_g.strip())
case('plan: bad --screen message names the screen id', _NO_SCREEN in e_bad_p, True)
case('graft: a nonexistent --screen never writes --out',
     os.path.exists(_bad_graft_out), False)

# --- Final fix wave, Finding 1 (Critical): a minted id must not collide with the
# payload's OWN un-renamed ids ----------------------------------------------------
# `{card, card_2}` grafted where `card` alone is taken at the destination used to
# mint `card` -> `card_2`, colliding with the snippet's own `card_2` and collapsing
# two elements into one on write. Built directly (in-process) rather than through
# `extract`, so the exact colliding shape is pinned rather than hoped for.
_f1_payload = {
    'rootId': 'card',
    'map': {
        'card': {'id': 'card', 'type': 'text', 'props': {}},
        'card_2': {'id': 'card_2', 'type': 'text', 'props': {}},
    },
    'hierarchy': {'id': 'card', 'children': [{'id': 'card_2', 'children': []}]},
}
_f1_snippet = {
    'formatVersion': 1, 'kind': 'element', 'name': 'Card collision',
    'description': '', 'savedAt': '2026-08-27',
    'source': {'app': None, 'flowName': None, 'screenId': None, 'schemaVersion': None},
    'intendedScope': 'same-app',
    'payload': _f1_payload,
    'dependencies': {'colors': [], 'typography': [], 'fonts': [], 'icons': [],
                     'variables': [], 'components': {}, 'groups': [], 'products': [],
                     'consumes': [], 'producesInternally': [], 'navigateTargets': [],
                     'media': [], 'locales': [], 'defaultLocale': None},
}
_f1_config = {
    'screens': [{'id': 'scr_f1', 'elements': {
        'map': {'card': {'id': 'card', 'type': 'text', 'props': {}}},
        'hierarchy': {'id': 'root', 'children': [{'id': 'card', 'children': []}]}},
        'selectableGroups': []}],
    'components': {}, '_meta': {'screens': {}},
}

_f1_ren = sn.plan_renames(_f1_snippet, _f1_config)
case('finding1: the minted id is EXACTLY card_3 -- not card_2, which the payload '
     'itself already uses', _f1_ren['elements'], {'card': 'card_3'})

_f1_plan = sn.build_plan(_f1_snippet, _f1_config, 'scr_f1', None, None, None)
_f1_out = sn.apply_plan(_f1_config, _f1_snippet, _f1_plan)
_f1_final_map = _f1_out['screens'][0]['elements']['map']
case('finding1: element COUNT is preserved -- 1 destination + 2 grafted, no '
     'collapse', len(_f1_final_map), 3)
case('finding1: the destination\'s own `card` element survived untouched',
     'card' in _f1_final_map, True)
case('finding1: the payload\'s own `card_2` element survived untouched',
     'card_2' in _f1_final_map, True)
case('finding1: the renamed element landed at the minted id, colliding with '
     'neither the destination id nor the payload\'s own second id',
     'card_3' in _f1_final_map, True)
_f1_hier_ids = set()
def _f1_walk_hier(n):
    _f1_hier_ids.add(n['id'])
    for c in n.get('children') or []:
        _f1_walk_hier(c)
_f1_walk_hier(_f1_out['screens'][0]['elements']['hierarchy'])
case('finding1: the hierarchy carries three distinct ids too, matching the map',
     len(_f1_hier_ids & {'card', 'card_2', 'card_3'}), 3)

# The group form of the same hazard: a minted group id must not collide with
# another group the SAME snippet is carrying in.
_f1g_snippet = {
    'formatVersion': 1, 'kind': 'element', 'name': 'Group collision',
    'description': '', 'savedAt': '2026-08-27',
    'source': {'app': None, 'flowName': None, 'screenId': None, 'schemaVersion': None},
    'intendedScope': 'same-app',
    'payload': {'rootId': 'gel', 'map': {'gel': {'id': 'gel', 'type': 'text', 'props': {}}},
                'hierarchy': {'id': 'gel', 'children': []}},
    'dependencies': {'colors': [], 'typography': [], 'fonts': [], 'icons': [],
                     'variables': [], 'components': {},
                     'groups': [{'id': 'plan', 'type': 'single_choice'},
                               {'id': 'plan_2', 'type': 'single_choice'}],
                     'products': [], 'consumes': [], 'producesInternally': [],
                     'navigateTargets': [], 'media': [], 'locales': [],
                     'defaultLocale': None},
}
_f1g_config = {
    'screens': [{'id': 'scr_f1g', 'elements': {'map': {}, 'hierarchy': {'id': 'root', 'children': []}},
                'selectableGroups': [{'id': 'plan', 'type': 'single_choice'}]}],
    'components': {}, '_meta': {'screens': {}},
}
_f1g_ren = sn.plan_renames(_f1g_snippet, _f1g_config)
case('finding1 (groups): the minted group id is EXACTLY plan_3 -- not plan_2, '
     'which the snippet itself already carries', _f1g_ren['groups'], {'plan': 'plan_3'})

# --- Final fix wave, Finding 2 (Critical, crash): a valid-JSON but wrong-typed
# --config or --snippet must fail cleanly, never with a traceback ----------------
_BAD_SHAPES = (('list', [1, 2, 3]), ('string', 'hello'), ('int', 42))

for label, shape in _BAD_SHAPES:
    path = os.path.join(TMP, f'bad-config-{label}.json')
    json.dump(shape, open(path, 'w'))
    rc, out, err = run('plan', '--config', path, '--snippet', p2, '--screen', QUIZ_S0)
    case(f'finding2: a {label}-shaped --config exits 2, not a crash', rc, 2)
    case(f'finding2: a {label}-shaped --config produces no Python traceback',
         'Traceback' in err, False)

for label, shape in _BAD_SHAPES:
    path = os.path.join(TMP, f'bad-snippet-{label}.json')
    json.dump(shape, open(path, 'w'))
    rc, out, err = run('plan', '--config', QUIZ, '--snippet', path, '--screen', QUIZ_S0)
    case(f'finding2: a {label}-shaped --snippet exits 2, not a crash', rc, 2)
    case(f'finding2: a {label}-shaped --snippet produces no Python traceback',
         'Traceback' in err, False)

# --- Final fix wave, Finding 3 (Critical, crash): a catalog row that matches on
# store ids but carries no `id` must be skipped, never crash the rebind ----------
BAD_CAT_NOID = os.path.join(TMP, 'catalog-noid.json')
json.dump([{'vendor_products': {'app_store': {'product_id': 'com.x.0'}}}],
          open(BAD_CAT_NOID, 'w'))
_rc, out3, err3 = run('plan', '--config', COMP, '--snippet', pp_any, '--screen', COMP_S0,
                      '--catalog', BAD_CAT_NOID, '--json')
case('finding3: a store-id-matching catalog row with no `id` does not crash', _rc in (0, 1), True)
case('finding3: a store-id-matching catalog row with no `id` produces no traceback',
     'Traceback' in err3, False)
if _rc in (0, 1):
    pl_noid = json.loads(out3)
    case('finding3: a catalog row with no `id` invents no rebind', pl_noid['rebinds'], {})
    case('finding3: a catalog row with no `id` still asks for every product',
         len([n for n in pl_noid['needs'] if 'product' in n['text']]), len(src_products))

# --- Final fix wave, Finding 4 (Important): a font named directly by a CARRIED
# component's own element must be carried too, not just a font named by the
# payload or by a carried preset -------------------------------------------------
_F4_FONT_ID = 'font-only-in-component'
_F4_COMP_ID = 'pb_font_only_test'
_f4_snippet = {
    'payload': None,   # the top-level payload never mentions this font at all
    'dependencies': {
        'colors': [], 'typography': [],
        'fonts': [{'id': _F4_FONT_ID, 'name': 'Only In Component',
                  'iosName': 'OnlyInComponent', 'androidName': 'OnlyInComponent',
                  'url': 'https://example.invalid/only-in-component.ttf'}],
        'icons': [], 'variables': [],
        'components': {
            _F4_COMP_ID: {
                'map': {'el_f4': {'id': 'el_f4', 'type': 'text',
                                  'props': {'font': {'family': {'id': _F4_FONT_ID}}}}},
                'hierarchy': {'id': 'el_f4', 'children': []},
            },
        },
        'groups': [], 'products': [], 'consumes': [], 'producesInternally': [],
        'navigateTargets': [], 'media': [], 'locales': [], 'defaultLocale': None,
    },
}
_f4_dest = {
    'screens': [{'id': 'scr_f4', 'elements': {'map': {}, 'hierarchy': {'id': 'root', 'children': []}},
                'selectableGroups': []}],
    'theme': {'colors': [], 'typography': []}, '_meta': {'fonts': [], 'icons': []},
    'variables': [], 'components': {},
}
_f4_res = sn.resolve_theme(_f4_snippet, _f4_dest)
case('finding4: a font named only by an element inside a CARRIED component is '
     'itself carried', _F4_FONT_ID in {f['id'] for f in _f4_res['carry']['fonts']}, True)

# Existing invariant-9 behaviour (a carried PRESET drags its own font) must
# survive this change untouched -- re-run the same comparison-into-quiz pair the
# earlier Task 4 assertions used and confirm the same fonts still land.
case('finding4 regression check: invariant 9 path 2 (carried preset drags its '
     'font) is unaffected -- typ_RPXzQ8BE still carries exactly its own font',
     {f['id'] for f in pl2['carry']['fonts']},
     {'c9c5360d-44d1-4f97-3754-f1ab62af984c'})

# --- Final fix wave, Finding 5 (Important): the component cycle guard has no
# coverage today, so a regression there hangs the suite instead of failing red --
# Two-level nested chain: a screen pulls in component A, A pulls in component B,
# B carries a dependency of its own (a groupId) that must still surface.
_f5_chain_cfg = {
    'screens': [{'id': 'scr_f5chain', 'elements': {
        'map': {'root_el': {'id': 'root_el', 'type': 'container', 'props': {}}},
        'hierarchy': {'id': 'root_el', 'children': [
            {'id': 'pb_f5a', 'type': 'global', 'children': []}]}},
        'selectableGroups': []}],
    'components': {
        'pb_f5a': {
            'map': {'elA': {'id': 'elA', 'type': 'text', 'props': {}}},
            'hierarchy': {'id': 'elA', 'children': [
                {'id': 'pb_f5b', 'type': 'global', 'children': []}]},
        },
        'pb_f5b': {
            'map': {'elB': {'id': 'elB', 'type': 'text',
                            'props': {'groupId': 'grp_from_f5b'}}},
            'hierarchy': {'id': 'elB', 'children': []},
        },
    },
}
_els, _node, _s = sn.fragment_of(_f5_chain_cfg, 'root_el@scr_f5chain')
_d_chain = sn.scan_dependencies(_f5_chain_cfg, _els, _node)
case('finding5: a two-level nested component chain finds the INNER component',
     'pb_f5b' in _d_chain['components'], True)
case("finding5: the inner component's own dependency (a groupId) is reported",
     'grp_from_f5b' in _d_chain['groups'], True)

# Mutual reference (A -> B -> A): must terminate, not hang. Run under a subprocess
# timeout so a real regression here fails the suite red instead of wedging it.
_f5_cyc_cfg = {
    'screens': [{'id': 'scr_f5cyc', 'elements': {
        'map': {'root_el2': {'id': 'root_el2', 'type': 'container', 'props': {}}},
        'hierarchy': {'id': 'root_el2', 'children': [
            {'id': 'pb_f5c', 'type': 'global', 'children': []}]}},
        'selectableGroups': []}],
    'components': {
        'pb_f5c': {
            'map': {'elC': {'id': 'elC', 'type': 'text',
                            'props': {'groupId': 'grp_from_f5c'}}},
            'hierarchy': {'id': 'elC', 'children': [
                {'id': 'pb_f5d', 'type': 'global', 'children': []}]},
        },
        'pb_f5d': {
            'map': {'elD': {'id': 'elD', 'type': 'text', 'props': {}}},
            'hierarchy': {'id': 'elD', 'children': [
                {'id': 'pb_f5c', 'type': 'global', 'children': []}]},   # cycle back to C
        },
    },
}
_f5_cyc_path = os.path.join(TMP, 'cyclic-components.json')
json.dump(_f5_cyc_cfg, open(_f5_cyc_path, 'w'))
try:
    _f5r = subprocess.run([sys.executable, SNIP, 'scan', '--config', _f5_cyc_path,
                           'root_el2@scr_f5cyc'], capture_output=True, text=True, timeout=10)
    _f5_timed_out = False
    _f5_rc, _f5_out = _f5r.returncode, _f5r.stdout
except subprocess.TimeoutExpired:
    _f5_timed_out = True
    _f5_rc, _f5_out = None, ''
case('finding5: a mutual-reference component cycle TERMINATES (does not hang)',
     _f5_timed_out, False)
if not _f5_timed_out:
    case('finding5: a mutual-reference component cycle exits 0', _f5_rc, 0)
    _f5_cyc_d = json.loads(_f5_out)
    case('finding5: a mutual-reference cycle still reports the inner dependency',
         'grp_from_f5c' in _f5_cyc_d['groups'], True)
    case('finding5: a mutual-reference cycle reports both components exactly once',
         set(_f5_cyc_d['components']), {'pb_f5c', 'pb_f5d'})

# --- Task 11: placement description (Change 1) ----------------------------------
# Synthetic, minimal config so every position (empty root, existing siblings, a
# named parent) is exact and reproducible rather than depending on wherever a
# fixture's own hierarchy happens to have room.
_snip_place = {
    'formatVersion': sn.FORMAT_VERSION, 'kind': 'element', 'name': 'Placement probe',
    'description': '', 'savedAt': '2026-08-27',
    'source': {'app': None, 'flowName': None, 'screenId': None, 'schemaVersion': None},
    'intendedScope': 'same-app',
    'payload': {'rootId': 'el_new',
               'map': {'el_new': {'id': 'el_new', 'type': 'text', 'props': {}}},
               'hierarchy': {'id': 'el_new', 'children': []}},
    'dependencies': {'colors': [], 'typography': [], 'fonts': [], 'icons': [],
                     'components': {}, 'groups': [], 'products': [], 'consumes': [],
                     'producesInternally': [], 'navigateTargets': [], 'media': [],
                     'variables': [], 'locales': [], 'defaultLocale': None},
}
_cfg_place = {
    'screens': [
        {'id': 'scr_empty', 'props': {},
         'elements': {'map': {}, 'hierarchy': {'id': 'root', 'children': []}},
         'selectableGroups': []},
        {'id': 'scr_full', 'props': {}, 'elements': {
            'map': {'el_card': {'id': 'el_card', 'type': 'container', 'props': {}}},
            'hierarchy': {'id': 'root', 'children': [
                {'id': 'el_title', 'children': []},
                {'id': 'el_card', 'children': [{'id': 'el_sub', 'children': []}]},
                {'id': 'el_footer', 'children': []},
            ]}}, 'selectableGroups': []},
    ],
    '_meta': {'screens': {}}, 'theme': {'colors': [], 'typography': []},
}

pl_empty = sn.build_plan(_snip_place, _cfg_place, 'scr_empty', None, None, None)
case('placement: appending to an empty root names it precisely',
     pl_empty['placementText'], 'appended as the last child of `root`')

pl_append = sn.build_plan(_snip_place, _cfg_place, 'scr_full', None, None, None)
case('placement: appending under root with existing children still says "last child"',
     pl_append['placementText'], 'appended as the last child of `root`')

pl_first = sn.build_plan(_snip_place, _cfg_place, 'scr_full', None, 0, None)
case('placement: index 0 under root names the sibling it displaces',
     pl_first['placementText'], 'first child of `root`, before `el_title`')

pl_mid = sn.build_plan(_snip_place, _cfg_place, 'scr_full', None, 2, None)
case('placement: a middle index names the sibling it lands after',
     pl_mid['placementText'], 'at index 2 under `root`, after `el_card`')

pl_parent_append = sn.build_plan(_snip_place, _cfg_place, 'scr_full', 'el_card', None, None)
case('placement: appending under a NAMED parent (not root) names that parent',
     pl_parent_append['placementText'], 'appended as the last child of `el_card`')

pl_parent_first = sn.build_plan(_snip_place, _cfg_place, 'scr_full', 'el_card', 0, None)
case('placement: index 0 under a named parent names the child it displaces',
     pl_parent_first['placementText'], 'first child of `el_card`, before `el_sub`')

# The plan HEADER carries this line -- not just the `--json` field.
_report_first = sn.render_plan(pl_first, _snip_place, _cfg_place, 'scr_full')
case('placement: the plan header carries the placement line',
     '  first child of `root`, before `el_title`' in _report_first.splitlines(), True)

# `theme` and `component` are not positioned at all -- placementText must be None,
# never an invented "screen None" placeholder.
_rc_p4j, _out_p4j, _e = run('plan', '--config', COMP, '--snippet', p4, '--json')
case('placement: a theme-kind plan has no placementText',
     json.loads(_out_p4j)['placementText'], None)
_rc_pcj, _out_pcj, _e = run('plan', '--config', COMP, '--snippet', p_comp, '--json')
case('placement: a component-kind plan has no placementText',
     json.loads(_out_pcj)['placementText'], None)

# `screen`-kind: position is in `screens[]`, independent of any `--screen` passed
# for identity-resolution purposes.
_rc_pp, pl_pp_json = plan_json(QUIZ, pp, QUIZ_S0)
case('placement: a screen-kind graft with no --index appends as the last screen',
     pl_pp_json['placementText'], 'appended as the last screen')
_rc_pp0, pl_pp0_json = plan_json(QUIZ, pp, QUIZ_S0, extra=('--index', '0'))
case('placement: a screen-kind graft at index 0 names the screen it precedes',
     pl_pp0_json['placementText'],
     'first in `screens[]`, before screen "Welcome" (' + QUIZ_S0 + ')')

# --- The APPLIED line: printed by `graft`, never by `plan` -----------------------
_applied_el_out = os.path.join(TMP, 'applied-element.json')
_rc_ap, out_ap, _e = run('graft', '--config', QUIZ, '--snippet', p2, '--screen', QUIZ_S0,
                         '--out', _applied_el_out)
_applied_el_lines = [l for l in out_ap.splitlines() if l.startswith('APPLIED')]
case('applied: an element graft prints exactly one APPLIED line', len(_applied_el_lines), 1)
_pl_p2_json = plan_json(QUIZ, p2, QUIZ_S0)[1]
_p2_elcount = len(_pl_p2_json['adds']['elements'])
case('applied: the APPLIED line names the actual element count',
     f'{_p2_elcount} element' in _applied_el_lines[0], True)
case('applied: the APPLIED line names the destination screen id',
     f'`{QUIZ_S0}`' in _applied_el_lines[0], True)
case('applied: the APPLIED line carries the same placement text the plan header showed',
     _pl_p2_json['placementText'] in _applied_el_lines[0], True)
case('applied: `plan` (never writing) prints no APPLIED line',
     any(l.startswith('APPLIED') for l in
         run('plan', '--config', QUIZ, '--snippet', p2, '--screen', QUIZ_S0)[1].splitlines()),
     False)

_applied_theme_out = os.path.join(TMP, 'applied-theme.json')
_rc_apt, out_apt, _e = run('graft', '--config', COMP, '--snippet', p4,
                           '--out', _applied_theme_out)
case('applied: a theme graft names the merge target, not a screen',
     [l for l in out_apt.splitlines() if l.startswith('APPLIED')],
     ['APPLIED       theme merged into theme/_meta/variables'])

_applied_comp_out = os.path.join(TMP, 'applied-component.json')
_rc_apc, out_apc, _e = run('graft', '--config', COMP, '--snippet', p_comp,
                           '--out', _applied_comp_out)
case('applied: a component graft names the component id, not a screen',
     [l for l in out_apc.splitlines() if l.startswith('APPLIED')],
     ['APPLIED       component `pb_dl05vuVs` → components'])

_applied_screen_out = os.path.join(TMP, 'applied-screen.json')
_rc_aps, out_aps, _e = run('graft', '--config', QUIZ, '--snippet', pp, '--screen', QUIZ_S0,
                           '--out', _applied_screen_out)
_applied_screen_lines = [l for l in out_aps.splitlines() if l.startswith('APPLIED')]
case('applied: a screen graft names the screen and its resolved position, '
     'not an element count',
     any(l.startswith('APPLIED       screen') and 'appended as the last screen' in l
         for l in _applied_screen_lines), True)

# --- Task 12: carried-colour contrast (Change 3) ---------------------------------
# Direct math first -- revert-provable independent of any fixture or graft.
case('contrast: black vs white is the WCAG reference value 21.0:1',
     round(sn.contrast_ratio('#000000', '#FFFFFF'), 4), 21.0)
case('contrast: a 3-digit hex expands to the same ratio as its 6-digit form',
     sn.contrast_ratio('#abc', '#000000'), sn.contrast_ratio('#aabbcc', '#000000'))
case('contrast: a leading # is optional', sn.contrast_ratio('000000', 'ffffff'), 21.0)
case("contrast: mixed-case hex parses -- this repo's own comparison-paywall.json "
     'has literal `#FFFFFf`', sn.contrast_ratio('#FFFFFf', '#FFFFFF'), 1.0)
case('contrast: an 8-digit alpha hex is unresolvable, never guessed at',
     sn.contrast_ratio('#FFFFFFD9', '#000000'), None)
case('contrast: a non-hex string is unresolvable',
     sn.contrast_ratio('not-a-color', '#000000'), None)
case('contrast: either side unresolvable makes the whole ratio None',
     sn.contrast_ratio('#000000', None), None)

# The real failure this change encodes: a timeline grafted from a light-background
# flow into a dark one. `muted` (#8E99B3) exists in both flows with the SAME
# definition -> adopted/reused, never checked. `ink` (#0C1116) exists only in the
# source -> carried in verbatim, and against the destination's #080D1C background
# it is measured near-black-on-near-black.
_src_contrast_cfg = {
    'screens': [{'id': 'scr_src',
                'props': {'fill': {'type': 'color',
                                   'color': {'type': 'hex', 'hex': '#F5F5F5'}}},
                'elements': {
        'map': {
            'el_card': {'id': 'el_card', 'type': 'container', 'props': {}},
            'el_title': {'id': 'el_title', 'type': 'text', 'props': {'colorId': 'ink'}},
            'el_sub': {'id': 'el_sub', 'type': 'text', 'props': {'colorId': 'muted'}},
        },
        'hierarchy': {'id': 'root', 'children': [{'id': 'el_card', 'children': [
            {'id': 'el_title', 'children': []}, {'id': 'el_sub', 'children': []}]}]}},
                'selectableGroups': []}],
    'theme': {'colors': [
        {'id': 'ink', 'name': 'Ink', 'light': {'hex': '#0C1116'}},
        {'id': 'muted', 'name': 'Muted', 'light': {'hex': '#8E99B3'}}],
             'typography': []},
    '_meta': {'fonts': [], 'icons': [], 'screens': {}},
    'variables': [], 'components': {}, 'locales': [], 'defaultLocale': None,
    'schemaVersion': 10,
}
_dst_contrast_cfg = {
    'screens': [{'id': 'scr_dst',
                'props': {'fill': {'type': 'color',
                                   'color': {'type': 'hex', 'hex': '#080D1C'}}},
                'elements': {'map': {}, 'hierarchy': {'id': 'root', 'children': []}},
                'selectableGroups': []}],
    'theme': {'colors': [{'id': 'muted', 'name': 'Muted', 'light': {'hex': '#8E99B3'}}],
             'typography': []},
    '_meta': {'fonts': [], 'icons': [], 'screens': {}},
    'variables': [], 'components': {}, 'locales': [], 'defaultLocale': None,
    'schemaVersion': 10,
}
_snip_ink = sn.build_snippet(_src_contrast_cfg, 'element', 'el_card@scr_src',
                             'Timeline probe', '', 'same-app', None, None)

pl_ink = sn.build_plan(_snip_ink, _dst_contrast_cfg, 'scr_dst', None, None, None)
_ink_needs = [n for n in pl_ink['needs']
             if 'ink' in n['text'] and 'was carried in' in n['text']]
case('contrast: `ink` is reported as CARRIED (the only colour missing in the dest)',
     [c['id'] for c in pl_ink['carry']['colors']], ['ink'])
case('contrast: `muted` is REUSED, not carried', pl_ink['reuse'], ['muted'])
case('contrast: the real case FIRES -- carried `ink` (#0C1116) against a '
     '#080D1C background', len(_ink_needs), 1)
case('contrast: the fired need is `?`-level (advisory), never a blocker',
     _ink_needs[0]['level'] if _ink_needs else None, '?')
case('contrast: the fired need names the carried hex',
     '#0C1116' in _ink_needs[0]['text'] if _ink_needs else False, True)
case('contrast: the fired need names the destination background hex',
     '#080D1C' in _ink_needs[0]['text'] if _ink_needs else False, True)
_muted_contrast_needs = [n for n in pl_ink['needs'] if 'muted' in n['text']]
case('contrast: the adopted case STAYS SILENT -- `muted` never reaches the check '
     'at all because it was never carried', _muted_contrast_needs, [])

# Background resolution: image fill, no fill, gradient (first stop), array-form
# (v10) fill, and a colorId-referenced fill resolved against the DESTINATION theme.
def _contrast_fires(dst_cfg):
    pl = sn.build_plan(_snip_ink, dst_cfg, 'scr_dst', None, None, None)
    return [n for n in pl['needs'] if 'ink' in n['text'] and 'was carried in' in n['text']]

_dst_image = json.loads(json.dumps(_dst_contrast_cfg))
_dst_image['screens'][0]['props']['fill'] = {'type': 'image', 'image': {'url': 'x'}}
case('contrast: an image-fill background is unresolvable -- skips silently',
     _contrast_fires(_dst_image), [])

_dst_nofill = json.loads(json.dumps(_dst_contrast_cfg))
del _dst_nofill['screens'][0]['props']['fill']
case('contrast: no fill at all -- skips silently, never guesses',
     _contrast_fires(_dst_nofill), [])

_dst_grad = json.loads(json.dumps(_dst_contrast_cfg))
_dst_grad['screens'][0]['props']['fill'] = {'type': 'gradient', 'stops': [
    {'color': {'type': 'hex', 'hex': '#080D1C'}, 'position': 0},
    {'color': {'type': 'hex', 'hex': '#FFFFFF'}, 'position': 1}]}
case('contrast: a gradient background resolves via its FIRST stop',
     len(_contrast_fires(_dst_grad)), 1)

_dst_array = json.loads(json.dumps(_dst_contrast_cfg))
_dst_array['screens'][0]['props']['fill'] = [{'type': 'color',
                                              'color': {'type': 'hex', 'hex': '#080D1C'}}]
case('contrast: an array-form (v10) single-layer fill resolves the same as v9\'s object form',
     len(_contrast_fires(_dst_array)), 1)

_dst_colorid = json.loads(json.dumps(_dst_contrast_cfg))
_dst_colorid['theme']['colors'].append(
    {'id': 'bg', 'name': 'Background', 'light': {'hex': '#080D1C'}})
_dst_colorid['screens'][0]['props']['fill'] = {
    'type': 'color', 'color': {'type': 'color-style', 'colorId': 'bg'}}
case('contrast: a colorId-referenced fill resolves against the DESTINATION theme',
     len(_contrast_fires(_dst_colorid)), 1)

# Only an `element` snippet has an existing destination screen to compare against
# -- a `screen` snippet brings its own background along with it, so the check is
# out of scope for it (never a false negative on the real case: the destination
# screen simply does not exist yet at plan time).
_snip_ink_screen = sn.build_snippet(_src_contrast_cfg, 'screen', 'root@scr_src',
                                    'Full screen probe', '', 'same-app', None, None)
pl_screen_kind = sn.build_plan(_snip_ink_screen, _dst_contrast_cfg, None, None, None, None)
case('contrast: a `screen`-kind graft is out of scope for this check',
     [n for n in pl_screen_kind['needs'] if 'was carried in' in n['text']], [])

# Corpus-wide false-positive sweep: SAME-APP reuse (the default scope, and the
# realistic in-flow case) must never manufacture a contrast ask, because every
# colour a same-app fragment references already exists in the destination with
# the IDENTICAL definition -- reused, never carried. Every top-level child of
# every screen in every tracked fixture, extracted and planned onto every OTHER
# screen of the SAME fixture.
_corpus_pairs, _corpus_fires = 0, []
for _fx in (QUIZ, COMP, TABS, VPN, os.path.join(CORPUS, 'timeline-anchored.json')):
    _fxcfg = sn.load(_fx)
    for _s in _fxcfg['screens']:
        for _child in (_s['elements']['hierarchy'].get('children') or []):
            try:
                _probe = sn.build_snippet(_fxcfg, 'element', _child['id'] + '@' + _s['id'],
                                          'probe', '', 'same-app', None, None)
            except SystemExit:
                continue
            for _s2 in _fxcfg['screens']:
                if _s2['id'] == _s['id']:
                    continue
                _corpus_pairs += 1
                _plp = sn.build_plan(_probe, _fxcfg, _s2['id'], None, None, None)
                _corpus_fires += [n for n in _plp['needs'] if 'was carried in' in n['text']]
case(f'contrast: zero false positives across the tracked fixture corpus '
     f'({_corpus_pairs} same-app element-x-destination-screen pairs)',
     len(_corpus_fires), 0)

# --- Task 13: WILL SAY -- the plan lists the copy it is importing (Change 1) ----
# Direct unit checks on the token renderer, independent of any fixture.
case('willsay: a product-relative price variable strips its UUID head',
     sn._readable_ref('7658234e-f95b-474e-bf5c-4b9ae634029e.prod_price_per_month'),
     '{price_per_month}')
case('willsay: a bare prod_price (no per-period suffix) becomes {price}',
     sn._readable_ref('8fb58c50-7c05-42f9-a8e3-8d0fde19505a.prod_price'), '{price}')
case('willsay: a non-UUID head is shown verbatim, unstripped',
     sn._readable_ref('name.value'), '{name.value}')
case('willsay: a group-relative selectedProduct reference is shown verbatim',
     sn._readable_ref('products.selectedProduct.prod_price'),
     '{products.selectedProduct.prod_price}')
# The rule is keyed on the FIELD (`prod_`-prefixed), not merely "head is a
# UUID" -- a UUID head with a non-price tail is shown verbatim too.
case('willsay: a UUID head with a non-price tail is shown verbatim, not stripped',
     sn._readable_ref('7658234e-f95b-474e-bf5c-4b9ae634029e.selectedProduct'),
     '{7658234e-f95b-474e-bf5c-4b9ae634029e.selectedProduct}')

case('willsay: an inline `text` node contributes its own text verbatim',
     sn._inline_text([{'type': 'text', 'text': 'Hello '}]), 'Hello ')
case('willsay: an inline `variable` node renders as a readable token, never dropped',
     sn._inline_text([{'type': 'variable',
                       'attrs': {'variableId': 'name.value'}}]), '{name.value}')
case('willsay: an inline `token` node renders as a readable token, never dropped',
     sn._inline_text([{'type': 'token', 'attrs': {'token': 'timer_minutes'}}]),
     '{timer_minutes}')
case('willsay: mixed text + variable inline nodes concatenate with no added separator',
     sn._inline_text([{'type': 'variable', 'attrs': {'variableId': 'name.value'}},
                      {'type': 'text', 'text': '?'}]), '{name.value}?')

case('willsay: a bare string content value is returned verbatim',
     sn._readable_value('Next'), 'Next')
case('willsay: a paragraph-block content value concatenates blocks with NO separator',
     sn._readable_value([
         {'type': 'paragraph', 'content': [{'type': 'text', 'text': 'Are you ready, '}]},
         {'type': 'paragraph', 'content': [
             {'type': 'variable', 'attrs': {'variableId': 'name.value'}},
             {'type': 'text', 'text': '?'}]},
     ]), 'Are you ready, {name.value}?')
case('willsay: an unrecognised content shape resolves to None, never guessed at',
     sn._readable_value(42), None)

# `will_say_lines`: HIERARCHY order, not map/dict order -- built so map insertion
# order and hierarchy order actively DISAGREE, or a bug that read `emap` directly
# would still pass.
_ws_emap = {
    'el_b': {'id': 'el_b', 'type': 'text', 'props': {'content': 'Second'}},
    'el_a': {'id': 'el_a', 'type': 'text', 'props': {'content': 'First'}},
}
_ws_hier = {'id': 'root', 'children': [
    {'id': 'el_a', 'children': []}, {'id': 'el_b', 'children': []}]}
_ws_payload = {'rootId': 'root', 'map': _ws_emap, 'hierarchy': _ws_hier}
case('willsay: lines follow HIERARCHY order, not dict/map insertion order',
     sn.will_say_lines(_ws_payload, 'element', None), ['First', 'Second'])

# A `theme` snippet has no elements at all -- `[]`, never a crash on a null payload.
case('willsay: a theme-kind payload (None) yields no lines',
     sn.will_say_lines(None, 'theme', None), [])

# An element whose only prop is `image` (never `content`/`placeholder`) contributes
# nothing -- WILL SAY is about copy, not assets.
_ws_img_payload = {'rootId': 'el_img',
                   'map': {'el_img': {'id': 'el_img', 'type': 'image',
                                      'props': {'image': {
                                          '_localizable': True,
                                          'values': {'en': {'id': 'a', 'url': 'https://x'}}}}}},
                   'hierarchy': {'id': 'el_img', 'children': []}}
case('willsay: an image element (no content/placeholder key) contributes no line',
     sn.will_say_lines(_ws_img_payload, 'element', None), [])

# Locale fallback: no declared default -> the first locale alphabetically, the
# same fallback `resolve_locales` itself uses.
_ws_locale_payload = {'rootId': 'el_l', 'map': {'el_l': {'id': 'el_l', 'type': 'text',
    'props': {'content': {'_localizable': True,
                          'values': {'fr': 'Bonjour', 'de': 'Hallo'}}}}},
    'hierarchy': {'id': 'el_l', 'children': []}}
case('willsay: with no declared default locale, falls back to the first locale '
     'ALPHABETICALLY', sn.will_say_lines(_ws_locale_payload, 'element', None), ['Hallo'])
case("willsay: the snippet's OWN declared defaultLocale wins over alphabetical order",
     sn.will_say_lines(_ws_locale_payload, 'element', 'fr'), ['Bonjour'])

# `_truncate_line`: exact length and the unicode ellipsis this repo already uses
# elsewhere (`p["id"][:8]…`), never a multi-char "..." substitute.
case('willsay: a line at or under the cap is left untouched',
     sn._truncate_line('short line'), 'short line')
_long = 'A' * 100
_trunc = sn._truncate_line(_long)
case('willsay: a line over the cap is cut to exactly 72 chars including the ellipsis',
     len(_trunc), 72)
case('willsay: the truncated line ends in the unicode ellipsis, not "..."',
     _trunc[-1], '…')
case('willsay: embedded whitespace/newlines are collapsed to single spaces',
     sn._truncate_line('a\n\n  b   c'), 'a b c')

# --- End-to-end, against a real config: the quiz paywall grafted into
# comparison. `pp`/`out2`/`pl7b` are Task 7/8's own quiz-paywall-into-comparison
# pair -- reused rather than re-run, matching this suite's own convention.
case('willsay: WILL SAY heading appears in the human report', 'WILL SAY' in out2, True)
_ws_report_lines = out2.splitlines()
_ws_start = _ws_report_lines.index('WILL SAY')
_ws_block = []
for l in _ws_report_lines[_ws_start + 1:]:
    if not l.startswith('  '):
        break
    _ws_block.append(l)
case('willsay: the actual price copy is printed, product UUID stripped to a '
     'readable token', '  {price_per_month}/month' in _ws_block, True)
case('willsay: the actual annual price copy is printed the same way',
     '  {price_per_year}/year' in _ws_block, True)
case('willsay: the name-input variable renders as a readable token inside its '
     'sentence, not dropped',
     '  Are you ready, {name.value}?' in _ws_block, True)
case('willsay: plain button copy is printed verbatim',
     '  Subscribe' in _ws_block, True)

# Position, not just content: `WILL SAY` must be its OWN section, printed only
# after `WILL ADD` is complete -- element/group line PLUS every carry
# continuation line (`theme.colors`, `theme.typography`, `_meta.fonts`,
# `_meta.icons`, `variables`, each printed with a 14-space indent, distinct
# from WILL SAY's own 2-space content lines). This same plan (`out2`) carries
# both `theme.colors` and `theme.typography`, so it can actually exercise the
# ordering -- a plan with no carry lines would pass this trivially either way.
_wa_carry_labels = ('theme.colors', 'theme.typography', '_meta.fonts',
                    '_meta.icons', 'variables')
_wa_carry_line_idx = [i for i, l in enumerate(_ws_report_lines)
                      if l.startswith('              ')
                      and l.lstrip(' ').startswith(_wa_carry_labels)]
case('willsay: this plan actually has WILL ADD carry lines to order against '
     '(a non-vacuous check)', len(_wa_carry_line_idx) > 0, True)
case("willsay: every WILL ADD carry continuation line appears BEFORE the "
     "WILL SAY heading -- WILL SAY is not interleaved inside WILL ADD",
     all(i < _ws_start for i in _wa_carry_line_idx), True)

case('willsay --json: the plan carries a machine-readable `willSay` list',
     isinstance(pl7b.get('willSay'), list), True)
case('willsay --json: the json list contains the full, UNTRUNCATED sentence',
     'Are you ready, {name.value}?' in pl7b['willSay'], True)
case('willsay --json: the json list contains the price line with its token form',
     '{price_per_month}/month' in pl7b['willSay'], True)

# A `theme`-kind plan (`p4`) has no elements at all -- the section must be
# OMITTED entirely, never printed with an empty heading.
case('willsay: a theme-kind plan report has no WILL SAY heading at all',
     'WILL SAY' in out_theme2, False)
case('willsay --json: a theme-kind plan carries an empty willSay list',
     json.loads(_out_p4j)['willSay'], [])

# The cap and truncation wiring, END-TO-END through build_plan/render_plan --
# not just the standalone helpers above. 15 elements, each a few words, so the
# cap (12) and the "… and N more" tail both fire for real.
_ws15_map, _ws15_children = {}, []
for i in range(15):
    eid = f'el_ws{i}'
    _ws15_map[eid] = {'id': eid, 'type': 'text',
                      'props': {'content': f'Line number {i} of the fixture'}}
    _ws15_children.append({'id': eid, 'children': []})
_ws15_snippet = {
    'formatVersion': sn.FORMAT_VERSION, 'kind': 'element', 'name': 'Fifteen lines',
    'description': '', 'savedAt': '2026-08-27',
    'source': {'app': None, 'flowName': None, 'screenId': None, 'schemaVersion': None},
    'intendedScope': 'same-app',
    'payload': {'rootId': 'ws_root', 'map': _ws15_map,
               'hierarchy': {'id': 'ws_root', 'children': _ws15_children}},
    'dependencies': {'colors': [], 'typography': [], 'fonts': [], 'icons': [],
                     'components': {}, 'groups': [], 'products': [], 'consumes': [],
                     'producesInternally': [], 'navigateTargets': [], 'media': [],
                     'variables': [], 'locales': [], 'defaultLocale': None},
}
_ws15_cfg = {
    'screens': [{'id': 'scr_ws15', 'props': {},
                'elements': {'map': {}, 'hierarchy': {'id': 'root', 'children': []}},
                'selectableGroups': []}],
    '_meta': {'screens': {}}, 'theme': {'colors': [], 'typography': []},
}
_ws15_plan = sn.build_plan(_ws15_snippet, _ws15_cfg, 'scr_ws15', None, None, None)
case('willsay: build_plan carries all 15 UNCAPPED lines in willSay',
     len(_ws15_plan['willSay']), 15)
_ws15_report = sn.render_plan(_ws15_plan, _ws15_snippet, _ws15_cfg, 'scr_ws15')
_ws15_report_lines = _ws15_report.splitlines()
_ws15_shown = [l for l in _ws15_report_lines if l.startswith('  Line number')]
case('willsay: the rendered report shows exactly the CAP (12), never all 15',
     len(_ws15_shown), sn.WILL_SAY_MAX_LINES)
case('willsay: the rendered report names the remaining count precisely (15 - 12 = 3)',
     '  … and 3 more' in _ws15_report_lines, True)

_wslong_snippet = json.loads(json.dumps(_ws15_snippet))
_wslong_snippet['payload']['map']['el_ws0']['props']['content'] = 'B' * 100
_wslong_plan = sn.build_plan(_wslong_snippet, _ws15_cfg, 'scr_ws15', None, None, None)
_wslong_report = sn.render_plan(_wslong_plan, _wslong_snippet, _ws15_cfg, 'scr_ws15')
_wslong_line = next(l for l in _wslong_report.splitlines() if l.strip().startswith('B'))
case('willsay: a single over-cap line is truncated to 72 chars in the actual '
     'rendered report (end-to-end, not just the helper)',
     len(_wslong_line.strip()), 72)

if fails:
    print(f'\n{len(fails)} FAILED')
    for f in fails:
        print('  ' + f)
    sys.exit(1)
print(f'\nall passed')

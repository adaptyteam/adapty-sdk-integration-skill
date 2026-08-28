#!/usr/bin/env python3
"""Calibration for the transformer-refusal checks in `references/verify-config.py`.

Repo-only, like everything under `tests/`. It runs the shipped script as a subprocess --
never imports it, so nothing writes a `__pycache__` into `references/`, which the
copy-install path would ship.

These checks exist because `flows config validate` reports ONE fatal per run: a document
with three condition defects costs three network round trips, where this names all of them
locally in one pass. Each case below is one code the transform service refuses with a hard
422, ranked from production logs over the 40 days to 2026-08-28.

Two halves, and both matter equally. A check that misses its defect buys nothing over the
round trip; a check that fires on a real export gets ignored within a day, and then it misses
its defect too. So every case asserts a direction:

    FIRES   -- an injected defect must be reported as an ERROR, matching a fragment
    SILENT  -- every real export, tracked and raw, must produce no error at all

Usage: python3 tests/test-verify-transformer.py    # 0 all pass, 1 a case regressed
"""
import copy, glob, json, os, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERIFY = os.path.join(ROOT, 'skills', 'flow-generator', 'references', 'verify-config.py')
CORPUS = os.path.join(ROOT, 'tests', 'fixtures')
RAW = os.path.join(ROOT, 'tests', 'fixtures-raw')
SRC = os.path.join(CORPUS, 'onboarding-quiz-paywall.json')
TABS = os.path.join(CORPUS, 'tabs-paywall.json')
CAROUSEL = os.path.join(CORPUS, 'reviews-carousel.json')

fails = []


def errors(doc):
    """The ERROR lines the shipped script prints for `doc`."""
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, 'c.json')
        json.dump(doc, open(p, 'w'))
        r = subprocess.run([sys.executable, VERIFY, p], capture_output=True, text=True)
    return [l.split('ERROR:', 1)[1].strip() for l in r.stdout.splitlines() if 'ERROR:' in l]


def load(path=SRC):
    return json.load(open(path))


def first_element(d, pred):
    for s in d['screens']:
        for eid, e in s['elements']['map'].items():
            if pred(e):
                return s, eid, e
    raise AssertionError('no element matched')


def fires(name, doc, fragment):
    found = [e for e in errors(doc) if fragment in e]
    if not found:
        fails.append(f'{name}: expected an error containing {fragment!r}, got {errors(doc)!r}')
        print(f'  FAIL  {name}')
    else:
        print(f'  ok    {name}')


def silent(name, doc):
    errs = errors(doc)
    if errs:
        fails.append(f'{name}: expected no errors, got {errs!r}')
        print(f'  FAIL  {name}')
    else:
        print(f'  ok    {name}')


# ---------------------------------------------------------------- SILENT: the real corpus
print('SILENT on every real export (the false-positive half):')
for path in sorted(glob.glob(os.path.join(CORPUS, '*.json'))):
    silent(f'tracked {os.path.basename(path)}', load(path))
for path in sorted(glob.glob(os.path.join(RAW, '*.json'))):
    d = json.load(open(path))
    silent(f'raw {os.path.basename(path)}', d)

# ------------------------------------------------------- FIRES: one injected defect each
print('\nFIRES on an injected defect (the false-negative half):')

# --- invalid_visibility_condition / invalid_state_condition, one walker, several shapes.
def with_visibility(condition):
    d = load()
    s, eid, e = first_element(d, lambda e: e.get('type') == 'text')
    e.setdefault('props', {})['visibility'] = {'type': 'conditional', 'condition': condition}
    return d


fires('condition: unknown expression type',
      with_visibility({'type': 'bogus'}), 'invalid condition expression')
fires('condition: `assign`, schema-legal with no case in the walker',
      with_visibility({'type': 'assign', 'left': {'type': 'var', 'variableId': 'a'},
                       'right': {'type': 'const', 'value': 1}}),
      "'assign' has no case in the condition walker")
fires('condition: empty variableId',
      with_visibility({'type': 'var', 'variableId': ''}), '.variableId')
fires('condition: comparison missing its right operand',
      with_visibility({'type': '==', 'left': {'type': 'var', 'variableId': 'a.value'}}),
      '.right')
fires('condition: predicates present but not an array',
      with_visibility({'type': '&&', 'predicates': 'nope'}), '.predicates')
fires('condition: a switch case that is not a [predicate, value] pair',
      with_visibility({'type': 'switch', 'cases': [['only-one']]}), '.cases[0]')
fires('condition: a bare string where an expression belongs',
      with_visibility('email.value'), 'invalid condition expression')

# The three collections whose ABSENCE the service accepts -- a stricter port would fire here.
silent('condition: `&&` with predicates absent (service accepts)',
       with_visibility({'type': '&&'}))
silent('condition: `switch` with cases absent (service accepts)',
       with_visibility({'type': 'switch'}))
silent('condition: `concat` with operands absent (service accepts)',
       with_visibility({'type': 'concat'}))


def with_state_condition(condition):
    d = load()
    s, eid, e = first_element(d, lambda e: e.get('type') == 'text')
    e['states'] = [{'id': 'custom1', 'type': 'custom', 'condition': condition}]
    return d


fires('state condition: same walker, custom state',
      with_state_condition({'type': 'bogus'}), 'invalid condition expression')

# A `selected` system state's condition is overwritten by the service before use, so a
# malformed one there must NOT be reported -- that would be a false positive.
d = load()
_s, _eid, _e = first_element(d, lambda e: e.get('type') == 'text')
_e['states'] = [{'id': 'selected', 'type': 'system', 'condition': {'type': 'bogus'}}]
silent('state condition: `selected` is overwritten by the service, so not checked', d)

# --- script_type_violation: an unresolved condition variable becomes a bare identifier.
fires('condition variable resolving to nothing (TS2304)',
      with_visibility({'type': 'notEmpty',
                       'left': {'type': 'var', 'variableId': 'nosuchinput.value'}}),
      'resolves to nothing')

# --- invalid_action_payload, one code per required field.
def with_action(action):
    d = load()
    s, eid, e = first_element(d, lambda e: bool(e.get('interactions')))
    e['interactions'][0]['actions'] = [action]
    return d


fires('action: navigate with no screen',
      with_action({'id': 'a1', 'type': 'navigate', 'payload': {'type': 'screen'}}),
      '.payload.screen')
fires('action: navigate with no payload at all',
      with_action({'id': 'a1', 'type': 'navigate'}), 'no object payload')
fires('action: openUrl with no url',
      with_action({'id': 'a1', 'type': 'openUrl', 'payload': {}}), '.payload.url')
fires('action: selectProduct with no element id',
      with_action({'id': 'a1', 'type': 'selectProduct', 'payload': {}}), '.payload.element')
fires('action: custom with no payload id',
      with_action({'id': 'a1', 'type': 'custom', 'payload': {}}), '.payload.id')
fires('action: alert with neither title nor message',
      with_action({'id': 'a1', 'type': 'alert', 'payload': {}}), 'title or a message')
fires('action: setVariable with a non-array payload',
      with_action({'id': 'a1', 'type': 'setVariable', 'payload': {}}), 'ARRAY payload')
fires('action: setVariable assignment with no target',
      with_action({'id': 'a1', 'type': 'setVariable', 'payload': [{'left': {}}]}),
      'left.variableId')
fires('action: conditional with cases that are not tuples',
      with_action({'id': 'a1', 'type': 'conditional',
                   'payload': {'type': 'switch', 'cases': ['nope']}}),
      'not a [predicate, value] tuple')
fires('action: purchase with neither a product id nor an expression',
      with_action({'id': 'a1', 'type': 'purchase', 'payload': {'product': {}}}),
      '.payload.product.id')

# A purchase bound to an EXPRESSION is what every real export does -- must stay silent.
silent('action: purchase bound to a var expression (the real-export shape)',
       with_action({'id': 'a1', 'type': 'purchase',
                    'payload': {'product': {'type': 'var',
                                            'variableId': 'products.selectedProduct'}}}))

# --- empty_carousel
d = json.load(open(CAROUSEL))
for s in d['screens']:
    def strip(n):
        if s['elements']['map'].get(n.get('id'), {}).get('type') == 'carousel':
            n['children'] = []
        for c in n.get('children') or []:
            strip(c)
    strip(s['elements']['hierarchy'])
fires('carousel with no slides', d, 'empty_carousel')

# --- mixed_tab_group_ids / wrong_tab_selectable_group_type
def tabs_doc(mutate):
    d = json.load(open(TABS))
    mutate(d)
    return d


def _disagree(d):
    for s in d['screens']:
        items = [e for e in s['elements']['map'].values() if e.get('type') == 'tab-item']
        if len(items) > 1:
            items[0]['props']['groupId'] = 'other'
            s['selectableGroups'].append({'id': 'other', 'type': 'single_choice'})
            return


def _wrong_type(d):
    for s in d['screens']:
        for g in s.get('selectableGroups') or []:
            if g['id'] == 'tabs':
                g['type'] = 'multi_choice'


fires('tab-items disagreeing on groupId', tabs_doc(_disagree), 'mixed_tab_group_ids')
fires('tab group declared something other than single_choice',
      tabs_doc(_wrong_type), 'wrong_tab_selectable_group_type')

# --- invalid_localized_rich_text
d = load()
_s, _eid, _e = first_element(d, lambda e: isinstance((e.get('props') or {}).get('content'), dict))
_e['props']['content']['values'] = {k: {'oops': True}
                                    for k in _e['props']['content']['values']}
fires('a localizable content value that is neither string, array nor switch',
      d, 'invalid_localized_rich_text')

# --- mixed_product_targets_in_text
d = load()
prods = sorted({p['id'] for v in d.get('_meta', {}).get('screens', {}).values()
                for p in v.get('products', [])})
if len(prods) > 1:
    _s, _eid, _e = first_element(d, lambda e: isinstance((e.get('props') or {}).get('content'),
                                                         dict))
    node = {'type': 'paragraph', 'content': [
        {'type': 'variable', 'variableId': f'{prods[0]}.prod_price'},
        {'type': 'variable', 'variableId': f'{prods[1]}.prod_price'}]}
    _e['props']['content']['values'] = {k: [node]
                                        for k in _e['props']['content']['values']}
    fires('one text referencing two distinct products', d,
          'mixed_product_targets_in_text')
else:
    print('  skip  mixed_product_targets_in_text (fixture has <2 declared products)')

# --- theme colour hexes, position-scoped (see THEME_HEX in verify-config.py).
for _tag, _hex in (('3-digit', '#fff'), ('empty', ''), ('no-hash', 'FFFFFF'),
                   ('8-digit', '#FFFFFFD9'), ('7-digit', '#FFFFFFF')):
    _d = load(os.path.join(CORPUS, 'comparison-paywall.json'))
    _d['theme']['colors'][0]['light']['hex'] = _hex
    fires(f'theme hex {_tag} ({_hex!r})', _d, 'not #RRGGBB')

# An ELEMENT colour is a different rule: the service accepts a 3-digit hex, an 8-digit one and
# an empty string there, and real exports carry both -- so this must stay silent.
_d = load()
_s, _eid, _e = first_element(_d, lambda e: e.get('type') == 'text')
_e.setdefault('props', {})['color'] = {'type': 'hex', 'hex': '#fff', 'opacity': 100}
silent('an element colour with a 3-digit hex (real exports carry looser forms)', _d)

# --- `<groupId>.selectedOptionId` on a multi_choice group (round-2 bycatch, three agents).
_d = load(os.path.join(CORPUS, 'onboarding-quiz-paywall.json'))
for _s in _d['screens']:
    for _g in (_s.get('selectableGroups') or []):
        if f'{_g["id"]}.selectedOptionId' in json.dumps(_d):
            _g['type'] = 'multi_choice'
fires('selectedOptionId read from a multi_choice group', _d, 'multi_choice')

# single_choice is the form the service accepts -- the corpus already uses it, so this is the
# false-positive guard for the check above.
silent('the same read on a single_choice group (the corpus form)',
       load(os.path.join(CORPUS, 'onboarding-quiz-paywall.json')))

print()
if fails:
    print(f'{len(fails)} FAILED')
    for f in fails:
        print('  -', f)
    sys.exit(1)
print('all checks passed')

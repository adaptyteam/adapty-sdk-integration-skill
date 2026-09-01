#!/usr/bin/env python3
"""Calibration for `skills/flow-audit/references/audit-flow.py`.

Repo-only. Runs the shipped script as a subprocess -- never imports it, so nothing
writes a `__pycache__` into `references/`, which the copy-install path would ship.

Every case asserts a direction, because both halves matter equally:

    FIRES   -- an injected defect must be reported, at the stated severity
    SILENT  -- a real flow must produce nothing for that check

Usage: python3 tests/test-audit-flow.py     # 0 all pass, 1 a case regressed
"""
import copy, json, os, re, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUDIT = os.path.join(ROOT, 'skills', 'flow-audit', 'references', 'audit-flow.py')
FIX = os.path.join(ROOT, 'tests', 'fixtures')
FLOW = os.path.join(FIX, 'onboarding-multilocale.json')
CATALOG = os.path.join(ROOT, 'tests', 'catalog-fixture.json')

fails = []


def run(config, catalog=CATALOG, stores=None):
    """Return (rc, findings). `config` is a path or a dict."""
    with tempfile.TemporaryDirectory() as tmp:
        if isinstance(config, dict):
            path = os.path.join(tmp, 'c.json')
            json.dump(config, open(path, 'w'))
        else:
            path = config
        cmd = [sys.executable, AUDIT, path, '--json']
        if catalog:
            cmd += ['--catalog', catalog]
        if stores:
            cmd += ['--stores', stores]
        r = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return r.returncode, json.loads(r.stdout)['findings']
    except Exception:
        # Surface the parse failure distinguishably: `None`, never a fabricated `[]`,
        # so a caller asserting `isinstance(findings, list)` can actually catch this.
        fails.append(f'unparseable output (rc={r.returncode}): {r.stdout[:200]} {r.stderr[:200]}')
        return r.returncode, None


def check(name, cond, detail=''):
    if cond:
        print(f'  ok    {name}')
    else:
        print(f'  FAIL  {name} {detail}')
        fails.append(name)


def of(findings, checkname):
    return [f for f in (findings or []) if f['check'] == checkname]


def load(path=FLOW):
    return json.load(open(path))


print('contract')
rc, findings = run(FLOW)
check('exit code is a legal value', rc in (0, 1), f'rc={rc}')
check('findings is a list', isinstance(findings, list))
check('every finding has the full key set',
      all(set(f) == {'severity', 'family', 'check', 'screen', 'element', 'message', 'fix'}
          for f in (findings or [])))
check('every severity is legal',
      all(f['severity'] in ('blocker', 'risk', 'question') for f in (findings or [])))
check('accepts an envelope as well as a bare config',
      run({'config': load(), 'status': 'draft', 'updated_at': 1})[0] in (0, 1))

print('\nparser')
# Finding 1: the positional config path must be found by INDEX, not by filtering argv
# for values equal to a flag's value -- a config path identical to the catalog path
# must not empty the positional list.
rc_eq, findings_eq = run(FLOW, catalog=FLOW)
check('a config path equal to the catalog path still parses (exit code)',
      rc_eq == rc, f'rc_eq={rc_eq} rc={rc}')
# The positional and --catalog are the SAME string here, but they are not the same
# semantic thing: --catalog FLOW loads the flow doc itself, which has no top-level
# `data` key, so main() unwraps it to an empty catalog `[]`. That legitimately changes
# the `products` family (every bound product now reports product-not-in-catalog
# against an empty catalog) without meaning the parser mis-resolved the positional --
# so compare everything else, and pin the products-family fallout separately.
# `billed-amount-not-shown` is ALSO catalog-dependent (an empty catalog means every
# bound product is missing from it, which both removes the `period` the risk form
# needs and puts the product in `check_price_prominence`'s `already_reported` set, so
# the check goes SILENT rather than firing either form -- see that function), so it
# gets the same carve-out as the products family.
check('a config path equal to the catalog path still parses (same non-products findings)',
      [f for f in (findings_eq or [])
       if f['family'] != 'products' and f['check'] != 'billed-amount-not-shown'] ==
      [f for f in (findings or [])
       if f['family'] != 'products' and f['check'] != 'billed-amount-not-shown'],
      'non-products findings differ when config path == catalog path')
_n_bound = sum(
    1 for s in load()['screens']
    for e in s['elements']['map'].values()
    if ((e.get('props') or {}).get('product') or {}).get('id'))
check('...and the reused path reads as an empty catalog, flagging every bound product',
      len(of(findings_eq, 'product-not-in-catalog')) == _n_bound, f'_n_bound={_n_bound}')

# Finding 2: a value-flag with nothing after it is a usage error (exit 2 on stderr),
# never a silently-ignored no-op.
r = subprocess.run([sys.executable, AUDIT, FLOW, '--catalog'], capture_output=True, text=True)
check('a trailing --catalog with no value is a usage error',
      r.returncode == 2, f'rc={r.returncode}')
check('a trailing --catalog with no value writes to stderr', bool(r.stderr.strip()))

r = subprocess.run([sys.executable, AUDIT, FLOW, '--stores'], capture_output=True, text=True)
check('a trailing --stores with no value is a usage error',
      r.returncode == 2, f'rc={r.returncode}')
check('a trailing --stores with no value writes to stderr', bool(r.stderr.strip()))

r = subprocess.run([sys.executable, AUDIT, FLOW, '--catalog', '--json'],
                    capture_output=True, text=True)
check('--catalog immediately followed by another flag is a usage error',
      r.returncode == 2, f'rc={r.returncode}')

print('\ntriggers')
rc, findings = run(FLOW)
dead = of(findings, 'dead-affordance')
check('dead affordance FIRES on the fixture (el_089T reads Restore/Terms/Privacy '
      'and has no interaction)', len(dead) == 1, f'got {len(dead)}')
check('dead affordance is a blocker',
      all(f['severity'] == 'blocker' for f in dead))
check('dead affordance names the element', dead and dead[0]['element'] is not None)

# SILENT: a plain caption that names no action must not be flagged
c = load()
for s in c['screens']:
    for eid, e in s['elements']['map'].items():
        if e.get('type') == 'text':
            e.setdefault('props', {})['content'] = {
                'values': {l: 'Welcome aboard' for l in ('en', 'sr', 'sr-Latn')}}
            break
    break
check('a non-action caption stays SILENT',
      len(of(run(c)[1], 'dead-affordance')) == len(dead))

# FIRES: an action wired to nothing
c = load()
first = c['screens'][0]['elements']['map']
tgt = next(iter(first))
first[tgt]['interactions'] = [{'id': 'int_x', 'trigger': 'tap',
                              'actions': [{'id': 'act_x', 'type': 'nothing'}]}]
check('a `nothing` action FIRES', len(of(run(c)[1], 'action-nothing')) == 1)
check('`nothing` is SILENT on the clean fixture', len(of(findings, 'action-nothing')) == 0)

# FIRES: an interaction with no actions
c = load()
first = c['screens'][0]['elements']['map']
first[tgt]['interactions'] = [{'id': 'int_y', 'trigger': 'tap', 'actions': []}]
check('an empty actions array FIRES', len(of(run(c)[1], 'interaction-no-actions')) == 1)
check('empty actions is SILENT on the clean fixture',
      len(of(findings, 'interaction-no-actions')) == 0)

# FIRES: openUrl with no url
c = load()
first = c['screens'][0]['elements']['map']
first[tgt]['interactions'] = [{'id': 'int_z', 'trigger': 'tap',
                               'actions': [{'id': 'act_z', 'type': 'openUrl',
                                            'payload': {'external': True}}]}]
check('openUrl with no url FIRES', len(of(run(c)[1], 'openurl-no-url')) == 1)

print('\ntriggers: corpus calibration (ancestor walk + 1+-word threshold)')
# comparison-paywall.json: "Restore" / "Terms" / "Privacy" are each standalone one-word
# labels with no interaction on themselves OR on any ancestor -- and the whole flow has
# no `restorePurchases` action and no `openUrl` action at all. Genuinely dead, all three.
rc_cmp, findings_cmp = run(os.path.join(FIX, 'comparison-paywall.json'))
check('comparison-paywall.json FIRES exactly 3 dead-affordance '
      '(Restore, Terms, Privacy -- no restorePurchases/openUrl anywhere in the flow)',
      len(of(findings_cmp, 'dead-affordance')) == 3,
      f'got {len(of(findings_cmp, "dead-affordance"))}')
check('comparison-paywall.json\'s dead affordances are all blockers',
      all(f['severity'] == 'blocker' for f in of(findings_cmp, 'dead-affordance')))

# These real exports carry one-word affordance labels ("Skip", "Terms", "Restore",
# "Privacy") whose tap target lives on a wired ANCESTOR -- the ancestor walk must clear
# every one of them, on every trigger check.
for _name in ('onboarding-quiz-paywall.json', 'tabs-paywall.json', 'timeline-anchored.json'):
    _rc, _findings = run(os.path.join(FIX, _name))
    _trig = [f for f in (_findings or []) if f['family'] == 'triggers']
    check(f'{_name} is SILENT on every trigger check',
          len(_trig) == 0, f'got {[t["check"] for t in _trig]}')

print('\ntriggers: dead-affordance is a LABEL match, not a substring match (C2)')
# Four reproduced false-positive blockers: raw substring matching flagged ordinary
# marketing copy that merely CONTAINS an affordance word, on an unwired text
# element. All four must now be SILENT.
FALSE_POSITIVE_COPY = (
    'Restore your natural sleep rhythm in 7 days',
    'We take your privacy seriously and never sell your data',
    'The best value in terms of cost per session',
    'Skip the guesswork — we plan every workout for you',
)
for _copy in FALSE_POSITIVE_COPY:
    # A standalone single-element synthetic config, not the FLOW fixture -- the
    # fixture's own el_089T is a genuine, already-firing dead-affordance case, and
    # reusing it (with a `break` that may not even land on el_089T) risks the
    # assertion passing or failing for the wrong reason. This element carries no
    # interaction of its own and has no ancestor at all, so if `named` is
    # non-empty the check WOULD fire -- silence here can only mean the label match
    # itself declined the copy, isolating exactly what C2 changed.
    _cfg = {'screens': [{'id': 'scr_x', 'elements': {'map': {
        'el_copy': {'type': 'text',
                    'props': {'content': {'values': {'en': _copy}}}},
    }}}], 'locales': [], 'defaultLocale': 'en'}
    check(f'{_copy!r} stays SILENT (affordance word inside a sentence, not a label)',
          len(of(run(_cfg, catalog=None)[1], 'dead-affordance')) == 0,
          [f['message'] for f in of(run(_cfg, catalog=None)[1], 'dead-affordance')])

# Must still FIRE: a single element packing several affordances into one label row,
# separated by `·` -- el_089T in onboarding-multilocale.json reads exactly this way.
dead_row = of(run(FLOW)[1], 'dead-affordance')
check('el_089T ("Restore purchase · Terms · Privacy") still FIRES as one '
      'dead-affordance finding naming all three',
      len(dead_row) == 1
      and all(w in dead_row[0]['message'] for w in ('restore', 'terms', 'privacy')),
      dead_row)

# Must still FIRE: three SEPARATE sibling elements each carrying one bare affordance
# word -- comparison-paywall.json's Restore/Terms/Privacy, already covered by the
# corpus-calibration check above (3 dead-affordance findings); re-asserted here
# under the C2 heading so the label-matching fix is pinned against both shapes
# (one element, several labels) AND (several elements, one label each).
check('comparison-paywall.json\'s three separate one-word elements '
      '(Restore / Terms / Privacy) still FIRE 3 separate dead-affordance findings',
      len(of(findings_cmp, 'dead-affordance')) == 3, findings_cmp)

# Must still be SILENT: "Skip" on its own, wired to a parent -- for the ANCESTOR
# reason, not the label-matching reason. tabs-paywall.json carries this element and
# is already asserted SILENT on every trigger check above; re-confirm the label
# itself ("skip") is still recognised as an affordance word in isolation, so a truly
# UNWIRED bare "Skip" would still fire (proven directly, isolated from any fixture).
skip_only = {
    'screens': [{'id': 'scr_x', 'elements': {'map': {
        'el_skip': {'type': 'text', 'props': {'content': {'values': {'en': 'Skip'}}}},
    }}}],
    'locales': [], 'defaultLocale': 'en'}
check('a bare, UNWIRED "Skip" element still FIRES dead-affordance '
      '(label matching did not silence the one-word case)',
      len(of(run(skip_only)[1], 'dead-affordance')) == 1,
      run(skip_only)[1])

print('\ncompliance')
rc, findings = run(FLOW)
check('no-restore FIRES (the flow sells and has no restorePurchases action)',
      len(of(findings, 'no-restore')) == 1)
check('no-terms-link FIRES', len(of(findings, 'no-terms-link')) == 1)
check('no-privacy-link FIRES', len(of(findings, 'no-privacy-link')) == 1)
check('no-escape-from-paywall FIRES (scr_paywall has only a purchase action)',
      len(of(findings, 'no-escape-from-paywall')) == 1)
check('the paywall blockers make the run exit 1', rc == 1, f'rc={rc}')

# the escape finding must report the label as evidence, since 7 of 9 measured escapes
# are icon-only -- this flow's own closeFlow buttons carry no text, so the message
# must fall back to the "(icon only, no text)" phrase rather than go silent about it.
esc = of(findings, 'no-escape-from-paywall')
check('no-escape-from-paywall names a label or the icon-only phrase as evidence',
      bool(esc) and '(icon only, no text)' in esc[0]['message'],
      esc[0]['message'] if esc else '<no finding>')

# SILENT: adding a restorePurchases action anywhere clears no-restore
c = load()
pw = [s for s in c['screens'] if s['id'] == 'scr_paywall'][0]
eid = next(iter(pw['elements']['map']))
pw['elements']['map'][eid]['interactions'] = [
    {'id': 'int_r', 'trigger': 'tap',
     'actions': [{'id': 'act_r', 'type': 'restorePurchases'}]}]
check('no-restore goes SILENT once the action exists',
      len(of(run(c)[1], 'no-restore')) == 0)

# SILENT: an escape reachable by navigate from the paywall clears the blocker
c = load()
pw = [s for s in c['screens'] if s['id'] == 'scr_paywall'][0]
eid = next(iter(pw['elements']['map']))
pw['elements']['map'][eid]['interactions'] = [
    {'id': 'int_c', 'trigger': 'tap',
     'actions': [{'id': 'act_c', 'type': 'closeFlow'}]}]
check('no-escape-from-paywall goes SILENT with a closeFlow on the screen',
      len(of(run(c)[1], 'no-escape-from-paywall')) == 0)

c = load()
pw = [s for s in c['screens'] if s['id'] == 'scr_paywall'][0]
eid = next(iter(pw['elements']['map']))
pw['elements']['map'][eid]['interactions'] = [
    {'id': 'int_n', 'trigger': 'tap',
     'actions': [{'id': 'act_n', 'type': 'navigate',
                  'payload': {'type': 'screen', 'screen': 'scr_welcome'}}]}]
check('no-escape-from-paywall goes SILENT when a navigate REACHES an escape',
      len(of(run(c)[1], 'no-escape-from-paywall')) == 0)

no_sell_with_escape = {
    'screens': [{'id': 'scr_only', 'elements': {'map': {
        'el_close': {
            'type': 'text', 'props': {'content': {'values': {'en': 'Close'}}},
            'interactions': [{'id': 'i_close', 'trigger': 'tap', 'actions': [
                {'id': 'a_close', 'type': 'closeFlow', 'payload': {}}]}]},
    }}}],
    'locales': [], 'defaultLocale': 'en'}
check('a flow with no selling screen AND a real escape reports no compliance '
      'findings at all -- no-restore/no-terms-link/no-privacy-link/'
      'no-escape-from-paywall are all scoped to selling screens, and '
      'no-escape-in-flow is silent because an escape exists',
      not any(x['family'] == 'compliance'
              for x in (run(no_sell_with_escape, catalog=None)[1] or [])))

# `no-escape-in-flow` is NOT gated behind selling: a non-paywall onboarding flow
# with no way off anywhere fires it too -- the early `if not selling: return out`
# used to defeat this entirely (CLAUDE.md finding, corrected here). A `screens: []`
# flow has no escape and no selling screen, so this is the narrowest repro.
no_sell_no_escape_findings = run(
    {'screens': [], 'locales': [], 'defaultLocale': 'en'})[1] or []
check('a flow with no selling screen and NO escape anywhere still FIRES '
      'no-escape-in-flow (this check applies to any flow, selling or not)',
      len(of(no_sell_no_escape_findings, 'no-escape-in-flow')) == 1,
      no_sell_no_escape_findings)
check('...and no OTHER compliance check fires alongside it (the rest stay scoped '
      'to selling screens, which this flow has none of)',
      [x['check'] for x in no_sell_no_escape_findings if x['family'] == 'compliance']
      == ['no-escape-in-flow'], no_sell_no_escape_findings)

# Both legal-link checks are a blocker on the base fixture, which has no openUrl
# action at all -- outcome 1 of the ruling: certain, because there cannot be a legal
# link without one.
check('no-terms-link is a blocker when there is no openUrl action anywhere',
      bool(of(findings, 'no-terms-link'))
      and of(findings, 'no-terms-link')[0]['severity'] == 'blocker')
check('no-privacy-link is a blocker when there is no openUrl action anywhere',
      bool(of(findings, 'no-privacy-link'))
      and of(findings, 'no-privacy-link')[0]['severity'] == 'blocker')

# The reviewer's counterexample: real, working openUrl actions to /terms and
# /privacy -- but the buttons are labeled "Legal". Detection must live on the url
# payload, never the label, or this is exactly the false blocker a reviewer caught:
# asserting no such link exists when one demonstrably does.
c = load()
pw = [s for s in c['screens'] if s['id'] == 'scr_paywall'][0]
eids = list(pw['elements']['map'])
t_eid, p_eid = eids[0], eids[1]
for eid_, url_, act_id in ((t_eid, 'https://example.com/terms', 'act_lt'),
                           (p_eid, 'https://example.com/privacy', 'act_lp')):
    el = pw['elements']['map'][eid_]
    el.setdefault('props', {})['content'] = {
        'values': {l: 'Legal' for l in ('en', 'sr', 'sr-Latn')}}
    el['interactions'] = [
        {'id': f'int_{act_id}', 'trigger': 'tap',
         'actions': [{'id': act_id, 'type': 'openUrl', 'payload': {'url': url_}}]}]
legal_findings = run(c)[1]
check('a real openUrl to /terms labeled "Legal" clears no-terms-link',
      len(of(legal_findings, 'no-terms-link')) == 0)
check('a real openUrl to /privacy labeled "Legal" clears no-privacy-link',
      len(of(legal_findings, 'no-privacy-link')) == 0)

# An openUrl action exists but its url is opaque (no terms/privacy token at all) --
# outcome 3: a QUESTION, not a blocker, naming the url so the human can confirm it.
c = load()
pw = [s for s in c['screens'] if s['id'] == 'scr_paywall'][0]
eid = next(iter(pw['elements']['map']))
pw['elements']['map'][eid]['interactions'] = [
    {'id': 'int_op', 'trigger': 'tap',
     'actions': [{'id': 'act_op', 'type': 'openUrl',
                  'payload': {'url': 'https://x.co/a1'}}]}]
opaque_findings = run(c)[1]
opaque_terms = of(opaque_findings, 'no-terms-link')
opaque_privacy = of(opaque_findings, 'no-privacy-link')
check('an opaque openUrl url with no matching token FIRES no-terms-link as a question '
      'naming the url',
      len(opaque_terms) == 1 and opaque_terms[0]['severity'] == 'question'
      and 'https://x.co/a1' in opaque_terms[0]['message'],
      opaque_terms[0]['message'] if opaque_terms else '<no finding>')
check('an opaque openUrl url with no matching token FIRES no-privacy-link as a '
      'question naming the url',
      len(opaque_privacy) == 1 and opaque_privacy[0]['severity'] == 'question'
      and 'https://x.co/a1' in opaque_privacy[0]['message'],
      opaque_privacy[0]['message'] if opaque_privacy else '<no finding>')

# Substring-containment trap: a vocabulary word matching INSIDE an unrelated word must
# not silence the check -- 'tos' inside 'photos'/'autos', 'legal' inside 'illegally'.
# Each of these three urls has no legal link at all, so both checks must still fire
# (as a question, since an openUrl action does exist -- just not a matching one).
for url_ in ('https://example.com/photos/hero.jpg',
             'https://example.com/autos/list',
             'https://example.com/illegally-obtained-content'):
    c = load()
    pw = [s for s in c['screens'] if s['id'] == 'scr_paywall'][0]
    eid = next(iter(pw['elements']['map']))
    pw['elements']['map'][eid]['interactions'] = [
        {'id': 'int_collision', 'trigger': 'tap',
         'actions': [{'id': 'act_collision', 'type': 'openUrl',
                      'payload': {'url': url_}}]}]
    coll_findings = run(c)[1]
    check(f'{url_!r} does not falsely silence no-terms-link (substring trap)',
          len(of(coll_findings, 'no-terms-link')) == 1,
          f'got {of(coll_findings, "no-terms-link")}')
    check(f'{url_!r} does not falsely silence no-privacy-link (substring trap)',
          len(of(coll_findings, 'no-privacy-link')) == 1,
          f'got {of(coll_findings, "no-privacy-link")}')

# The tokenized positives must still clear the checks -- tokenizing must not itself
# become a false blocker.
c = load()
pw = [s for s in c['screens'] if s['id'] == 'scr_paywall'][0]
eid = next(iter(pw['elements']['map']))
pw['elements']['map'][eid]['interactions'] = [
    {'id': 'int_tos', 'trigger': 'tap',
     'actions': [{'id': 'act_tos', 'type': 'openUrl',
                  'payload': {'url': 'https://example.com/tos'}}]}]
check('a real /tos url still clears no-terms-link after tokenizing',
      len(of(run(c)[1], 'no-terms-link')) == 0)

c = load()
pw = [s for s in c['screens'] if s['id'] == 'scr_paywall'][0]
eid = next(iter(pw['elements']['map']))
pw['elements']['map'][eid]['interactions'] = [
    {'id': 'int_tos2', 'trigger': 'tap',
     'actions': [{'id': 'act_tos2', 'type': 'openUrl',
                  'payload': {'url': 'https://example.com/terms-of-service'}}]}]
check('a real /terms-of-service url still clears no-terms-link after tokenizing',
      len(of(run(c)[1], 'no-terms-link')) == 0)

print('\nproducts / catalog')

# catalog-not-fetched: no catalog was supplied at all, on a flow that binds products.
# The fix must not leak this script's own `--catalog` flag or the CLI command an
# agent would run to get one -- SKILL.md's rule that a client never sees a tool name.
no_cat = of(run(FLOW, catalog=None)[1], 'catalog-not-fetched')
check('catalog-not-fetched FIRES when no catalog is supplied to a product-binding flow',
      len(no_cat) == 1, no_cat)
check('catalog-not-fetched is a question, never a blocker',
      bool(no_cat) and no_cat[0]['severity'] == 'question')
check('...and its fix never names the --catalog flag or a CLI command',
      bool(no_cat) and '--catalog' not in no_cat[0]['fix']
      and 'adapty' not in no_cat[0]['fix'].lower(),
      no_cat[0]['fix'] if no_cat else '<no finding>')
check('catalog-not-fetched is SILENT when a catalog IS supplied',
      len(of(run(FLOW)[1], 'catalog-not-fetched')) == 0)
check('catalog-not-fetched is SILENT on a flow that binds nothing, even with no '
      'catalog supplied -- nothing about products needs verifying either way',
      len(of(run({'screens': [], 'locales': [], 'defaultLocale': 'en'},
                 catalog=None)[1], 'catalog-not-fetched')) == 0)

rc, findings = run(FLOW)
check('a bound product present in the catalog is SILENT',
      len(of(findings, 'product-not-in-catalog')) == 0)

# FIRES: rebind to a product id that is in no catalog
c = load()
for s in c['screens']:
    for eid, e in s['elements']['map'].items():
        if ((e.get('props') or {}).get('product') or {}).get('id'):
            e['props']['product']['id'] = 'ffffffff-0000-4000-8000-00000000ffff'
            break
_pnic = of(run(c)[1], 'product-not-in-catalog')
check('product-not-in-catalog FIRES', len(_pnic) == 1)
check('product-not-in-catalog is a blocker',
      bool(_pnic) and _pnic[0]['severity'] == 'blocker')

# store coverage is a QUESTION when stores are unknown, a BLOCKER when android is named
gaps_unknown = of(run(FLOW)[1], 'product-store-gap')
gaps_android = of(run(FLOW, stores='ios,android')[1], 'product-store-gap')
check('store gap is a question when the stores are unknown',
      gaps_unknown and all(f['severity'] == 'question' for f in gaps_unknown))
check('store gap becomes a blocker when android is declared',
      gaps_android and all(f['severity'] == 'blocker' for f in gaps_android))
check('store gap is SILENT when only ios is declared',
      len(of(run(FLOW, stores='ios')[1], 'product-store-gap')) == 0)

# base_plan_id null must be read only on a play_store entry
check('a null base_plan_id on an app_store entry stays SILENT',
      len(of(run(FLOW)[1], 'play-base-plan-missing')) == 0)

print('\nproducts / catalog: dedup arity and site naming')

# The fixture binds two elements to two DIFFERENT real products (el_076S, el_084S).
# Rebind both to the SAME missing product id: this must yield exactly ONE
# product-not-in-catalog finding (not two), and its message must name both sites --
# a user fixing the deduped finding must not be left unaware a second element binds
# the same broken product.
c = load()
pw = [s for s in c['screens'] if s['id'] == 'scr_paywall'][0]
bound_eids = [eid for eid, e in pw['elements']['map'].items()
              if ((e.get('props') or {}).get('product') or {}).get('id')]
check('fixture setup: exactly two elements bind a product', len(bound_eids) == 2,
      f'got {bound_eids}')
for eid in bound_eids:
    pw['elements']['map'][eid]['props']['product']['id'] = \
        'ffffffff-0000-4000-8000-00000000ffff'
dup_missing = of(run(c)[1], 'product-not-in-catalog')
check('the same missing product bound on two elements yields exactly ONE '
      'product-not-in-catalog finding', len(dup_missing) == 1,
      f'got {len(dup_missing)}')
check('...and its message names both binding sites',
      dup_missing and all(f'scr_paywall/{eid}' in dup_missing[0]['message']
                           for eid in bound_eids),
      dup_missing[0]['message'] if dup_missing else '<no finding>')

# Same shape for a check that was already deduping (product-store-gap) but was
# silently dropping every site after the first: bind BOTH elements to the same
# store-gap product (Pro Annual -- app_store only, no play_store entry in the
# fixture catalog) and confirm exactly one finding naming both sites.
c = load()
pw = [s for s in c['screens'] if s['id'] == 'scr_paywall'][0]
annual_id = [p['id'] for p in json.load(open(CATALOG)) if p.get('title') == 'Pro Annual'][0]
for eid in bound_eids:
    pw['elements']['map'][eid]['props']['product']['id'] = annual_id
dup_gap = of(run(c)[1], 'product-store-gap')
check('the same store-gap product bound on two elements yields exactly ONE '
      'product-store-gap finding', len(dup_gap) == 1, f'got {len(dup_gap)}')
check('...and its message names both binding sites',
      dup_gap and all(f'scr_paywall/{eid}' in dup_gap[0]['message']
                       for eid in bound_eids),
      dup_gap[0]['message'] if dup_gap else '<no finding>')

print('\nproducts / catalog: const-purchase product binding (C1)')
# A `const` purchase action binds a product with no `product` element and no card
# copy -- CLAUDE.md documents the shape. `bound_products` must see it: real fixture
# tabs-paywall.json binds three products this way, none of which exist in the
# catalog fixture -- previously this family was entirely blind to them.
rc_tabs, findings_tabs = run(os.path.join(FIX, 'tabs-paywall.json'))
CONST_IDS = ('64364f33-610c-4eb7-c19f-46b64b5dc59b',
             '134badab-bd2f-416c-0d7a-e04b4a1a029a',
             '097b40ac-92dd-41c3-403b-0923cb62c7d9')
missing = of(findings_tabs, 'product-not-in-catalog')
check('tabs-paywall.json FIRES product-not-in-catalog for each of its 3 '
      'const-purchase-bound products (one finding per product)',
      len(missing) == 3, f'got {len(missing)}: {missing}')
check('...and each finding names one of the const-bound product ids',
      all(any(pid in f['message'] for pid in CONST_IDS) for f in missing),
      missing)
check('tabs-paywall.json is NOT READY once its const-bound products are checked '
      'against the catalog (was READY, exit 0, before this fix)',
      rc_tabs == 1, f'rc={rc_tabs}')

# The report header's product count must include const-bound products too.
r_tabs_report = subprocess.run(
    [sys.executable, AUDIT, os.path.join(FIX, 'tabs-paywall.json'),
     '--catalog', CATALOG, '--report'], capture_output=True, text=True)
check('the report header counts const-bound products (3), not just element-bound '
      'ones (was omitted from the header before this fix)',
      '3 products' in r_tabs_report.stdout.splitlines()[1],
      r_tabs_report.stdout.splitlines()[:3])

# SILENT: a const-purchase binding to a product that DOES exist in the catalog, with
# a full store/access-level binding (Pro Monthly), must not fire any catalog check.
const_ok = {
    'screens': [{'id': 'scr_pay', 'elements': {'map': {
        'el_buy': {
            'type': 'text', 'props': {'content': {'values': {'en': 'Subscribe'}}},
            'interactions': [{'id': 'i_buy', 'trigger': 'tap', 'actions': [
                {'id': 'a_buy', 'type': 'purchase', 'payload': {'product': {
                    'type': 'const',
                    'value': {'id': 'fbc63856-bf3a-45d1-7bee-dd4bcb54b10a'}}}}]}]},
    }}}],
    'locales': [], 'defaultLocale': 'en'}
const_ok_findings = run(const_ok)[1] or []
check('a const-purchase binding to a real, fully-bound catalog product '
      '(Pro Monthly) stays SILENT across the whole products family',
      not any(f['family'] == 'products' for f in const_ok_findings),
      [f['check'] for f in const_ok_findings if f['family'] == 'products'])

# The dedup/site-naming discipline (already proven for the element shape above) must
# hold for the const shape too -- and the two shapes must be seen INDEPENDENTLY when
# they land on the very same element (one `product` prop, one `const` purchase
# action, two different product ids).
c = load()
pw = [s for s in c['screens'] if s['id'] == 'scr_paywall'][0]
first_prod_eid = next(eid for eid, e in pw['elements']['map'].items()
                       if ((e.get('props') or {}).get('product') or {}).get('id'))
pw['elements']['map'][first_prod_eid].setdefault('interactions', []).append(
    {'id': 'int_const_extra', 'trigger': 'tap', 'actions': [
        {'id': 'act_const_extra', 'type': 'purchase', 'payload': {'product': {
            'type': 'const',
            'value': {'id': 'ffffffff-0000-4000-8000-00000000ffff'}}}}]})
mixed = of(run(c)[1], 'product-not-in-catalog')
check('an element binding one product via `props.product` (real, silent) and a '
      'DIFFERENT missing product via a `const` purchase action on the SAME element '
      'reports the const one (both shapes seen independently)',
      len(mixed) == 1
      and 'ffffffff-0000-4000-8000-00000000ffff' in mixed[0]['message']
      and mixed[0]['element'] == first_prod_eid,
      mixed)

# period-claim-mismatch and price-integrity stay ELEMENT-SCOPED on purpose -- a
# `const` purchase action has no card copy to read, so neither check may ever see
# this shape. A flow whose only binding is a const purchase, with copy nearby that
# would mismatch if this check were catalog-scoped like `product-not-in-catalog`,
# must stay silent on both.
const_period = {
    'screens': [{'id': 'scr_pay', 'elements': {'map': {
        'el_buy': {
            'type': 'text', 'props': {'content': {'values': {'en': 'Yearly Plan'}}},
            'interactions': [{'id': 'i_buy', 'trigger': 'tap', 'actions': [
                {'id': 'a_buy', 'type': 'purchase', 'payload': {'product': {
                    'type': 'const',
                    'value': {'id': 'fbc63856-bf3a-45d1-7bee-dd4bcb54b10a'}}}}]}]},
    }}}],
    'locales': [], 'defaultLocale': 'en'}
const_period_findings = run(const_period)[1]
check('period-claim-mismatch stays SILENT on a const-purchase binding even when '
      'nearby copy names a different period ("Yearly Plan" beside a const purchase '
      'of the monthly product) -- element-scoped, never sees this shape',
      len(of(const_period_findings, 'period-claim-mismatch')) == 0,
      const_period_findings)
check('hardcoded-price and foreign-price-variable are also SILENT on a '
      'const-purchase-only flow (no card copy to check)',
      len(of(const_period_findings, 'hardcoded-price')) == 0
      and len(of(const_period_findings, 'foreign-price-variable')) == 0,
      const_period_findings)

print('\nproducts / period claim')

# the vocabulary, tested directly through the four traps that broke the naive version
CASES = [
    ('Annual | $0 during trial — then $49.99 /year | 7 Days Trial', {'annual'},
     '7 Days Trial must not read as weekly'),
    ('Annual | Billed once a year | $4.16 /mo | $49.99 a year', {'annual', 'monthly'},
     '"once a year" must not read as lifetime'),
    ('Individual | 12 mo • $79.99 | $6.67 / MO', {'annual', 'monthly'},
     '"12 mo" must read as annual, not only monthly'),
    ('Monthly | Cancel any time', {'monthly'}, 'plain monthly'),
    ('Yearly | Best value — 12 months', {'annual'}, 'plain annual'),
    # Hyphenated multiplied units: `\s*` never matches a hyphen, so these all fell
    # through to the bare-unit rule below and read as monthly/weekly instead of
    # annual/quarterly. Real copy hyphenates routinely.
    ('12-month plan', {'annual'}, '"12-month" must read as annual, not monthly'),
    ('3-month plan', {'quarterly'}, '"3-month" must read as quarterly, not monthly'),
    ('12-mo plan', {'annual'}, '"12-mo" must read as annual, not monthly'),
    ('52-week plan', {'annual'}, '"52-week" must read as annual, not weekly'),
    ('12-months', {'annual'}, '"12-months" must resolve to annual, not vanish'),
    # Substring guards on the bare monthly/weekly rules -- adding the plural must not
    # reopen a false match inside an unrelated word.
    ('bimonthly', set(), '"bimonthly" must not resolve to monthly (substring trap)'),
    ('mobile', set(), '"mobile" must not resolve to monthly (substring trap)'),
    ('weekend', set(), '"weekend" must not resolve to weekly (substring trap)'),
    ('martyr', set(), '"martyr" must not resolve to annual via "yr" (substring trap)'),
    # Regression: the destructive consumption must still eat "12 months" whole via the
    # annual multiplied-unit rule, leaving no stray "months" for the bare rule to catch.
    ('12 months', {'annual'}, '"12 months" must resolve to annual only, no stray monthly'),
]
rc, findings = run(FLOW)
check('period-claim is SILENT on the fixture (both cards name the right period)',
      len(of(findings, 'period-claim-mismatch')) == 0)

# FIRES: rebind the annual card to the monthly product, leaving "Yearly" copy in place
c = load()
cat = json.load(open(CATALOG))
monthly = [p['id'] for p in cat if p.get('period') == 'monthly'][0]
pw = [s for s in c['screens'] if s['id'] == 'scr_paywall'][0]
for eid, e in pw['elements']['map'].items():
    if e.get('caption') == 'Plan Yearly':
        e['props']['product']['id'] = monthly
        break
mism = of(run(c)[1], 'period-claim-mismatch')
check('period-claim FIRES when a "Yearly" card is bound to a monthly product',
      len(mism) == 1, f'got {len(mism)}')
check('period-claim is a blocker', mism and mism[0]['severity'] == 'blocker')

# SILENT: a card naming BOTH periods is the equivalent-price pattern
c = load()
pw = [s for s in c['screens'] if s['id'] == 'scr_paywall'][0]
for eid, e in pw['elements']['map'].items():
    if e.get('caption') == 'Plan Monthly':
        for cid, ce in pw['elements']['map'].items():
            if ce.get('type') == 'text':
                ce.setdefault('props', {})['content'] = {'values': {
                    l: '$4.16 /mo billed 12 mo' for l in ('en', 'sr', 'sr-Latn')}}
                break
        break
check('a card naming both periods stays SILENT (equivalent-price pattern)',
      len(of(run(c)[1], 'period-claim-mismatch')) == 0)

print('\nproducts / period claim: billing-context requirement (I3)')
# Local helpers duplicating `_find_hier_node`/`_descendants` (defined further down,
# in the price-integrity section) -- kept local rather than reordering the file, since
# this section runs first and this is a flat script, not a module of importable defs.
def _find_node_i3(node, target):
    if node.get('id') == target:
        return node
    for ch in (node.get('children') or []):
        got = _find_node_i3(ch, target)
        if got:
            return got
    return None


def _descendants_i3(node):
    ids = [node.get('id')]
    for ch in (node.get('children') or []):
        ids += _descendants_i3(ch)
    return [i for i in ids if i]


# Reproduced: rewriting el_076S (bound to Pro Annual) to "Pro | Weekly progress
# reports" read as a WEEKLY period claim purely because the benefit sentence
# contains the word "weekly" -- the card's real period is annual and its own text
# no longer names it at all. Must now be SILENT: no period word appears in a
# price/billing context.
c = load()
pw = [s for s in c['screens'] if s['id'] == 'scr_paywall'][0]
annual_eid = next(eid for eid, e in pw['elements']['map'].items()
                   if e.get('caption') == 'Plan Yearly')
card_node = _find_node_i3(pw['elements']['hierarchy'], annual_eid)
check('fixture setup: found the annual card\'s hierarchy node', card_node is not None)
for _eid in _descendants_i3(card_node):
    _el = pw['elements']['map'].get(_eid, {})
    if _el.get('type') == 'text':
        _el.setdefault('props', {})['content'] = {
            'values': {l: 'Pro | Weekly progress reports'
                       for l in ('en', 'sr', 'sr-Latn')}}
        break
check('period-claim-mismatch stays SILENT when a card\'s copy is rewritten to '
      'benefit text that merely contains a period word ("Pro | Weekly progress '
      'reports" on the annual card) -- was a false BLOCKER before this fix',
      len(of(run(c)[1], 'period-claim-mismatch')) == 0,
      of(run(c)[1], 'period-claim-mismatch'))

# The three other reproduced false positives, tested directly against the vocabulary
# function (the same level CASES above already exercises).
FALSE_POSITIVE_PERIODS = (
    ('Cancel anytime, no monthly fees', set()),
    ('Save 50% a year', set()),
    ('Your monthly report', set()),
)
CASES += [(text, want, f'{text!r} must not read as a period claim (I3)')
          for text, want in FALSE_POSITIVE_PERIODS]

# A GENUINE mismatch must still fire after the context restriction -- rebind the
# real "Yearly | Best value — 12 months" card (bare "Yearly" label, no benefit
# sentence rewrite) to the monthly product. This is the same rebind as the existing
# period-claim test above; re-asserted here under the I3 heading to pin that the
# context requirement did not also silence the real defect.
c = load()
cat = json.load(open(CATALOG))
monthly = [p['id'] for p in cat if p.get('period') == 'monthly'][0]
pw = [s for s in c['screens'] if s['id'] == 'scr_paywall'][0]
for eid, e in pw['elements']['map'].items():
    if e.get('caption') == 'Plan Yearly':
        e['props']['product']['id'] = monthly
        break
genuine_mism = of(run(c)[1], 'period-claim-mismatch')
check('a genuine mismatch (bare "Yearly" label bound to the monthly product) still '
      'FIRES a blocker after the billing-context restriction',
      len(genuine_mism) == 1 and genuine_mism[0]['severity'] == 'blocker',
      genuine_mism)

print('\nproducts / price integrity')
rc, findings = run(FLOW)
check('foreign-price-variable is SILENT on the fixture (each card cites its own product)',
      len(of(findings, 'foreign-price-variable')) == 0)
check('hardcoded-price is SILENT on the fixture (both cards use price variables)',
      len(of(findings, 'hardcoded-price')) == 0)

# FIRES: rebind one card, leaving its price variable pointing at the old product
c = load()
cat = json.load(open(CATALOG))
other = [p['id'] for p in cat if p.get('period') == 'weekly'][0]
pw = [s for s in c['screens'] if s['id'] == 'scr_paywall'][0]
for eid, e in pw['elements']['map'].items():
    if e.get('caption') == 'Plan Monthly':
        e['props']['product']['id'] = other
        break
check('foreign-price-variable FIRES when a card cites another product\'s price',
      len(of(run(c)[1], 'foreign-price-variable')) == 1)

# Arity, not presence: a card citing a foreign price variable ALONGSIDE its own is the
# was/now comparison pattern (measured on a real shipped card: onboarding-quiz-
# paywall.json's el_8rfwhBiXQL sells its own product AND shows a struck-through rate
# from another plan) and must stay silent. Only a card with NO reference to its own
# product's price variable is the real defect.
MONTHLY_ID = 'fbc63856-bf3a-45d1-7bee-dd4bcb54b10a'
YEARLY_ID = '6cdd73d5-bdb2-4b2e-c207-784fbcb2f408'


def _find_price_text_eid(pw, product_id):
    for eid, e in pw['elements']['map'].items():
        if e.get('type') == 'text' and product_id in json.dumps(
                (e.get('props') or {}).get('content')):
            return eid
    return None


def _find_hier_node(node, target):
    """Find `target`'s node in a screen's `elements.hierarchy` tree, for tests that
    need to attach a new sibling element into a real card's subtree."""
    if node.get('id') == target:
        return node
    for ch in (node.get('children') or []):
        got = _find_hier_node(ch, target)
        if got:
            return got
    return None


c = load()
pw = [s for s in c['screens'] if s['id'] == 'scr_paywall'][0]
price_eid = _find_price_text_eid(pw, MONTHLY_ID)
check('fixture setup: found Plan Monthly\'s own price text element',
      price_eid is not None)
own_content = pw['elements']['map'][price_eid]['props']['content']
was_node = {'type': 'paragraph', 'content': [
    {'type': 'variable', 'attrs': {'variableId': f'{YEARLY_ID}.prod_price_per_month'}}]}
for loc, vals in list(own_content['values'].items()):
    own_content['values'][loc] = [was_node] + list(vals)
check('foreign-price-variable stays SILENT when the card ALSO cites its own '
      'product (was/now comparison pattern)',
      len(of(run(c)[1], 'foreign-price-variable')) == 0)

c = load()
pw = [s for s in c['screens'] if s['id'] == 'scr_paywall'][0]
price_eid = _find_price_text_eid(pw, MONTHLY_ID)
own_content = pw['elements']['map'][price_eid]['props']['content']
for loc in list(own_content['values']):
    own_content['values'][loc] = [{'type': 'paragraph', 'content': [
        {'type': 'variable',
         'attrs': {'variableId': f'{YEARLY_ID}.prod_price_per_month'}}]}]
foreign_only = of(run(c)[1], 'foreign-price-variable')
check('foreign-price-variable FIRES when the card cites ONLY a foreign price '
      'variable, none of its own', len(foreign_only) == 1, f'got {len(foreign_only)}')
check('foreign-price-variable (own reference removed) is a blocker',
      foreign_only and foreign_only[0]['severity'] == 'blocker')

print('\nproducts / price integrity: six-fixture foreign-price-variable calibration')
# `foreign-price-variable` must be SILENT on every tracked fixture -- including
# onboarding-quiz-paywall.json's el_8rfwhBiXQL, which was the measured false positive
# this fix was written to close. `hardcoded-price` and `period-claim-mismatch` are
# unaffected by this change and must remain silent on all six too.
for _name in ('comparison-paywall.json', 'onboarding-multilocale.json',
              'onboarding-quiz-paywall.json', 'tabs-paywall.json',
              'timeline-anchored.json', 'vpn-timer-draft.json'):
    _findings = run(os.path.join(FIX, _name))[1]
    for _chk in ('foreign-price-variable', 'hardcoded-price', 'period-claim-mismatch'):
        check(f'{_name} is SILENT on {_chk}', len(of(_findings, _chk)) == 0,
              f'got {len(of(_findings, _chk))}')

# FIRES: replace a price variable with a currency literal
c = load()
pw = [s for s in c['screens'] if s['id'] == 'scr_paywall'][0]
for eid, e in pw['elements']['map'].items():
    cont = (e.get('props') or {}).get('content')
    if isinstance(cont, dict) and 'values' in cont:
        blob = json.dumps(cont['values'].get('en'))
        if 'variable' in blob:
            e['props']['content'] = {'values': {
                l: '$79.99 / year' for l in ('en', 'sr', 'sr-Latn')}}
            break
hard = of(run(c)[1], 'hardcoded-price')
check('hardcoded-price FIRES on a currency literal with no price variable', len(hard) >= 1)

# SILENT: a zero literal alongside a real variable is legitimate ("$0 during trial")
c = load()
pw = [s for s in c['screens'] if s['id'] == 'scr_paywall'][0]
for eid, e in pw['elements']['map'].items():
    if e.get('type') == 'text':
        e.setdefault('props', {})['content'] = {'values': {
            l: '$0 during trial' for l in ('en', 'sr', 'sr-Latn')}}
        break
check('a $0 literal stays SILENT', len(of(run(c)[1], 'hardcoded-price')) == 0)

print('\nproducts / price integrity: hardcoded-price is ELEMENT-scoped, not card-scoped')
# JOB 1 fix: `check_price_integrity` used to compute one text blob for the whole card
# and suppress `hardcoded-price` if the CARD referenced any price variable anywhere.
# Measured false negative: keep the annual card's real price variable, add a sibling
# text element reading "was $99.99" -- 0 findings, fabricated price ships. The fix
# judges each literal against the ELEMENT that carries it.

# FIRES: annual card keeps its real price variable; a sibling element fabricates a
# "was $99.99" literal with no variable of its own.
c = load()
pw = [s for s in c['screens'] if s['id'] == 'scr_paywall'][0]
annual_eid = next(eid for eid, e in pw['elements']['map'].items()
                   if e.get('caption') == 'Plan Yearly')
was_eid = 'el_wasFabricatedTest'
pw['elements']['map'][was_eid] = {
    'id': was_eid, 'type': 'text',
    'props': {'content': {'values': {
        l: 'was $99.99' for l in ('en', 'sr', 'sr-Latn')}}}}
card_node = _find_hier_node(pw['elements']['hierarchy'], annual_eid)
check('fixture setup: found the annual card\'s hierarchy node', card_node is not None)
card_node.setdefault('children', []).append({'id': was_eid, 'children': []})
sibling_hard = of(run(c)[1], 'hardcoded-price')
check('hardcoded-price FIRES on a sibling literal even though the card carries a '
      'real price variable elsewhere (element-scoped, not card-scoped)',
      len(sibling_hard) == 1, f'got {len(sibling_hard)}')
check('...anchored at the element that carries the literal, not the card element',
      bool(sibling_hard) and sibling_hard[0]['element'] == was_eid,
      sibling_hard[0]['element'] if sibling_hard else '<no finding>')
check('...and it is reported as a blocker',
      bool(sibling_hard) and sibling_hard[0]['severity'] == 'blocker')

# A reproduced false positive, not a hypothetical: a savings figure written beside
# (never inside) the price-variable element still trips `hardcoded-price`, because
# the guard is element-scoped, not card-scoped -- CLAUDE.md's own known-limitations
# entry had this backwards ("beside" read as the SILENT case; it is the one that
# FIRES). The message must not assert the literal IS the price -- "Save $20" is a
# savings figure, not a price -- so it is worded as a currency amount written into
# the copy, letting the reader judge, never "the price $20".
c = load()
pw = [s for s in c['screens'] if s['id'] == 'scr_paywall'][0]
annual_eid = next(eid for eid, e in pw['elements']['map'].items()
                   if e.get('caption') == 'Plan Yearly')
save_eid = 'el_saveTwentyTest'
pw['elements']['map'][save_eid] = {
    'id': save_eid, 'type': 'text',
    'props': {'content': {'values': {
        l: 'Yearly | Save $20 vs monthly' for l in ('en', 'sr', 'sr-Latn')}}}}
card_node = _find_hier_node(pw['elements']['hierarchy'], annual_eid)
card_node.setdefault('children', []).append({'id': save_eid, 'children': []})
save_hard = of(run(c)[1], 'hardcoded-price')
check('hardcoded-price FIRES on a sibling savings figure ("Save $20 vs monthly") '
      'beside the card\'s real price variable -- a reproduced false positive, not '
      'silenced by the same-element guard',
      len(save_hard) == 1 and save_hard[0]['element'] == save_eid,
      save_hard)
check('...and its message never asserts the amount IS the price -- it says a '
      'currency amount is written into the copy, and lets the reader judge',
      bool(save_hard)
      and 'currency amount' in save_hard[0]['message']
      and '$20' in save_hard[0]['message']
      and 'the price $20' not in save_hard[0]['message'],
      save_hard[0]['message'] if save_hard else '<no finding>')

# SILENT: same setup, but the sibling's only literal is the legitimate zero amount
# ("$0 during trial"), alongside the card's real price variable elsewhere.
c = load()
pw = [s for s in c['screens'] if s['id'] == 'scr_paywall'][0]
annual_eid = next(eid for eid, e in pw['elements']['map'].items()
                   if e.get('caption') == 'Plan Yearly')
zero_eid = 'el_zeroSiblingTest'
pw['elements']['map'][zero_eid] = {
    'id': zero_eid, 'type': 'text',
    'props': {'content': {'values': {
        l: '$0 during trial' for l in ('en', 'sr', 'sr-Latn')}}}}
card_node = _find_hier_node(pw['elements']['hierarchy'], annual_eid)
card_node.setdefault('children', []).append({'id': zero_eid, 'children': []})
check('a $0 sibling stays SILENT under element scoping, with a real price variable '
      'elsewhere in the same card',
      len(of(run(c)[1], 'hardcoded-price')) == 0)

# SILENT (brief regression): the untouched fixture, where both cards legitimately use
# price variables and carry no literal at all, must still report nothing.
check('hardcoded-price is still SILENT on the untouched fixture '
      '(both cards use price variables, no literals)',
      len(of(run(FLOW)[1], 'hardcoded-price')) == 0)

print('\nlocalization')
rc, findings = run(FLOW)
check('empty-translation is SILENT on the fixture', len(of(findings, 'empty-translation')) == 0)
unt = of(findings, 'untranslated')
# RULING (overrides the brief): the fixture's 2 untranslated values ("Nimbus",
# "Nimbus Plus") are identical in BOTH non-base locales (sr and sr-Latn), so a
# per-locale finding would emit 2 -- this repeats the coverage table instead of
# adding to it. `check_localization` emits exactly ONE grouped finding for the whole
# flow, carrying the per-locale counts and up to 4 examples in its message.
check('untranslated FIRES once, grouped, for the brand name', len(unt) == 1, f'got {len(unt)}')
check('untranslated is a risk, never a blocker', bool(unt) and unt[0]['severity'] == 'risk')
check('untranslated names its examples', bool(unt) and 'Nimbus' in unt[0]['message'])

# FIRES: empty a translation -- find the first `values` map carrying both `en` and
# `sr`, and replace its `sr` value with a paragraph holding an empty `text` node. An
# empty text node is NOT substantive (see `SUBSTANTIVE_NODES`), so this must count as
# empty rather than as present-with-no-text.
c = load()
done = False


def _empty(o):
    global done
    if done:
        return
    if isinstance(o, dict):
        if 'values' in o and isinstance(o['values'], dict) and {'en', 'sr'} <= set(o['values']):
            o['values']['sr'] = [{'type': 'paragraph',
                                  'content': [{'type': 'text', 'text': ''}]}]
            done = True
            return
        for v in o.values():
            _empty(v)
    elif isinstance(o, list):
        for v in o:
            _empty(v)


_empty(c)
check('fixture setup: an empty translation was actually injected', done)
empty_findings = run(c)[1]
_empty_tr = of(empty_findings, 'empty-translation')
check('empty-translation FIRES on an emptied value',
      len(_empty_tr) == 1,
      f'got {len(_empty_tr)}')
check('empty-translation is a blocker',
      bool(_empty_tr) and _empty_tr[0]['severity'] == 'blocker')

# SILENT: a price element has no literal text by construction -- a variable-only
# field must never be reported as an empty translation.
check('a variable-only field is not reported empty',
      len(of(run(FLOW)[1], 'empty-translation')) == 0)

# SILENT: CONDITIONAL TEXT. A personalization payoff's copy is a `switch` nested inside
# the locale, not a block array, so a richtext-shaped reader sees nothing there. Measured
# firing a BLOCKER on three legitimate fields of a real onboarding flow before the fix --
# the third instance of this trap, after variable-only content and per-locale images.
def _switch_val(text):
    return {'_localizable': True, 'values': {'en': {
        'type': 'switch',
        'cases': [[{'type': '==', 'left': {'type': 'var',
                                           'variableId': 'goal.selectedOptionId'},
                    'right': {'type': 'const', 'value': 'a'}},
                   {'type': 'const', 'value': [{'type': 'paragraph', 'content': [
                       {'type': 'text', 'text': text, 'attrs': {}}]}]}]],
        'default': {'type': 'const', 'value': [{'type': 'paragraph', 'content': [
            {'type': 'text', 'text': text, 'attrs': {}}]}]}}}}


c = load(FLOW)
_target = None
for _s in c['screens']:
    for _e in _s['elements']['map'].values():
        if _e.get('type') == 'text' and isinstance(_e['props'].get('content'), dict):
            _target = _e
            break
    if _target:
        break
_target['props']['content'] = _switch_val('Your plan for falling asleep faster')
check('fixture setup: a conditional-text value was actually injected', _target is not None)
check('conditional text is SILENT on empty-translation',
      len(of(run(c)[1], 'empty-translation')) == 0,
      f'got {len(of(run(c)[1], "empty-translation"))}')

# FIRES: the branches are recursed rather than the type merely accepted, so a switch
# whose branches are all empty is still an empty translation.
c = load(FLOW)
_target2 = None
for _s in c['screens']:
    for _e in _s['elements']['map'].values():
        if _e.get('type') == 'text' and isinstance(_e['props'].get('content'), dict):
            _target2 = _e
            break
    if _target2:
        break
_target2['props']['content'] = _switch_val('')
check('an all-empty conditional-text switch still FIRES',
      len(of(run(c)[1], 'empty-translation')) == 1,
      f'got {len(of(run(c)[1], "empty-translation"))}')

print('\nlocalization: delegation to verify-config.py (Step 5)')
# A MISSING locale key (one field, present in some locales and absent in this one) is
# already reported by verify-config.py, per field. `locale_coverage` may COUNT it for
# the table, but `check_localization` must NOT turn it into a finding of its own --
# that would duplicate verify-config.py's report.
VERIFY_CONFIG = os.path.join(ROOT, 'skills', 'flow-generator', 'references',
                             'verify-config.py')
c = load()
done = False


def _drop_key(o):
    global done
    if done:
        return
    if isinstance(o, dict):
        v = o.get('values')
        if isinstance(v, dict) and 'sr' in v and 'en' in v:
            del v['sr']
            done = True
            return
        for x in o.values():
            _drop_key(x)
    elif isinstance(o, list):
        for x in o:
            _drop_key(x)


_drop_key(c)
check('fixture setup: a locale key was actually dropped', done)
with tempfile.TemporaryDirectory() as tmp:
    missing_key_path = os.path.join(tmp, 'missing-key.json')
    json.dump(c, open(missing_key_path, 'w'))
    verify_out = subprocess.run(
        [sys.executable, VERIFY_CONFIG, missing_key_path],
        capture_output=True, text=True)
check('verify-config.py reports the missing key itself',
      'no value for' in (verify_out.stdout + verify_out.stderr),
      (verify_out.stdout + verify_out.stderr)[:300])
loc_findings = [f for f in (run(c)[1] or []) if f['family'] == 'localization']
check('audit-flow.py does not duplicate a missing-key finding of its own '
      '(no `missing`-based check present for a single dropped key)',
      not any(f['check'] in ('locale-entirely-empty',) for f in loc_findings)
      and len(of(loc_findings, 'empty-translation')) == 0,
      [f['check'] for f in loc_findings])

print('\nlocalization: six-fixture calibration')
# `empty-translation` must be SILENT on every real, single-locale fixture. Measured
# false positive before `_has_content` learned the image-value shape: a per-locale
# IMAGE value is a bare `{'id', 'url'}` object with no `type` discriminator at all, so
# the richtext-only walk (`node_kinds`/`flat_text`) saw nothing and called a real,
# filled image asset empty -- on onboarding-quiz-paywall.json and vpn-timer-draft.json.
for _name in ('comparison-paywall.json', 'onboarding-quiz-paywall.json',
              'tabs-paywall.json', 'timeline-anchored.json', 'vpn-timer-draft.json'):
    _findings = run(os.path.join(FIX, _name))[1]
    check(f'{_name} is SILENT on empty-translation',
          len(of(_findings, 'empty-translation')) == 0,
          f'got {len(of(_findings, "empty-translation"))}')
    check(f'{_name} is SILENT on locale-entirely-empty',
          len(of(_findings, 'locale-entirely-empty')) == 0,
          f'got {len(of(_findings, "locale-entirely-empty"))}')

print('\nperiod vocabulary (direct)')
VOCAB = os.path.join(ROOT, 'skills', 'flow-audit', 'references', 'audit-flow.py')
for text, want, why in CASES:
    got = subprocess.run(
        [sys.executable, '-c',
         'import importlib.util,sys,json;'
         f'spec=importlib.util.spec_from_file_location("a", {VOCAB!r});'
         'm=importlib.util.module_from_spec(spec);'
         'sys.dont_write_bytecode=True;spec.loader.exec_module(m);'
         f'print(json.dumps(sorted(m.period_terms({text!r}))))'],
        capture_output=True, text=True).stdout.strip()
    check(why, got == json.dumps(sorted(want)), f'{text!r} -> {got}, wanted {sorted(want)}')

print('\nplaceholders')
rc, findings = run(FLOW)
check('placeholder-copy is SILENT on the fixture', len(of(findings, 'placeholder-copy')) == 0)

for text in ('Lorem ipsum dolor sit amet', 'TODO write this', 'Your headline here'):
    c = load()
    for s in c['screens']:
        for eid, e in s['elements']['map'].items():
            if e.get('type') == 'text':
                e.setdefault('props', {})['content'] = {
                    'values': {l: text for l in ('en', 'sr', 'sr-Latn')}}
                break
        break
    check(f'placeholder-copy FIRES on {text!r}',
          len(of(run(c)[1], 'placeholder-copy')) == 1)

# SILENT: real copy that merely contains a placeholder-ish word
c = load()
for s in c['screens']:
    for eid, e in s['elements']['map'].items():
        if e.get('type') == 'text':
            e.setdefault('props', {})['content'] = {'values': {
                l: 'Sample a new workout every week' for l in ('en', 'sr', 'sr-Latn')}}
            break
    break
check('real copy containing "sample" stays SILENT',
      len(of(run(c)[1], 'placeholder-copy')) == 0)

print('\nvariables')
rc, findings = run(FLOW)
check('variable-no-consumer is SILENT on the fixture', len(of(findings, 'variable-no-consumer')) == 0)

# FIRES: a `setVariable` action whose target is never read anywhere else in the flow.
c = load()
s0 = c['screens'][0]
eid0 = next(iter(s0['elements']['map']))
s0['elements']['map'][eid0]['interactions'] = [
    {'id': 'int_test', 'trigger': 'tap', 'actions': [
        {'id': 'act_test', 'type': 'setVariable',
         'payload': {'id': 'test.orphan', 'value': {'type': 'const', 'value': 'x'}}}]}]
check('variable-no-consumer FIRES on an orphaned setVariable',
      len(of(run(c)[1], 'variable-no-consumer')) == 1)

# SILENT: the same producer, plus a real consumer (a `var` predicate) elsewhere in the
# same flow -- proves the check reads structurally rather than by a raw substring count,
# which is what the brief's first draft did and what made it too crude to calibrate.
c2 = load()
s0 = c2['screens'][0]
eid0 = next(iter(s0['elements']['map']))
s0['elements']['map'][eid0]['interactions'] = [
    {'id': 'int_test', 'trigger': 'tap', 'actions': [
        {'id': 'act_test', 'type': 'setVariable',
         'payload': {'id': 'test.orphan', 'value': {'type': 'const', 'value': 'x'}}},
        {'id': 'act_test2', 'type': 'conditional', 'payload': {
            'type': 'switch', 'cases': [[
                {'type': '&&', 'predicates': [
                    {'left': {'type': 'var', 'variableId': 'test.orphan'},
                     'type': '==', 'right': {'type': 'const', 'value': 'x'}}]},
                {'type': 'const', 'value': [{'id': '', 'type': 'nothing'}]}]],
            'default': {'type': 'const', 'value': [{'id': '', 'type': 'nothing'}]}}}]}]
check('variable-no-consumer stays SILENT when a predicate elsewhere reads the variable',
      len(of(run(c2)[1], 'variable-no-consumer')) == 0)

print('\nplaceholders + variables: six-fixture calibration')
# `onboarding-multilocale.json` (== FLOW) is covered by the "is SILENT on the fixture"
# checks above; this loop covers the other five real, shipped exports. A firing here is
# a false positive to fix, never a finding to report -- see the narrowing note on
# `check_variables` for why the `groupId`-as-producer idea from the brief's first draft
# was dropped rather than patched: `tabs-paywall.json`'s `tabs` group (3 members, a
# `tab-item` selection with no readable variable at all) and
# `onboarding-multilocale.json`'s own `notify` group (1 member, a plain toggle) both
# would have fired under every consumer-detection method tried, alongside real,
# genuinely-consumed groups (`products`/`plans`/`quiz`) that must not.
for _name in ('comparison-paywall.json', 'onboarding-quiz-paywall.json', 'tabs-paywall.json',
              'timeline-anchored.json', 'vpn-timer-draft.json'):
    _findings = run(os.path.join(FIX, _name))[1]
    check(f'{_name} is SILENT on placeholder-copy',
          len(of(_findings, 'placeholder-copy')) == 0,
          f'got {len(of(_findings, "placeholder-copy"))}')
    check(f'{_name} is SILENT on variable-no-consumer',
          len(of(_findings, 'variable-no-consumer')) == 0,
          f'got {len(of(_findings, "variable-no-consumer"))}')

print('\nreport')
r = subprocess.run([sys.executable, AUDIT, FLOW, '--catalog', CATALOG, '--report',
                    '--name', 'Nimbus onboarding', '--flow-id', 'abc', '--status',
                    'publication_failed'], capture_output=True, text=True)
txt = r.stdout
check('the verdict is the first non-empty line',
      txt.strip().splitlines()[0].startswith('Flow:'))
check('the verdict line names NOT READY and a blocker count',
      'NOT READY FOR PRODUCTION' in txt and 'blocker' in txt)
check('a clickable flow url is printed, not a bare uuid',
      'https://app.adapty.io/flows/abc/builder' in txt)
check('BEFORE YOU SHIP reminds about the placement link',
      'BEFORE YOU SHIP' in txt and 'placement' in txt)
check('there is no gate-status section',
      'verify-config' not in txt and 'GATES' not in txt)
check('the locale coverage table is printed', 'LOCALE COVERAGE' in txt
      and 'sr-Latn' in txt)
check('report mode still exits 1 when blockers fired', r.returncode == 1)
check('the closing offer hands blockers to flow-generator',
      'flow-generator' in txt and 'Want me to fix' in txt)

# DEFECT 1 -- the verdict line is short family labels, never a slice of full finding
# prose. Extract it (the first line after 'Flow:'/url/stats/blank) and check its shape
# rather than its exact wording, since the label set is allowed to evolve.
verdict_line = next(l for l in txt.splitlines() if l.startswith('NOT READY'))
check('the verdict line is comfortably short', len(verdict_line) < 120,
      f'{len(verdict_line)} chars: {verdict_line!r}')
check('the verdict line is not built from raw finding messages (no ";")',
      ';' not in verdict_line, verdict_line)
check('the verdict line uses short labels, not colon-clauses',
      verdict_line.count(':') <= 1, verdict_line)

# Regression: a label that already reads as a negation ("no legal links", "no restore
# action") must never get a "<count> " prefix -- two independent checks (no-terms-link,
# no-privacy-link) share the one "no legal links" label, and prefixing a count onto it
# produced the ungrammatical "2 no legal links" on real fixtures. A countable-noun label
# ("product not in catalog") still gets the count, correctly pluralized.
#
# comparison-paywall.json USED to exercise this (its three sibling dead-affordance
# elements merged into three separate findings, two of which landed on "no legal
# links"), but Task 15's sibling collapse (DEFECT 1) now merges all three into ONE
# finding, so that fixture no longer doubles the label. The regression this guards
# still matters -- two SEPARATE merged findings landing on the same negation label --
# so it is reproduced directly: "Terms" and "Privacy" under two DIFFERENT (unwired)
# parents, so they merge with no-terms-link and no-privacy-link SEPARATELY rather
# than collapsing together, and both findings' label is the same "no legal links".
two_legal_gaps = {
    'screens': [{'id': 'scr_pay', 'elements': {
        'map': {
            'el_buy': {
                'type': 'text', 'props': {'content': {'values': {'en': 'Continue'}}},
                'interactions': [{'id': 'i_buy', 'trigger': 'tap', 'actions': [
                    {'id': 'a_buy', 'type': 'purchase', 'payload': {}}]}]},
            'el_terms': {
                'type': 'text', 'props': {'content': {'values': {'en': 'Terms'}}}},
            'el_privacy': {
                'type': 'text', 'props': {'content': {'values': {'en': 'Privacy'}}}},
        },
        'hierarchy': {'id': 'el_root', 'children': [
            {'id': 'el_buy', 'children': []},
            {'id': 'el_group_a', 'children': [{'id': 'el_terms', 'children': []}]},
            {'id': 'el_group_b', 'children': [{'id': 'el_privacy', 'children': []}]},
        ]},
    }}],
    'locales': [], 'defaultLocale': 'en'}
with tempfile.TemporaryDirectory() as tmp:
    _tlg_path = os.path.join(tmp, 'two_legal_gaps.json')
    json.dump(two_legal_gaps, open(_tlg_path, 'w'))
    _rc_tlg, _findings_tlg = run(_tlg_path, catalog=None)
    _r_cmp = subprocess.run([sys.executable, AUDIT, _tlg_path, '--report'],
                            capture_output=True, text=True)
check('fixture setup: two dead-affordance findings (Terms, Privacy) under different '
      'parents, both merging with a legal-link check',
      len(of(_findings_tlg, 'dead-affordance')) == 2, _findings_tlg)
_cmp_verdict = next(l for l in _r_cmp.stdout.splitlines() if l.startswith('NOT READY'))
check('a doubled negation label ("no legal links", from two SEPARATE merged '
      'findings) is never count-prefixed',
      'no legal links' in _cmp_verdict and '2 no legal links' not in _cmp_verdict,
      _cmp_verdict)

for _fname in sorted(os.listdir(FIX)):
    if not _fname.endswith('.json'):
        continue
    _r_all = subprocess.run([sys.executable, AUDIT, os.path.join(FIX, _fname),
                              '--catalog', CATALOG, '--report'],
                             capture_output=True, text=True)
    for _vl in _r_all.stdout.splitlines():
        if not (_vl.startswith('NOT READY') or _vl.startswith('READY')):
            continue
        check(f'{_fname}: no verdict line has a digit directly before "no"',
              not re.search(r'\d no\b', _vl), _vl)

# DEFECT 2 -- findings 1-4 on this fixture are one defect (a dead row that already
# explains the missing restore/terms/privacy actions) stated four times; the renderer
# must collapse them to ONE blocker, so this fixture reports exactly 2.
blocker_count = int(re.search(r'(\d+) blocker', verdict_line).group(1))
check('this fixture reports exactly 2 blockers after the dead-affordance collapse',
      blocker_count == 2, f'got {blocker_count}: {verdict_line!r}')
check('the BLOCKERS section prints exactly 2 numbered findings',
      txt.count('BLOCKERS') == 1 and len(re.findall(r'^\d+\.', txt.split('RISKS')[0],
                                                       re.M)) == 2)

# The underlying checks stay independent: a flow missing a restore action but with NO
# dead-affordance row of its own (every element that names an affordance word is
# properly wired) must still report its OWN separate `no-restore` blocker -- collapsing
# is a display-only merge, never a suppression.
no_dead_row = {
    'screens': [{'id': 'scr_pay', 'elements': {'map': {
        'el_buy': {
            'type': 'text', 'props': {'content': {'values': {'en': 'Continue'}}},
            'interactions': [{'id': 'i_buy', 'trigger': 'tap', 'actions': [
                {'id': 'a_buy', 'type': 'purchase', 'payload': {}}]}]},
        'el_terms': {
            'type': 'text', 'props': {'content': {'values': {'en': 'Terms'}}},
            'interactions': [{'id': 'i_terms', 'trigger': 'tap', 'actions': [
                {'id': 'a_terms', 'type': 'openUrl',
                 'payload': {'url': 'https://example.com/terms'}}]}]},
        'el_privacy': {
            'type': 'text', 'props': {'content': {'values': {'en': 'Privacy'}}},
            'interactions': [{'id': 'i_privacy', 'trigger': 'tap', 'actions': [
                {'id': 'a_privacy', 'type': 'openUrl',
                 'payload': {'url': 'https://example.com/privacy'}}]}]},
        'el_close': {
            'type': 'text', 'props': {'content': {'values': {'en': ''}}},
            'interactions': [{'id': 'i_close', 'trigger': 'tap', 'actions': [
                {'id': 'a_close', 'type': 'closeFlow', 'payload': {}}]}]},
    }}}],
    'locales': [], 'defaultLocale': 'en'}
with tempfile.TemporaryDirectory() as tmp:
    nd_path = os.path.join(tmp, 'no_dead_row.json')
    json.dump(no_dead_row, open(nd_path, 'w'))
    rc_nd, findings_nd = run(nd_path, catalog=None)
    rnd = subprocess.run([sys.executable, AUDIT, nd_path, '--report'],
                        capture_output=True, text=True)
check('no dead-affordance row fires on this config',
      len(of(findings_nd, 'dead-affordance')) == 0, findings_nd)
check('the missing restore action still fires its own blocker',
      len(of(findings_nd, 'no-restore')) == 1, findings_nd)
check('the report surfaces the un-merged restore blocker on its own',
      'NOT READY FOR PRODUCTION — 1 blocker: no restore action' in rnd.stdout,
      rnd.stdout[:300])

# `dead-affordance-merged` always sets its own `_label` at creation time today, so
# `CHECK_LABELS` never actually falls back to a per-check entry for it -- this reads
# the source (never imports it, per this suite's own rule) so a future change that
# ever constructs a merged finding without `_label` set still gets a real label
# instead of the raw check name reaching a client's verdict line.
_audit_src = open(AUDIT).read()
_labels_block = _audit_src.split('CHECK_LABELS = {', 1)[1].split('\n}', 1)[0]
check("CHECK_LABELS carries a 'dead-affordance-merged' entry -- a defensive guard "
      'against a future unlabelled verdict, not something reachable today',
      "'dead-affordance-merged':" in _labels_block)

print('\nDEFECT 1 -- sibling dead affordances collapse in the report')
# comparison-paywall.json: el_CqN7LxyqK8 ("Restore"), el_WiqJNVPbb8 ("Terms") and
# el_zSZPjSyaqU ("Privacy") are three SIBLING elements sharing one parent
# (el_fiZXD04jZt) on the same screen -- one thing a user recognises (a dead
# legal/restore row), not three. `audit()`/`--json` must keep reporting all three as
# separate `dead-affordance` findings -- the underlying checks stay independent;
# only `--report` collapses them.
cmp_fixture = os.path.join(FIX, 'comparison-paywall.json')
rc_cmp2, findings_cmp2 = run(cmp_fixture)
check('comparison-paywall.json still raises 3 separate dead-affordance findings in '
      '--json (the collapse is report-only)',
      len(of(findings_cmp2, 'dead-affordance')) == 3,
      f'got {len(of(findings_cmp2, "dead-affordance"))}')

r_cmp2 = subprocess.run([sys.executable, AUDIT, cmp_fixture, '--catalog', CATALOG,
                          '--report'], capture_output=True, text=True)
cmp_txt = r_cmp2.stdout
cmp_verdict = next(l for l in cmp_txt.splitlines() if l.startswith('NOT READY'))
cmp_blocker_count = int(re.search(r'(\d+) blocker', cmp_verdict).group(1))
check('comparison-paywall.json reports exactly 2 blockers after the sibling '
      'dead-affordance collapse (1 merged dead row + 1 product-not-in-catalog, '
      'down from 4)', cmp_blocker_count == 2, f'got {cmp_blocker_count}: {cmp_verdict!r}')
check('the BLOCKERS section prints exactly 2 numbered findings for '
      'comparison-paywall.json',
      len(re.findall(r'^\d+\.', cmp_txt.split('BEFORE YOU SHIP')[0], re.M)) == 2,
      cmp_txt)
check('the BLOCKERS section prints exactly ONE "This row is dead text." finding',
      len(re.findall(r'^\d+\. This row is dead text\.', cmp_txt, re.M)) == 1, cmp_txt)

cmp_finding1 = cmp_txt.split('1. This row is dead text.', 1)[1].split('\n2.', 1)[0]
check('the collapsed sibling finding names all three contributing elements',
      all(eid in cmp_finding1 for eid in
          ('el_CqN7LxyqK8', 'el_WiqJNVPbb8', 'el_zSZPjSyaqU')), cmp_finding1)
check('the collapsed sibling finding names all three affordances (their own copy)',
      all(w in cmp_finding1 for w in ('Restore', 'Terms', 'Privacy')), cmp_finding1)

print('\nDEFECT 2 -- the single-affordance fix line wording')
# The old wording -- "Split the row into one tappable element" -- is nonsense when
# the element already is one element. No fix line anywhere may read that way, for
# any fixture: the sibling-merge case wires N already-separate elements ("Wire
# el_a to ..., el_b to ...") and the single-affordance case wires the one element
# ("Wire this element to ...") -- neither ever says "split into one".
for _fname in sorted(os.listdir(FIX)):
    if not _fname.endswith('.json'):
        continue
    _r_fix = subprocess.run([sys.executable, AUDIT, os.path.join(FIX, _fname),
                              '--catalog', CATALOG, '--report'],
                             capture_output=True, text=True)
    check(f'{_fname}: no fix line reads "into one tappable element"',
          'into one tappable element' not in _r_fix.stdout, _r_fix.stdout)

# A synthetic single-element, single-affordance case, isolated from every other
# compliance check so exactly one matches: "Restore" is the only dead row (terms
# and privacy are both properly wired to real openUrl actions), so only no-restore
# merges with it.
one_word = {
    'screens': [{'id': 'scr_pay', 'elements': {'map': {
        'el_buy': {
            'type': 'text', 'props': {'content': {'values': {'en': 'Continue'}}},
            'interactions': [{'id': 'i_buy', 'trigger': 'tap', 'actions': [
                {'id': 'a_buy', 'type': 'purchase', 'payload': {}}]}]},
        'el_restore': {
            'type': 'text', 'props': {'content': {'values': {'en': 'Restore'}}}},
        'el_terms': {
            'type': 'text', 'props': {'content': {'values': {'en': 'Terms'}}},
            'interactions': [{'id': 'i_terms', 'trigger': 'tap', 'actions': [
                {'id': 'a_terms', 'type': 'openUrl',
                 'payload': {'url': 'https://example.com/terms'}}]}]},
        'el_privacy': {
            'type': 'text', 'props': {'content': {'values': {'en': 'Privacy'}}},
            'interactions': [{'id': 'i_privacy', 'trigger': 'tap', 'actions': [
                {'id': 'a_privacy', 'type': 'openUrl',
                 'payload': {'url': 'https://example.com/privacy'}}]}]},
    }}}],
    'locales': [], 'defaultLocale': 'en'}
with tempfile.TemporaryDirectory() as tmp:
    ow_path = os.path.join(tmp, 'one_word.json')
    json.dump(one_word, open(ow_path, 'w'))
    rc_ow, findings_ow = run(ow_path, catalog=None)
    row = subprocess.run([sys.executable, AUDIT, ow_path, '--report'],
                         capture_output=True, text=True)
check('fixture setup: exactly one dead-affordance finding (only "Restore" is dead; '
      'terms/privacy are wired)', len(of(findings_ow, 'dead-affordance')) == 1,
      findings_ow)
check('a single-affordance merge says what to WIRE it to, not to "split" a row '
      'that is already one element',
      'Fix: Wire this element to a restorePurchases action.' in row.stdout,
      row.stdout)
check('...and never the old "Split the row into one tappable element" wording',
      'into one tappable element' not in row.stdout, row.stdout)

print('\nsibling grouping is strict on (screen, parent) -- different parents never merge')
# Two elements naming DISTINCT affordance words on the SAME screen but under
# DIFFERENT parents must stay two separate merged findings -- merging them would
# combine two rows a user sees as unrelated. `el_restore` and `el_terms` sit under
# `el_group_a`/`el_group_b` respectively, two different (unwired) wrapping stacks.
two_parents = {
    'screens': [{'id': 'scr_pay', 'elements': {
        'map': {
            'el_buy': {
                'type': 'text', 'props': {'content': {'values': {'en': 'Continue'}}},
                'interactions': [{'id': 'i_buy', 'trigger': 'tap', 'actions': [
                    {'id': 'a_buy', 'type': 'purchase', 'payload': {}}]}]},
            'el_restore': {
                'type': 'text', 'props': {'content': {'values': {'en': 'Restore'}}}},
            'el_terms': {
                'type': 'text', 'props': {'content': {'values': {'en': 'Terms'}}}},
        },
        'hierarchy': {'id': 'el_root', 'children': [
            {'id': 'el_buy', 'children': []},
            {'id': 'el_group_a', 'children': [{'id': 'el_restore', 'children': []}]},
            {'id': 'el_group_b', 'children': [{'id': 'el_terms', 'children': []}]},
        ]},
    }}],
    'locales': [], 'defaultLocale': 'en'}
with tempfile.TemporaryDirectory() as tmp:
    tp_path = os.path.join(tmp, 'two_parents.json')
    json.dump(two_parents, open(tp_path, 'w'))
    rc_tp, findings_tp = run(tp_path, catalog=None)
    r_tp = subprocess.run([sys.executable, AUDIT, tp_path, '--report'],
                          capture_output=True, text=True)
check('fixture setup: two dead-affordance findings under two different parents',
      len(of(findings_tp, 'dead-affordance')) == 2, findings_tp)
tp_txt = r_tp.stdout
tp_dead_findings = len(re.findall(r'^\d+\. This row is dead text\.', tp_txt, re.M))
check('two dead affordances under DIFFERENT parents stay as two separate merged '
      'findings in the report (never collapsed together)',
      tp_dead_findings == 2, tp_txt)

print('\ncontract: the collapse never widens the finding dict\'s key set')
# The collapse is structural (walks `config`'s hierarchy), not an extra key on the
# finding dict -- re-assert the exact-key-set contract holds for --json output on
# both fixtures exercised above, so a future edit cannot quietly reopen that route.
check('comparison-paywall.json --json findings keep the exact 7-key contract',
      all(set(f) == {'severity', 'family', 'check', 'screen', 'element', 'message',
                      'fix'} for f in (findings_cmp2 or [])))

# flow-untitled reads the NAME, which is not in the config
r3 = subprocess.run([sys.executable, AUDIT, FLOW, '--json', '--name', 'Untitled'],
                    capture_output=True, text=True)
check('flow-untitled FIRES on a flow still called Untitled',
      len(of(json.loads(r3.stdout)['findings'], 'flow-untitled')) == 1)
r4 = subprocess.run([sys.executable, AUDIT, FLOW, '--json', '--name', 'Nimbus onboarding'],
                    capture_output=True, text=True)
check('flow-untitled is SILENT on a real name',
      len(of(json.loads(r4.stdout)['findings'], 'flow-untitled')) == 0)

# publication-failed reads STATUS, which is also not in the config -- same shape as
# flow-untitled above, reached through `check_meta` after `audit()` runs.
r5 = subprocess.run([sys.executable, AUDIT, FLOW, '--json', '--status',
                    'publication_failed'], capture_output=True, text=True)
pf = of(json.loads(r5.stdout)['findings'], 'publication-failed')
check('publication-failed FIRES on --status publication_failed', len(pf) == 1, pf)
check('publication-failed is a question, never a blocker (no cause is knowable here)',
      bool(pf) and pf[0]['severity'] == 'question')
check('publication-failed does not invent a cause -- it names the dashboard status, '
      'says no local check explains it, and points at the Flow Builder, nothing more',
      bool(pf) and 'publication_failed' in pf[0]['message']
      and 'Flow Builder' in pf[0]['fix'])
for _status in ('draft', 'published', 'archived', None):
    _cmd = [sys.executable, AUDIT, FLOW, '--json']
    if _status:
        _cmd += ['--status', _status]
    _r = subprocess.run(_cmd, capture_output=True, text=True)
    check(f'publication-failed is SILENT when --status is {_status!r}',
          len(of(json.loads(_r.stdout)['findings'], 'publication-failed')) == 0)

# A flow with zero other findings still cannot print a bare READY once it is sitting
# in publication_failed -- the question alone must hold the verdict open.
with tempfile.TemporaryDirectory() as tmp:
    pf_path = os.path.join(tmp, 'pf_clean.json')
    json.dump({'screens': [], 'locales': [], 'defaultLocale': 'en'}, open(pf_path, 'w'))
    r_pf = subprocess.run([sys.executable, AUDIT, pf_path, '--report', '--status',
                           'publication_failed'], capture_output=True, text=True)
check('a flow with no other findings still prints READY, PENDING once its status is '
      'publication_failed, never a bare READY FOR PRODUCTION',
      'READY, PENDING' in r_pf.stdout and 'READY FOR PRODUCTION' not in r_pf.stdout,
      r_pf.stdout)
check('the publication_failed run exits 0 -- no blocker fired, only a question',
      r_pf.returncode == 0)

# A ruling overrides the brief's `/dev/stdin` + subprocess `input=` approach: `load_config`
# uses `open(path)`, and `/dev/stdin` is not reliable that way across platforms, so a temp
# file is written and its path passed -- matching every other case in this suite.
# A genuinely empty `screens: []` flow is no longer "nothing wrong" now that
# `no-escape-in-flow` applies to any flow -- it has no escape either, so it would
# fire. This fixture carries one non-selling screen with a real closeFlow action, so
# it stays a true negative control across every family, `no-escape-in-flow` included.
clean = {
    'screens': [{'id': 'scr_only', 'elements': {'map': {
        'el_close': {
            'type': 'text', 'props': {'content': {'values': {'en': 'Close'}}},
            'interactions': [{'id': 'i_close', 'trigger': 'tap', 'actions': [
                {'id': 'a_close', 'type': 'closeFlow', 'payload': {}}]}]},
    }}}],
    'locales': [], 'defaultLocale': 'en'}
with tempfile.TemporaryDirectory() as tmp:
    clean_path = os.path.join(tmp, 'clean.json')
    json.dump(clean, open(clean_path, 'w'))
    r2 = subprocess.run([sys.executable, AUDIT, clean_path, '--report'],
                        capture_output=True, text=True)
check('a flow with nothing wrong prints READY', 'READY FOR PRODUCTION' in r2.stdout)
check('a clean run exits 0', r2.returncode == 0)
check('a clean run offers no fix -- nothing to fix', 'Want me to fix' not in r2.stdout)

# READY, PENDING n CHECKS I CANNOT MAKE -- zero blockers, at least one open question.
# Built directly rather than relying on a fixture: a selling screen with a working
# restorePurchases action and both legal links present (so none of those fire), but
# no closeFlow/navigateBack anywhere in the flow, which is exactly what makes
# `no-escape-in-flow` a QUESTION rather than a blocker. The bare "Continue" CTA states
# no period, so `check_disclosure` (Task 4/5) also fires `no-period-disclosed` here --
# left in place, not edited away, because it gives this fixture double duty. Before
# Task 7 this was the only place in the suite that exercised a `question` and a
# `risk` finding together in one report; Task 7's partition pulls `no-period-
# disclosed` out of the severity loop entirely (it never reaches `RISKS` -- this
# report now has no `RISKS` heading at all) and numbers it last, in its own STORE
# REVIEW -- ADVISORY section, so what this fixture now exercises is a non-store
# `question` alongside a store-review finding printed after it (Answer group,
# flow-edit group, correct numbering -- see the grouping comment at the assertions
# below).
questions_only = {
    'screens': [{'id': 'scr_a', 'elements': {'map': {
        'el_buy': {
            'type': 'text',
            'props': {'content': {'values': {'en': 'Continue'}}},
            'interactions': [{'id': 'i_buy', 'trigger': 'tap', 'actions': [
                {'id': 'a_buy', 'type': 'purchase', 'payload': {}}]}]},
        'el_restore': {
            'type': 'text',
            'props': {'content': {'values': {'en': 'Restore purchases'}}},
            'interactions': [{'id': 'i_restore', 'trigger': 'tap', 'actions': [
                {'id': 'a_restore', 'type': 'restorePurchases', 'payload': {}}]}]},
        'el_terms': {
            'type': 'text',
            'props': {'content': {'values': {'en': 'Terms'}}},
            'interactions': [{'id': 'i_terms', 'trigger': 'tap', 'actions': [
                {'id': 'a_terms', 'type': 'openUrl',
                 'payload': {'url': 'https://example.com/terms'}}]}]},
        'el_privacy': {
            'type': 'text',
            'props': {'content': {'values': {'en': 'Privacy'}}},
            'interactions': [{'id': 'i_privacy', 'trigger': 'tap', 'actions': [
                {'id': 'a_privacy', 'type': 'openUrl',
                 'payload': {'url': 'https://example.com/privacy'}}]}]},
    }}}],
    'locales': [], 'defaultLocale': 'en'}
with tempfile.TemporaryDirectory() as tmp:
    q_path = os.path.join(tmp, 'q.json')
    json.dump(questions_only, open(q_path, 'w'))
    rq = subprocess.run([sys.executable, AUDIT, q_path, '--report'],
                        capture_output=True, text=True)
check('a flow with only open questions prints READY, PENDING ... I CANNOT MAKE',
      'READY, PENDING' in rq.stdout and 'I CANNOT MAKE' in rq.stdout,
      rq.stdout[:300])
check('a questions-only run still exits 0 -- no blocker fired', rq.returncode == 0)

# a single-locale flow omits the LOCALE COVERAGE table entirely
single = {'screens': [], 'locales': [{'code': 'en'}], 'defaultLocale': 'en'}
with tempfile.TemporaryDirectory() as tmp:
    s_path = os.path.join(tmp, 's.json')
    json.dump(single, open(s_path, 'w'))
    rs = subprocess.run([sys.executable, AUDIT, s_path, '--report'],
                        capture_output=True, text=True)
check('a single-locale flow has no LOCALE COVERAGE table',
      'LOCALE COVERAGE' not in rs.stdout)
check('the header singularizes "1 locale", never "1 locales" -- the verdict line '
      'already singularizes "1 blocker"/"1 CHECK", the header must match',
      '1 locale' in rs.stdout and '1 locales' not in rs.stdout, rs.stdout[:200])
check('the header still pluralizes "0 screens" (count != 1)',
      '0 screens' in rs.stdout, rs.stdout[:200])

# The inverse: exactly one screen, no locales declared, one bound product -- singular
# everywhere a count is 1, matching the verdict line's own singular/plural rule.
one_each = {
    'screens': [{'id': 'scr_only', 'elements': {'map': {
        'el_p': {'type': 'text', 'props': {
            'content': {'values': {'en': 'Plan'}},
            'product': {'id': 'fbc63856-bf3a-45d1-7bee-dd4bcb54b10a'}},
            'interactions': [{'id': 'i_p', 'trigger': 'tap', 'actions': [
                {'id': 'a_p', 'type': 'purchase', 'payload': {}}]}]},
    }}}],
    'locales': [], 'defaultLocale': 'en'}
with tempfile.TemporaryDirectory() as tmp:
    oe_path = os.path.join(tmp, 'one_each.json')
    json.dump(one_each, open(oe_path, 'w'))
    r_oe = subprocess.run([sys.executable, AUDIT, oe_path, '--report'],
                          capture_output=True, text=True)
check('the header prints "1 screen" and "1 product", singular, not "1 screens"/'
      '"1 products"',
      '1 screen ' in r_oe.stdout and '1 screens' not in r_oe.stdout
      and '1 product' in r_oe.stdout and '1 products' not in r_oe.stdout,
      r_oe.stdout[:200])

# --report and --json are mutually exclusive -- a usage error, not a silent pick
rboth = subprocess.run([sys.executable, AUDIT, FLOW, '--report', '--json'],
                       capture_output=True, text=True)
check('--report and --json together is a usage error',
      rboth.returncode == 2 and rboth.stdout == '')

print('\nwhat to do next')
# `txt` is still the multilocale fixture's report from the `report` section above,
# run with `--status publication_failed`: 6 findings after collapse (1-2 blockers,
# 3 risk -- the untranslated-values one -- 4-5 questions -- the store gap and the
# publication_failed status itself -- 6 the June 2026 price-prominence hazard, which
# Task 7 moved out of RISKS into its own STORE REVIEW -- ADVISORY section, numbered
# last and printed after LOCALE COVERAGE, before BEFORE YOU SHIP).
check('WHAT TO DO NEXT is present', 'WHAT TO DO NEXT' in txt)
check('WHAT TO DO NEXT comes after BEFORE YOU SHIP',
      'BEFORE YOU SHIP' in txt
      and txt.index('WHAT TO DO NEXT') > txt.index('BEFORE YOU SHIP'))
check('WHAT TO DO NEXT comes before the closing offer',
      'Want me to fix' in txt
      and txt.index('WHAT TO DO NEXT') < txt.index('Want me to fix'))

# The important one: every finding number the BLOCKERS/RISKS/COULD NOT CHECK
# sections assign must be named somewhere in WHAT TO DO NEXT, as "finding N" -- a
# finding that never shows up here is silently dropped from the plan.
nums = sorted(int(m) for m in re.findall(r'^(\d+)\.', txt, re.M))
next_section = txt.split('WHAT TO DO NEXT', 1)[1].split('Want me to fix', 1)[0]
missing = [n for n in nums if f'finding {n}' not in next_section]
check('every numbered finding is referenced in WHAT TO DO NEXT',
      nums == [1, 2, 3, 4, 5, 6] and not missing, f'nums={nums} missing={missing}')

check('Answer group asks about the store gap and points at its finding number',
      'Answer these' in next_section
      and 'Do you ship on Android?' in next_section
      and 'finding 4' in next_section.split('Change in the flow')[0])
check('the store-gap question and its dashboard fix both cite finding 4 '
      '(one question, one action -- not a drop, not a merge)',
      next_section.count('finding 4') == 2, next_section)
check('the flow-edit group names the dead row\'s screen/element',
      'scr_paywall / el_089T' in next_section.split('Change in the Adapty')[0])
check('the dashboard group carries the unconditional placement line',
      'Confirm the flow is attached to a placement.' in next_section)
# `billed-amount-not-shown` is a store-review check (Task 7): it is registered in
# `CHECK_TO_GROUP` as GROUP_FLOW like any other flow-edit fix, so it still gets a
# line here -- but it is numbered LAST (finding 6), after every non-store finding,
# because `render()` appends the STORE REVIEW section (and its own numbering) only
# after the BLOCKERS/RISKS/COULD NOT CHECK loop has assigned 1-5.
check('the flow-edit group carries the billed-amount-not-shown price risk',
      'finding 6' in next_section.split('Change in the Adapty')[0])
check('the optional group carries the untranslated-values risk',
      'Optional' in next_section
      and 'finding 3' in next_section.split('Optional', 1)[1])
check('the publication_failed question is finding 5, named once under the '
      'dashboard group, and does NOT get an Answer-group line (no answer here '
      'changes the verdict)',
      next_section.count('finding 5') == 1
      and 'finding 5' in next_section.split('Change in the Adapty')[1]
      and 'finding 5' not in next_section.split('Change in the flow')[0],
      next_section)

# Zero findings at all -- `r2`'s clean fixture from the `report` section above --
# prints no section, even though BEFORE YOU SHIP's placement line is unconditional.
check('a flow with nothing wrong has no WHAT TO DO NEXT section',
      'WHAT TO DO NEXT' not in r2.stdout)
check('...but still keeps the unconditional placement reminder',
      'placement' in r2.stdout)

# A group with no members prints no heading. `rnd`'s config (from DEFECT 2 above)
# fires exactly one finding -- `no-restore`, a flow edit -- so Answer (no verdict-
# conditional question fired) and Optional (no risk fired) must both be absent,
# while Flow (the finding itself) and Dashboard (the unconditional placement line)
# both appear.
rnd_next = rnd.stdout.split('WHAT TO DO NEXT', 1)[1] if 'WHAT TO DO NEXT' in rnd.stdout else ''
check('a single flow-edit finding still gets a WHAT TO DO NEXT section', bool(rnd_next))
check('...with no Answer heading (nothing verdict-conditional fired)',
      'Answer these' not in rnd_next)
check('...with no Optional heading (nothing risk-severity fired)',
      'Optional' not in rnd_next)
check('...with the flow-edit heading and its finding number',
      'Change in the flow' in rnd_next and 'finding 1' in rnd_next)
check('...with the dashboard heading present only for the placement line',
      'Change in the Adapty dashboard' in rnd_next
      and 'Confirm the flow is attached to a placement.' in rnd_next)

# `rq`'s questions-only config (from the READY-PENDING case above) now fires TWO
# findings, not one -- the bare "Continue" CTA states no billing period, so
# `check_disclosure` (Task 4/5) also fires `no-period-disclosed`. This is
# deliberately NOT edited away (a prior pass rewrote the CTA to silence it; restored
# on review, because that hid a real finding rather than testing it): the fixture now
# gives this suite its only report combining a non-store `question` and a
# store-review finding together -- Answer group, flow-edit group and correct
# numbering all in one place.
#
# finding 1 = `no-escape-in-flow` (verdict-conditional question) -- lands in BOTH the
# Answer group and its own default (flow-edit) group, per the same rule
# `product-store-gap` demonstrates on the main fixture.
# finding 2 = `no-period-disclosed` -- a store-review check (Task 7), so it is
# partitioned out of the severity groups entirely (it never reaches RISKS, and never
# sorts against the question by `ORDER`) and numbered last, in its own STORE REVIEW
# -- ADVISORY section printed after LOCALE COVERAGE. It IS registered in
# `CHECK_TO_GROUP` (Task 7 Step 6), as GROUP_FLOW like every other store-review
# check, so it still gets a "Change in the flow" line in WHAT TO DO NEXT.
#
# Both land in the SAME group ("Change in the flow"), not split across a flow-edit/
# Optional divide -- but for a different reason than before Task 7: `no-period-
# disclosed` is mapped to GROUP_FLOW, not GROUP_OPTIONAL, so there is no `Optional`
# heading in this report. (Store-review checks are deliberately absent from
# `VERDICT_CONDITIONAL` and `CHECK_LABELS` too -- see Task 7's brief -- neither of
# which this scenario exercises.)
rq_next = rq.stdout.split('WHAT TO DO NEXT', 1)[1] if 'WHAT TO DO NEXT' in rq.stdout else ''
check('a questions-only-plus-store-review report still gets a WHAT TO DO NEXT section',
      bool(rq_next))
check('...with an Answer prompt about the missing dismiss',
      'Answer these' in rq_next and 'dismiss' in rq_next.lower())
check('...naming finding 1 (no-escape-in-flow) in both the Answer and flow-edit groups',
      rq_next.count('finding 1') == 2, rq_next)
check('...naming finding 2 (no-period-disclosed) once, in the flow-edit group',
      rq_next.count('finding 2') == 1
      and 'finding 2' in rq_next.split('Change in the Adapty')[0], rq_next)
check('...with no Optional heading -- no-period-disclosed is registered in '
      'CHECK_TO_GROUP as GROUP_FLOW, not GROUP_OPTIONAL, and never reaches RISKS '
      'at all (see the comment above)',
      'Optional' not in rq_next)
check('...and the STORE REVIEW -- ADVISORY section is present for finding 2',
      'STORE REVIEW' in rq.stdout and '2. ' in rq.stdout.split('STORE REVIEW', 1)[1])

if fails:
    print(f'\n{len(fails)} FAILED')
    for f in fails:
        print('  -', f)
    sys.exit(1)
print('\nall passed')

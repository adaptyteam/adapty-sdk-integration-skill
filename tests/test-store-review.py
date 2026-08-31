#!/usr/bin/env python3
"""Calibration for the store-review checks in `references/audit-flow.py`.

Repo-only, like everything under `tests/`. Runs the shipped script as a subprocess --
never imports it, so nothing writes a `__pycache__` into `references/`, which the
copy-install path would ship.

Both directions are asserted and they matter equally:

    FIRES   -- an injected defect must be reported, at the stated severity
    SILENT  -- every real export, tracked and raw, must stay clean

Store review is ADVISORY: no case here may assert a `blocker`, and the verdict must
stay clean when store-review findings are the only ones that fired.

Usage: python3 tests/test-store-review.py     # 0 all pass, 1 a case regressed
"""
import copy, glob, json, os, re, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUDIT = os.path.join(ROOT, 'skills', 'flow-audit', 'references', 'audit-flow.py')
FIX = os.path.join(ROOT, 'tests', 'fixtures')
RAW = os.path.join(ROOT, 'tests', 'fixtures-raw')
CATALOG = os.path.join(ROOT, 'tests', 'catalog-fixture.json')
MULTI = os.path.join(FIX, 'onboarding-multilocale.json')

fails = []


def run(config, catalog=CATALOG, stores=None, report=False):
    """(rc, findings|stdout). `config` is a path or a dict."""
    with tempfile.TemporaryDirectory() as tmp:
        path = config
        if isinstance(config, dict):
            path = os.path.join(tmp, 'c.json')
            json.dump(config, open(path, 'w'))
        cmd = [sys.executable, AUDIT, path, '--report' if report else '--json']
        if catalog:
            cmd += ['--catalog', catalog]
        if stores:
            cmd += ['--stores', stores]
        r = subprocess.run(cmd, capture_output=True, text=True)
    if 'Traceback' in r.stderr:
        raise AssertionError(f'audit-flow.py crashed:\n{r.stderr}')
    if report:
        return r.returncode, r.stdout
    return r.returncode, json.loads(r.stdout)['findings']


def check(name, cond, detail=''):
    if cond:
        print(f'  ok    {name}')
    else:
        print(f'  FAIL  {name} {detail}')
        fails.append(name)


def of(findings, checkname):
    return [f for f in (findings or []) if f['check'] == checkname]


def load(path=MULTI):
    doc = json.load(open(path))
    return doc.get('config', doc)


def corpus():
    """Every real export, tracked and raw. Raw is gitignored, so it may be absent."""
    return sorted(glob.glob(os.path.join(FIX, '*.json'))
                  + glob.glob(os.path.join(RAW, '*.json')))


def _section(text, heading):
    """Body text of one `--report` heading's block, or '' if the heading is absent.

    Uses `.find`, never `.index`: a missing heading must return '' so a caller's
    check FAILS and gets recorded, rather than raising `ValueError` and aborting the
    whole suite mid-run -- which is exactly what happened here once, when a check
    built on `.index('STORE REVIEW')` ran against a report that had no such section.
    """
    start = text.find('\n' + heading + '\n')
    if start == -1:
        return ''
    start += len(heading) + 2
    end = text.find('\n\n\n', start)
    return text[start:end if end != -1 else len(text)]


print('task 1 — helpers')
# The helpers are exercised through the checks that consume them; this case proves the
# script still runs and the contract is intact after the edit.
rc, findings = run(MULTI)
check('script runs and returns findings', isinstance(findings, list), f'rc={rc}')
check('no finding gained a new key',
      all(set(f) == {'severity', 'family', 'check', 'screen', 'element', 'message', 'fix'}
          for f in findings))

print('task 2 — price prominence')

# FIRES: the corpus already contains the rejected shape. `onboarding-multilocale.json`
# draws Pro Annual as a per-month figure at 22px bold and the billed annual amount
# appears nowhere on the screen -- the June 2026 notice, in a tracked fixture.
rc, findings = run(MULTI)
bans = of(findings, 'billed-amount-not-shown')
check('fires on the real per-month-only annual card', len(bans) == 1, str(bans))
check('...as a risk, never a blocker',
      all(f['severity'] == 'risk' for f in bans), str(bans))
check('...naming the product', bans and 'Pro Annual' in bans[0]['message'], str(bans))

# SILENT: with no catalog there is no `period`, so which suffix is the billed amount is
# undecidable -- and the whole gap is already reported ONCE, as `catalog-not-fetched`.
# So the question form is suppressed entirely rather than repeated per (screen,
# product): its content would be "I could not find that product in the catalog",
# which the report has already said. Measured before the suppression: two advisory
# questions here, and on `onboarding-quiz-paywall.json` with a real catalog, two more
# alongside the two `product-not-in-catalog` BLOCKERS naming the same products.
rc, findings = run(MULTI, catalog=None)
check('no billed-amount question when there is no catalog at all '
      '(catalog-not-fetched already covers it, once)',
      not of(findings, 'billed-amount-not-shown'),
      str(of(findings, 'billed-amount-not-shown')))
check('...and that single catalog-not-fetched question IS present, so the gap is '
      'reported rather than silently dropped',
      len(of(findings, 'catalog-not-fetched')) == 1,
      str(of(findings, 'catalog-not-fetched')))

# SILENT: the same suppression when a catalog IS supplied but the product is missing
# from it -- `product-not-in-catalog` is already a blocker naming that product.
rc, findings = run(os.path.join(FIX, 'onboarding-quiz-paywall.json'))
check('no billed-amount question for a product already reported as uncatalogued',
      not of(findings, 'billed-amount-not-shown'),
      str(of(findings, 'billed-amount-not-shown')))
check('...and product-not-in-catalog IS reported for those products',
      len(of(findings, 'product-not-in-catalog')) == 2,
      str(of(findings, 'product-not-in-catalog')))

# FIRES: the one case the question form survives for, and the reason it is not
# deleted -- the product IS in the catalog and its row carries no `period`, so which
# suffix is the billed amount is genuinely undecidable and nothing else in the report
# mentions it. Same two products as `MULTI`'s own catalog rows, `period` removed.
_noperiod = [dict(p, period=None) for p in json.load(open(CATALOG))]
NOPERIOD_CAT = os.path.join(tempfile.gettempdir(), 'store-review-noperiod-catalog.json')
with open(NOPERIOD_CAT, 'w') as fh:
    json.dump(_noperiod, fh)
try:
    rc, findings = run(MULTI, catalog=NOPERIOD_CAT)
    bans = of(findings, 'billed-amount-not-shown')
    check('degrades to a question when a CATALOGUED product states no period',
          bans and all(f['severity'] == 'question' for f in bans), str(bans))
    check('...and says so, rather than claiming the product is missing',
          bans and 'states no billing period' in bans[0]['message'], str(bans))
finally:
    os.unlink(NOPERIOD_CAT)

# FIRES: the SECOND case the question form survives for, and the reason the two are
# worded differently. A price variable can name a product that is absent from the
# catalog AND bound nowhere in the flow -- `check_products_catalog` walks
# `bound_products`, so it never sees this id either, and nothing else in the report
# mentions it. The single earlier wording ("whose catalog entry states no billing
# period") was FALSE here: there is no catalog entry at all. Caught by the final
# whole-branch review; no fixture covered the shape, hence this case.
GHOST = 'deadbeef-0000-4000-8000-000000000009'
ANNUAL_ID = '6cdd73d5-bdb2-4b2e-c207-784fbcb2f408'   # Pro Annual, catalog-fixture.json
ghost = load()
for s in ghost['screens']:
    if s['id'] != 'scr_paywall':
        continue
    e = ((s.get('elements') or {}).get('map') or {}).get('el_075T')
    # el_075T's whole content is one `variable` node naming Pro Annual; repoint it at
    # an id that is in neither the catalog nor the flow, leaving everything else alone.
    e['props']['content'] = json.loads(
        json.dumps(e['props']['content']).replace(ANNUAL_ID, GHOST))
rc, findings = run(ghost)
bans = of(findings, 'billed-amount-not-shown')
check('a price variable naming an unknown, unbound product still asks',
      bans and all(f['severity'] == 'question' for f in bans), str(bans))
check('...naming the id rather than claiming a catalog entry it does not have',
      bans and GHOST in bans[0]['message']
      and 'catalog entry' not in bans[0]['message'], str(bans))
check('...and says it is bound nowhere, which is the actionable half',
      bans and 'not bound anywhere' in bans[0]['message'], str(bans))
check('...while no product-not-in-catalog blocker covers it (that check walks bound '
      'products, so this id is invisible to it)',
      not any(GHOST in f['message'] for f in of(findings, 'product-not-in-catalog')),
      str(of(findings, 'product-not-in-catalog')))

# SILENT: a monthly product priced with `prod_price_per_month` IS showing its billed
# amount. Rebinding the annual card's variable to the monthly product must clear it.
doc = load()
scr = [s for s in doc['screens'] if s['id'] == 'scr_paywall'][0]
raw = json.dumps(scr)
MONTHLY = 'fbc63856-bf3a-45d1-7bee-dd4bcb54b10a'   # Pro Monthly, catalog-fixture.json
ANNUAL = '6cdd73d5-bdb2-4b2e-c207-784fbcb2f408'    # Pro Annual
mono = copy.deepcopy(doc)
mono['screens'] = [json.loads(raw.replace(ANNUAL, MONTHLY)) if s['id'] == 'scr_paywall'
                   else s for s in doc['screens']]
rc, findings = run(mono)
check('silent when the per-month figure IS the billed amount',
      not of(findings, 'billed-amount-not-shown'),
      str(of(findings, 'billed-amount-not-shown')))

# NOT a calibration of the comparison -- weaker than the old label claimed, and
# renamed to say so. With the catalog defaulting to `catalog-fixture.json` (whose
# product ids only match `onboarding-multilocale.json`), every OTHER fixture's bound
# products resolve no `period`, so `billed` stays empty and `check_price_prominence`
# takes the `if not billed:` branch before ever reaching the `dmax > bmax` comparison
# this loop used to claim to calibrate. All this loop actually proves: no real,
# shipped export accidentally trips `derived-price-louder` under this catalog. It
# does NOT prove the comparison ran correctly -- for that, see the quiz-catalog
# SILENT/FIRES pair below, which populates `billed` for real and is the only place in
# this suite where the comparison is genuinely exercised.
for path in corpus():
    rc, findings = run(path)
    check(f'no derived-price-louder MISFIRE on {os.path.basename(path)} '
          '(billed stays empty here under this catalog -- does not exercise the '
          'size/weight comparison; see the quiz-catalog pair below for that)',
          not of(findings, 'derived-price-louder'),
          str(of(findings, 'derived-price-louder')))

# FIRES: shrink the billed amount below the derived one on a card that shows both.
QUIZ = os.path.join(FIX, 'onboarding-quiz-paywall.json')
quiz = load(QUIZ)
quiz_cat = [{'id': '8fb58c50-7c05-42f9-a8e3-8d0fde19505a', 'title': 'Annual',
             'period': 'annual', 'access_level_id': 'a', 'vendor_products': {}},
            {'id': '7658234e-f95b-474e-bf5c-4b9ae634029e', 'title': 'Monthly',
             'period': 'monthly', 'access_level_id': 'a', 'vendor_products': {}}]
QUIZ_CAT = os.path.join(tempfile.gettempdir(), 'store-review-quiz-catalog.json')
with open(QUIZ_CAT, 'w') as fh:
    json.dump(quiz_cat, fh)
try:
    rc, findings = run(QUIZ, catalog=QUIZ_CAT)
    check('quiz paywall is clean with a real catalog',
          not of(findings, 'derived-price-louder') and not of(findings, 'billed-amount-not-shown'),
          str([f['check'] for f in findings]))

    louder = copy.deepcopy(quiz)
    for s in louder['screens']:
        e = ((s.get('elements') or {}).get('map') or {}).get('el_3La404eJMD')   # per-YEAR text
        if e:
            e['props']['font'] = {'size': 9, 'weight': 'light'}
    rc, findings = run(louder, catalog=QUIZ_CAT)
    check('fires when the derived figure outweighs the billed one',
          len(of(findings, 'derived-price-louder')) == 1,
          str(of(findings, 'derived-price-louder')))
    check('...as a risk', all(f['severity'] == 'risk' for f in of(findings, 'derived-price-louder')))
    check('...and the message names the SIZE difference, with both numbers',
          of(findings, 'derived-price-louder')
          and 'set larger than the billed amount (13pt against 9pt)'
          in of(findings, 'derived-price-louder')[0]['message'],
          str(of(findings, 'derived-price-louder')))

    # The WEIGHT-ONLY path. `dmax > bmax` compares (size, weight rank) tuples, so
    # weight breaks a tie only on EQUAL size -- and on that path the message used to
    # read "is set larger or heavier (13pt) than the billed amount (13pt)": the same
    # number twice, with the dimension that actually differs never mentioned.
    # Keyed on the price VARIABLE each element draws, not on element ids: this screen
    # carries several elements per product, so hardcoding two ids leaves the rest of
    # the product's rows at their preset size and makes which row wins the `max()`
    # accidental. `8fb58c50…` is Annual in `quiz_cat`, so `prod_price_per_year` is its
    # billed suffix and `prod_price_per_month` is the derived one.
    ANN = '8fb58c50-7c05-42f9-a8e3-8d0fde19505a'
    heavier = copy.deepcopy(quiz)
    n_billed = n_derived = 0
    for s in heavier['screens']:
        for eid, e in ((s.get('elements') or {}).get('map') or {}).items():
            if e.get('type') != 'text':
                continue
            raw = json.dumps(e.get('props', {}).get('content'))
            if f'{ANN}.prod_price_per_year' in raw or f'{ANN}.prod_price"' in raw:
                e['props']['font'] = {'size': 13, 'weight': 'regular'}
                n_billed += 1
            elif f'{ANN}.prod_price_per_month' in raw:
                e['props']['font'] = {'size': 13, 'weight': 'bold'}
                n_derived += 1
    check('the weight-only mutation actually found both a billed and a derived row '
          '(the guard that stops the case below passing for the wrong reason)',
          n_billed >= 1 and n_derived >= 1, f'billed={n_billed} derived={n_derived}')
    rc, findings = run(heavier, catalog=QUIZ_CAT)
    dpl = of(findings, 'derived-price-louder')
    check('fires on a weight-only difference at equal size', len(dpl) == 1, str(dpl))
    check('...and the message names the WEIGHT, not two identical point sizes',
          dpl and 'set in a heavier weight than the billed amount, both at 13pt'
          in dpl[0]['message'], str(dpl))
    check('...and never claims it is larger when the sizes match',
          dpl and 'larger' not in dpl[0]['message'], str(dpl))

    # SILENT, but discriminating this time: the mutation pair's other half. Same
    # fixture, same catalog, same two elements as `louder` above -- only now the
    # BILLED figure (el_3La404eJMD, per-YEAR) is set larger/heavier than the derived
    # one, instead of the reverse. `billed` and `derived` are both genuinely populated
    # here (unlike the corpus loop above), so this run DOES reach the `dmax > bmax`
    # comparison -- proven in the negative test below, where forcing that comparison
    # to always fire turns this case red while the corpus loop above stays green.
    quieter = copy.deepcopy(quiz)
    for s in quieter['screens']:
        e = ((s.get('elements') or {}).get('map') or {}).get('el_3La404eJMD')   # per-YEAR text (billed)
        if e:
            e['props']['font'] = {'size': 18, 'weight': 'bold'}
    rc, findings = run(quieter, catalog=QUIZ_CAT)
    check('silent when the billed amount is set larger than the derived one '
          '(reaches the comparison with real, populated billed/derived data)',
          not of(findings, 'derived-price-louder'),
          str(of(findings, 'derived-price-louder')))
finally:
    os.unlink(QUIZ_CAT)

print('task 3 — trial toggle')

# SILENT on the whole corpus. The decisive case: `onboarding-multilocale.json` carries
# the ONLY pill-shaped fixed box in the corpus -- a 50x30 stack with propsByState on
# `scr_notify`, a notifications opt-in. Shape alone would flag it; the trial-copy signal
# and the selling-screen scope each clear it independently.
for path in corpus():
    rc, findings = run(path)
    check(f'trial-toggle silent on {os.path.basename(path)}',
          not of(findings, 'trial-toggle'), str(of(findings, 'trial-toggle')))

# FIRES: build the catalog's own `trial-toggle` template onto the paywall screen.
doc = load()
pay = [s for s in doc['screens'] if s['id'] == 'scr_paywall'][0]
pay['elements']['map']['el_toggle'] = {
    'id': 'el_toggle', 'type': 'selectable',
    'props': {'groupId': 'trial_toggle', 'width': {'type': 'fill'},
              'height': {'type': 'hug'}},
    'states': [{'id': 'selected', 'type': 'system'}],
    'propsByState': {'selected': {}},
}
pay['elements']['map']['el_toggle_label'] = {
    'id': 'el_toggle_label', 'type': 'text',
    'props': {'content': {'values': {'en': [{'type': 'paragraph', 'content': [
        {'type': 'text', 'text': 'Free trial'}]}]}}},
}
pay['elements']['map']['el_toggle_switch'] = {
    'id': 'el_toggle_switch', 'type': 'stack',
    'props': {'width': {'type': 'fixed', 'value': 52},
              'height': {'type': 'fixed', 'value': 32},
              'borderRadius': {'tl': 9999, 'tr': 9999, 'bl': 9999, 'br': 9999}},
    'propsByState': {'selected': {'layout': {'alignH': 'end'}}},
}
pay['elements']['hierarchy']['children'].append(
    {'id': 'el_toggle', 'children': [{'id': 'el_toggle_label'},
                                     {'id': 'el_toggle_switch'}]})
rc, findings = run(doc)
tt = of(findings, 'trial-toggle')
check('fires on the catalog trial-toggle shape', len(tt) == 1, str(tt))
check('...as a risk, never a blocker', tt and all(f['severity'] == 'risk' for f in tt), str(tt))
check('...naming the January 2026 wave', tt and '2026' in tt[0]['message'], str(tt))

# SILENT under --stores android: the wave is iOS-only. Android and web were unaffected.
rc, findings = run(doc, stores='android')
check('silent for an Android-only app', not of(findings, 'trial-toggle'),
      str(of(findings, 'trial-toggle')))
rc, findings = run(doc, stores='ios,android')
check('fires for an app that also ships on iOS', len(of(findings, 'trial-toggle')) == 1)

# SILENT without the trial copy: the same switch labelled something else is a plain
# preference toggle, which Apple has never objected to.
notrial = copy.deepcopy(doc)
for s in notrial['screens']:
    e = ((s.get('elements') or {}).get('map') or {}).get('el_toggle_label')
    if e:
        e['props']['content']['values']['en'][0]['content'][0]['text'] = 'Email me tips'
rc, findings = run(notrial)
check('silent when the switch names no trial', not of(findings, 'trial-toggle'),
      str(of(findings, 'trial-toggle')))

# SILENT without the switch shape: trial copy beside an ordinary plan card is the
# COMPLIANT alternative Adapty recommends, and flagging it would be backwards.
noswitch = copy.deepcopy(doc)
for s in noswitch['screens']:
    m = (s.get('elements') or {}).get('map') or {}
    if 'el_toggle_switch' in m:
        m['el_toggle_switch']['props']['borderRadius'] = {'tl': 4, 'tr': 4, 'bl': 4, 'br': 4}
rc, findings = run(noswitch)
check('silent when the control is not switch-shaped', not of(findings, 'trial-toggle'),
      str(of(findings, 'trial-toggle')))

# SILENT: a static "Free trial" badge chip on a plan-card group member -- pill-shaped
# (width>height, fully rounded), naming a trial, scoped to a selling screen -- but
# carrying NO `propsByState` anywhere in its subtree. This is the check's own
# recommended remediation ("a side-by-side plan comparison with the trial badged on
# one plan"), so flagging it would tell a compliant customer their fix looks like the
# rejected pattern. Built from a fresh `load()`, not `doc`, so this case cannot pass
# by accident from the real toggle injected above.
badge = load()
bpay = [s for s in badge['screens'] if s['id'] == 'scr_paywall'][0]
bpay['elements']['map']['el_plancard'] = {
    'id': 'el_plancard', 'type': 'selectable',
    'props': {'groupId': 'plan_group', 'width': {'type': 'fill'},
              'height': {'type': 'hug'}},
}
bpay['elements']['map']['el_badge'] = {
    'id': 'el_badge', 'type': 'stack',
    'props': {'width': {'type': 'fixed', 'value': 90},
              'height': {'type': 'fixed', 'value': 24},
              'borderRadius': {'tl': 9999, 'tr': 9999, 'bl': 9999, 'br': 9999}},
}
bpay['elements']['map']['el_badge_label'] = {
    'id': 'el_badge_label', 'type': 'text',
    'props': {'content': {'values': {'en': [{'type': 'paragraph', 'content': [
        {'type': 'text', 'text': 'Free trial'}]}]}}},
}
bpay['elements']['hierarchy']['children'].append(
    {'id': 'el_plancard', 'children': [{'id': 'el_badge', 'children': [
        {'id': 'el_badge_label'}]}]})
rc, findings = run(badge)
check('silent on a static trial badge chip on a plan card (pill-shaped, names a '
      'trial, group member on a selling screen -- but no propsByState anywhere)',
      not of(findings, 'trial-toggle'), str(of(findings, 'trial-toggle')))

print('task 4 — period disclosure')

# SILENT on real product cards, measured before this check was written. The corpus is
# terse ("Yearly", "12 mo • $79.99") and every card names its period. `tabs-paywall.json`
# is the one documented exception -- see below -- because it is the const-purchase
# blind spot: its three products are bound through `const` purchase action payloads
# with NO `product` element, so there is no card for a card-scoped check to read, and
# (verified by reading the screen's own copy) it genuinely never states a period
# anywhere.
for path in corpus():
    if os.path.basename(path) == 'tabs-paywall.json':
        continue
    rc, findings = run(path)
    check(f'no-period-disclosed silent on {os.path.basename(path)}',
          not of(findings, 'no-period-disclosed'),
          str(of(findings, 'no-period-disclosed')))

# tabs-paywall.json's scr_RvSel001 is a real, shipped card-tier subscription screen
# (Revolut Metal/Premium/Standard). Its full text dump was read directly: "Metal",
# "Premium metal card", every feature row, "Get Metal" / "Get Premium" / "Get Standard
# on us", "Terms", "Restore", "Privacy" -- no period word ("month", "year", "annual",
# "/mo", "/yr", ...) appears anywhere on the screen. This is a TRUE finding, not a
# defect in the check: a real screen selling recurring subscriptions with no
# billing-frequency disclosure in the binary at all. Confirmed on both the tracked
# and raw copies (both present in `corpus()`).
for path in corpus():
    if os.path.basename(path) != 'tabs-paywall.json':
        continue
    rc, findings = run(path)
    check(f'no-period-disclosed correctly FIRES on the real const-purchase blind '
          f'spot ({path})',
          len(of(findings, 'no-period-disclosed')) == 1,
          str(of(findings, 'no-period-disclosed')))

# FIRES: strip every period word from the paywall screen's copy.
stripped = load()
for s in stripped['screens']:
    if s['id'] != 'scr_paywall':
        continue
    for eid, e in ((s.get('elements') or {}).get('map') or {}).items():
        if e.get('type') != 'text':
            continue
        blob = json.dumps(e['props'].get('content'))
        for word in ('Yearly', 'yearly', 'Monthly', 'monthly', 'year', 'month',
                     'Annual', 'annual', '/mo', '/yr'):
            blob = blob.replace(word, 'Pro')
        e['props']['content'] = json.loads(blob)
rc, findings = run(stripped)
npd = of(findings, 'no-period-disclosed')
check('fires when no period is stated anywhere on a selling screen', len(npd) >= 1, str(npd))
check('...as a risk', npd and all(f['severity'] == 'risk' for f in npd))
check('...citing the length requirement',
      npd and 'length' in npd[0]['fix'].lower(), str(npd))

# ONE finding per screen, not one per card -- a screen with four plan cards and no
# period anywhere is one omission, and four identical rows would bury the report.
check('one finding per screen, not per card', len(npd) == 1, str(npd))

# KNOWN LIMITATION (pinned, not desired behaviour -- accepted on review, not fixed).
# `_billing_context` treats a bare "per <unit>" as a billing claim (it exists to keep
# real cards like "12 mo • $79.99" recognised), so an ordinary feature bullet reading
# "10 workouts per week" satisfies it too, and `no-period-disclosed` stays SILENT on a
# screen with zero real disclosure. Ruling: `_billing_context` is pre-existing, shared
# with the already-shipped `period-claim-mismatch`, and calibrated against four
# measured false positives -- widening it for this new advisory check risks breaking a
# live check to fix a silence, and for an advisory check ("hazards, not verdicts") a
# miss is the cheaper error. If `_billing_context` is ever tightened, this goes red and
# whoever changes it finds this reasoning instead of rediscovering it.
per_week_bullet = copy.deepcopy(stripped)
for s in per_week_bullet['screens']:
    if s['id'] != 'scr_paywall':
        continue
    for eid, e in ((s.get('elements') or {}).get('map') or {}).items():
        if e.get('type') != 'text':
            continue
        e['props']['content'] = {'values': {'en': [
            {'type': 'paragraph', 'content': [
                {'type': 'text', 'text': '10 workouts per week'}]}]}}
        break
rc, findings = run(per_week_bullet)
check('KNOWN LIMITATION: no-period-disclosed stays silent on a feature bullet reading '
      '"10 workouts per week" with no real disclosure anywhere else on the screen '
      '(accepted false negative -- see comment above)',
      not of(findings, 'no-period-disclosed'),
      str(of(findings, 'no-period-disclosed')))

print('task 5 — trial terms')

for path in corpus():
    rc, findings = run(path)
    check(f'trial-terms-incomplete silent on {os.path.basename(path)}',
          not of(findings, 'trial-terms-incomplete'),
          str(of(findings, 'trial-terms-incomplete')))

# FIRES: a screen that promises a trial and says nothing about what follows it.
# Built by REWRITING the existing text elements rather than deleting them -- deleting
# would leave dangling `hierarchy` children, which `verify-config.py` would rightly
# call a broken document and which has nothing to do with what this check tests.
bare = load()
# The brief's own snippet names this element 'el_trial'; the real fixture's first
# text element on scr_paywall is 'el_066T', so a literal 'el_trial' key is never
# present in `bare['screens'][...]['elements']['map']` and the `withterms` mutation
# below would silently no-op. Captured here instead of hardcoded, so `withterms`
# edits the SAME element `bare` gave the trial copy to, whatever its real id is.
trial_el_id = None
for s in bare['screens']:
    if s['id'] != 'scr_paywall':
        continue
    first = True
    for eid, e in ((s.get('elements') or {}).get('map') or {}).items():
        if e.get('type') != 'text':
            continue
        text = 'Start your 7-day free trial' if first else 'Everything you need'
        if first:
            trial_el_id = eid
        first = False
        e['props']['content'] = {'values': {'en': [
            {'type': 'paragraph', 'content': [{'type': 'text', 'text': text}]}]}}
rc, findings = run(bare)
bare_findings = findings
tti = of(findings, 'trial-terms-incomplete')
check('fires on a trial promise with no terms', len(tti) == 1, str(tti))
check('...as a risk', tti and all(f['severity'] == 'risk' for f in tti))

# SILENT once the screen says what happens after the trial.
withterms = copy.deepcopy(bare)
for s in withterms['screens']:
    m = (s.get('elements') or {}).get('map') or {}
    if trial_el_id in m:
        m[trial_el_id]['props']['content']['values']['en'][0]['content'][0]['text'] = (
            'Start your 7-day free trial, then $79.99 per year. Cancel anytime.')
rc, findings = run(withterms)
check('silent once the charge after the trial is stated',
      not of(findings, 'trial-terms-incomplete'),
      str(of(findings, 'trial-terms-incomplete')))

# KNOWN LIMITATION (pinned, not desired behaviour -- accepted on review, not fixed).
# `after` searches the WHOLE screen-wide blob with no context restriction, so an
# unrelated currency amount elsewhere on the screen satisfies it even though it says
# nothing about the trial's own terms. Ruling: scoping `after` to the trial's own
# segment would manufacture the false POSITIVE this check specifically avoids -- the
# compliant layout states the trial in the hero and the charge in a footnote under the
# CTA, in different elements, and firing on that would be worse than this miss. If
# `after`'s scoping is ever tightened, this goes red and whoever changes it finds this
# reasoning instead of rediscovering it.
#
# The fixture writes the "$2" into exactly ONE element -- a footnote, which is the shape
# the limitation is about. An earlier version wrote it into EVERY non-first text element,
# which raised six `hardcoded-price` blockers as a side effect and taught a reader that
# the limitation needs a screen littered with money. Every other element gets neutral
# filler, not its original copy: the real copy states periods, which would satisfy
# `after` through `period_terms` and make this case pass for a reason that has nothing
# to do with `MONEY_RE`.
unrelated_money = load()
for s in unrelated_money['screens']:
    if s['id'] != 'scr_paywall':
        continue
    seen = 0
    for eid, e in ((s.get('elements') or {}).get('map') or {}).items():
        if e.get('type') != 'text':
            continue
        text = ('Start your free trial now' if seen == 0 else
                'Tip the developer $2' if seen == 1 else 'Everything you need')
        seen += 1
        e['props']['content'] = {'values': {'en': [
            {'type': 'paragraph', 'content': [{'type': 'text', 'text': text}]}]}}
rc, findings = run(unrelated_money)
check('KNOWN LIMITATION: trial-terms-incomplete stays silent when the only "after" '
      'signal on the screen is an unrelated currency amount ("Tip the developer $2") '
      '(accepted false negative -- see comment above)',
      not of(findings, 'trial-terms-incomplete'),
      str(of(findings, 'trial-terms-incomplete')))
check('...and the fixture no longer raises hardcoded-price blockers as a side effect '
      '(measured 6 before the one-footnote rewrite, 0 after -- the single "$2" sits '
      'outside every product card, so nothing else is reported alongside it)',
      not of(findings, 'hardcoded-price'),
      str([f['element'] for f in of(findings, 'hardcoded-price')]))

# A screen with neither period nor trial terms produces BOTH findings -- the two
# `check_disclosure` halves read the same per-screen blob independently. Uses the
# `bare` run's result (`findings` was reassigned by the `withterms` run above).
check('a screen with neither period nor trial terms produces both findings',
      len(of(bare_findings, 'no-period-disclosed')) == 1 and len(tti) == 1,
      str(bare_findings))

# ...and the REPORT collapses those two findings into ONE row. Measured before the
# collapse: two rows anchored to the same screen, where the second's message already
# carried the first's claim ("no price, no billing period, nothing about renewal")
# and the second's fix ("Free for 7 days, then $79.99/year") already satisfied the
# first. Same mechanism as the dead-affordance collapse -- `_collapse_for_report`,
# report-only, which is why the `--json` assertion above still sees both.
rc, bare_out = run(bare, report=True)
bare_store = _section(bare_out, 'STORE REVIEW — ADVISORY')
bare_rows = [l for l in bare_store.splitlines() if re.match(r'^\d+\. ', l)]
check('the report collapses the two disclosure findings into one row',
      len(bare_rows) == 1, str(bare_rows))
check('...and that one row names BOTH gaps, so nothing is dropped by merging',
      bare_rows and 'how often the subscription bills' in bare_rows[0]
      and 'when the trial ends' in bare_rows[0], str(bare_rows))
check('...and neither original message survives alongside it',
      'A user sees a price and a button' not in bare_store
      and 'never says what happens when it ends' not in bare_store, bare_store)
bare_nxt = (bare_out.split('WHAT TO DO NEXT', 1)[1]
            if 'WHAT TO DO NEXT' in bare_out else '')
check('...and the merged row is still routed in WHAT TO DO NEXT, exactly once',
      bare_nxt.count('State both next to the offer') == 1, bare_nxt[:600])

# The collapse requires BOTH halves on the same screen: a screen firing only
# `no-period-disclosed` keeps its own row, unmerged. `tabs-paywall.json` is the real
# export that fires exactly that one (see the FIRES case in task 4).
rc, tabs_out = run(os.path.join(FIX, 'tabs-paywall.json'), report=True)
tabs_store = _section(tabs_out, 'STORE REVIEW — ADVISORY')
check('a screen firing only no-period-disclosed keeps its own unmerged row',
      'nothing on this selling screen states how often' in tabs_store, tabs_store)

print('task 6 — external purchase link')

for path in corpus():
    rc, findings = run(path)
    check(f'external-purchase-link silent on {os.path.basename(path)}',
          not of(findings, 'external-purchase-link'),
          str(of(findings, 'external-purchase-link')))

# FIRES: a checkout link on the selling screen. APPENDED to el_088S's existing
# `interactions` rather than replacing them -- el_088S is the one element on
# `scr_paywall` that carries interactions, and its real `purchase` action is load-
# bearing for other checks. Replacing it (as the brief's own snippet did) would
# silently destroy that action and could make a SILENT case pass for a reason
# unrelated to what it tests. Corrected here per review: append a second interaction.
doc = load()
target, original = None, None
for s in doc['screens']:
    if s['id'] != 'scr_paywall':
        continue
    m = s['elements']['map']
    target = next(eid for eid, e in m.items() if e.get('interactions'))
    original = copy.deepcopy(m[target]['interactions'])
    m[target]['interactions'].append({'type': 'onTap', 'actions': [
        {'type': 'openUrl', 'payload': {'url': 'https://pay.example.com/checkout'}}]})
rc, findings = run(doc)
epl = of(findings, 'external-purchase-link')
check('fires on a checkout url on a selling screen', len(epl) == 1, str(epl))
check('...as a question, never a blocker',
      epl and all(f['severity'] == 'question' for f in epl), str(epl))
check('...quoting the url back', epl and 'pay.example.com' in epl[0]['message'], str(epl))
# This IS the "check that only fires on selling screens still fires" assertion the
# correction asked for: `check_external_purchase` is itself gated on
# `selling_screens`, so the FIRES row above already proves `scr_paywall` is still
# detected as selling. Restated explicitly, plus proof the append (not a replace)
# left el_088S's original `purchase` interaction intact.
check('scr_paywall is still a selling screen after the append '
      '(external-purchase-link only ever fires on a selling screen)',
      len(epl) == 1, str(epl))
for s in doc['screens']:
    if s['id'] != 'scr_paywall':
        continue
    m = s['elements']['map']
    ivs = m[target]['interactions']
    check("el_088S's original purchase interaction survives the append untouched",
          ivs[0] == original[0], str(ivs))
    check('el_088S now carries the original interaction plus the appended openUrl one',
          len(ivs) == len(original) + 1, str(ivs))

# SILENT under --stores android: 3.1.1 is Apple's rule.
rc, findings = run(doc, stores='android')
check('silent for an Android-only app', not of(findings, 'external-purchase-link'))

# SILENT for a terms link: the vocabulary must not swallow the legal links, which live
# on the same screen on essentially every paywall. Same append-not-replace correction
# as above.
legal = load()
for s in legal['screens']:
    if s['id'] != 'scr_paywall':
        continue
    m = s['elements']['map']
    ltarget = next(eid for eid, e in m.items() if e.get('interactions'))
    m[ltarget]['interactions'].append({'type': 'onTap', 'actions': [
        {'type': 'openUrl', 'payload': {'url': 'https://example.com/terms-of-service'}}]})
rc, findings = run(legal)
check('silent on a terms url', not of(findings, 'external-purchase-link'),
      str(of(findings, 'external-purchase-link')))

# SILENT on the three words dropped from PURCHASE_URL_WORDS after review -- pinning
# the vocabulary decision (payment mechanism, never product surface) with the
# reviewer's own concrete urls, so nobody re-adds `billing`/`upgrade`/`paywall` from a
# hunch without this case going red. Same append-not-replace construction as the
# terms-link case above, one screen per dropped word so each stays independently
# attributable if it ever regresses.
DROPPED_WORD_URLS = (
    ('billing', 'https://example.com/support/billing'),
    ('upgrade', 'https://example.com/why-upgrade'),
    ('paywall', 'https://yourapp.onelink.me/xyz?af_dp=yourapp://paywall'),
)
for word, url in DROPPED_WORD_URLS:
    dropped = load()
    for s in dropped['screens']:
        if s['id'] != 'scr_paywall':
            continue
        m = s['elements']['map']
        dtarget = next(eid for eid, e in m.items() if e.get('interactions'))
        m[dtarget]['interactions'].append({'type': 'onTap', 'actions': [
            {'type': 'openUrl', 'payload': {'url': url}}]})
    rc, findings = run(dropped)
    check(f'silent on a "{word}" url ({url}) -- dropped from PURCHASE_URL_WORDS, '
          'names a product surface/management path, not a payment mechanism',
          not of(findings, 'external-purchase-link'),
          str(of(findings, 'external-purchase-link')))

# FIRES: coverage for the kept half of the vocabulary beyond the one FIRES case
# already exercised above -- that case's url ('pay.example.com/checkout') matches
# BOTH 'pay' and 'checkout' at once, so it never proved any other kept word works in
# isolation. This url is chosen to hit exactly one: 'payment', on a host that names
# no other vocabulary word at all.
payment_doc = load()
for s in payment_doc['screens']:
    if s['id'] != 'scr_paywall':
        continue
    m = s['elements']['map']
    ptarget = next(eid for eid, e in m.items() if e.get('interactions'))
    m[ptarget]['interactions'].append({'type': 'onTap', 'actions': [
        {'type': 'openUrl',
         'payload': {'url': 'https://external.example.com/payment/confirm'}}]})
rc, findings = run(payment_doc)
payment_hits = of(findings, 'external-purchase-link')
check('fires on a /payment path, matching a kept word in isolation from checkout/pay',
      len(payment_hits) == 1, str(payment_hits))
check('...quoting the payment url back',
      payment_hits and 'external.example.com/payment/confirm' in payment_hits[0]['message'],
      str(payment_hits))

print('task 7 — report section')

# The six store-review check names -- what the checks below assert a config
# fires ONLY from, never "the checks this particular config happens to fire"
# (that was the old name, `STORE_ONLY_CHECK_NAMES`, and it read backwards at
# both use sites). Defined up front: the checks below need it before the
# synthesized config itself is built.
STORE_REVIEW_CHECK_NAMES = {
    'billed-amount-not-shown', 'derived-price-louder', 'trial-toggle',
    'no-period-disclosed', 'trial-terms-incomplete', 'external-purchase-link'}

# A flow whose ONLY findings are store-review ones must still read READY.
rc, out = run(MULTI, report=True)
rc, findings = run(MULTI)
check('the store-review section is printed', 'STORE REVIEW — ADVISORY' in out, out[:400])
check('the disclaimer is printed verbatim',
      'not guarantee' in out or 'not a guarantee' in out, out[:400])

# Fix round 1: the previous form of this check (`out.index('STORE REVIEW') >
# out.index('BLOCKERS')`) only proved ORDER -- it would hold even if a store-review
# finding's own text were ALSO printed a second time under RISKS -- and it raised
# `ValueError` (aborting the whole suite) on any report with no `STORE REVIEW`
# section at all, which is exactly what happened during this round's own Step 9
# negative test. Rewritten to a form that cannot raise (`_section` uses `.find`, not
# `.index`) and that asserts the real property: none of this flow's store-review
# finding MESSAGES appear inside the RISKS section's body text.
store_msgs = [f['message'] for f in findings if f['check'] in STORE_REVIEW_CHECK_NAMES]
check('MULTI has at least one store-review finding to check placement for -- the '
      'guard that stops the next assertion passing on an empty list',
      bool(store_msgs), str(findings))
check("no store-review finding's message is printed a second time inside RISKS",
      bool(store_msgs) and all(m not in _section(out, 'RISKS') for m in store_msgs),
      str(findings))

# Numbering continues into the section rather than restarting.
nums = [int(m.group(1)) for m in re.finditer(r'^(\d+)\. ', out, re.M)]
check('finding numbers are continuous and unique',
      bool(nums) and nums == list(range(1, len(nums) + 1)), str(nums))

# THE verdict test. The brief's own construction here was measured FALSE:
#
#     clean = load()
#     rc, findings = run(clean)
#     store_only = all(f['check'] in {...six names...} for f in findings)
#     if store_only: ...
#
# `onboarding-multilocale.json` fires `dead-affordance`, `no-restore`,
# `no-terms-link`, `no-privacy-link`, `no-escape-from-paywall`, `product-store-gap`
# and `untranslated` alongside its one store-review finding, so `store_only` is False
# and the `if` block -- which carries the central claim of this whole feature, that a
# store-review finding never changes the verdict -- never ran. Replaced below with a
# config SYNTHESIZED to be store-review-only (judgement call, made instead of pruning
# a real fixture down to nothing: every real fixture in the corpus carries enough
# screens/locales/products that suppressing every non-store family by subtraction is
# more fragile than building the handful of elements this needs directly), asserted
# UNCONDITIONALLY.
#
# Fix round 1, second defect: the first version of this config fired only TWO
# `risk`-severity checks, and `render()`'s verdict line reacts only to `blocker` and
# `question` severities -- measured, WITH the partition disabled the exact same
# `[risk, risk]` config still printed `READY FOR PRODUCTION`. So the "unconditional"
# assertions below were true whether the partition worked or not; they proved
# nothing about verdict isolation, only that the section renders. Fixed by adding
# `el_pay`, which fires `external-purchase-link` -- a `question` -- so the config now
# exercises the one severity that actually moves the verdict line, and the fix stays
# in the six-name set so the config is still genuinely store-review-only.
#
# The screen: `el_card` binds Pro Annual (a real, fully-cataloged product -- access
# level set, `app_store` entry present) via a `product` element and a wired
# `purchase` action, so the screen sells and the product passes every catalog check.
# `el_restore`/`el_terms`/`el_privacy`/`el_pay` each carry their OWN interaction
# (restorePurchases, two openUrls shaped like terms/privacy links, and one openUrl
# shaped like a payment link), which is what keeps `dead-affordance` silent --
# `_wired` only needs the element itself or an ancestor to carry an interaction, and
# here it is the element itself, so no `elements.hierarchy` tree is needed at all
# (every hierarchy-consuming helper in this module falls back to the node's own id
# when it finds no match, verified by reading `_find_node`/`_element_blobs`).
# `el_close` carries its own `closeFlow`, which makes `scr_paywall` both an escape
# screen and self-reaching in `_reaches`, silencing `no-escape-in-flow` and
# `no-escape-from-paywall` together. `--stores ios` is passed when running this
# config: Pro Annual has no `play_store` entry, and `product-store-gap`/
# `play-base-plan-missing` only fire for a store actually in `stores` (verified by
# reading `check_products_catalog` -- with `stores={'ios'}`, the missing `android` key
# is skipped by neither branch of its `if stores is None / elif want in stores`), and
# `external-purchase-link` itself requires `'ios' in stores` (or `stores is None`) to
# fire at all. `el_price` binds Pro Annual's `prod_price_per_month` variable -- the
# DERIVED, non-billed suffix for an annual product (`BILLED_SUFFIX['annual']` is
# `prod_price_per_year`, so `prod_price_per_month` is never the billed amount here),
# with no `prod_price_per_year`/`prod_price` variable anywhere else on the screen --
# which is exactly `billed-amount-not-shown`'s FIRES shape. No text on the screen
# states a period in words either, so `no-period-disclosed` fires too -- both are in
# the six-name set, so the config stays store-review-only either way.
ANNUAL = '6cdd73d5-bdb2-4b2e-c207-784fbcb2f408'   # Pro Annual, catalog-fixture.json

def _para(text):
    return [{'type': 'paragraph', 'content': [{'text': text, 'type': 'text', 'attrs': {}}]}]


store_only_config = {
    'screens': [{'id': 'scr_paywall', 'elements': {'map': {
        # A per-unit (monthly) price for an ANNUAL product with no billed (yearly)
        # amount anywhere on the screen -- fires `billed-amount-not-shown` -- same
        # shape as `onboarding-multilocale.json`'s own el_075T.
        'el_price': {
            'id': 'el_price', 'type': 'text',
            'props': {'content': {'values': {'en': [
                {'type': 'paragraph', 'content': [
                    {'type': 'variable',
                     'attrs': {'variableId': f'{ANNUAL}.prod_price_per_month'}}]}]}}}},
        'el_card': {
            'id': 'el_card', 'type': 'product',
            'props': {'product': {'id': ANNUAL}},
            'interactions': [{'id': 'i_buy', 'trigger': 'tap', 'actions': [
                {'id': 'a_buy', 'type': 'purchase', 'payload': {}}]}]},
        'el_restore': {
            'id': 'el_restore', 'type': 'text',
            'props': {'content': {'values': {'en': _para('Restore purchases')}}},
            'interactions': [{'id': 'i_restore', 'trigger': 'tap', 'actions': [
                {'id': 'a_restore', 'type': 'restorePurchases', 'payload': {}}]}]},
        'el_terms': {
            'id': 'el_terms', 'type': 'text',
            'props': {'content': {'values': {'en': _para('Terms')}}},
            'interactions': [{'id': 'i_terms', 'trigger': 'tap', 'actions': [
                {'id': 'a_terms', 'type': 'openUrl',
                 'payload': {'url': 'https://example.com/terms-of-service'}}]}]},
        'el_privacy': {
            'id': 'el_privacy', 'type': 'text',
            'props': {'content': {'values': {'en': _para('Privacy')}}},
            'interactions': [{'id': 'i_privacy', 'trigger': 'tap', 'actions': [
                {'id': 'a_privacy', 'type': 'openUrl',
                 'payload': {'url': 'https://example.com/privacy-policy'}}]}]},
        # closeFlow on the selling screen itself -- self-reaching, so both
        # `no-escape-in-flow` and `no-escape-from-paywall` stay silent.
        'el_close': {
            'id': 'el_close', 'type': 'icon', 'props': {},
            'interactions': [{'id': 'i_close', 'trigger': 'tap', 'actions': [
                {'id': 'a_close', 'type': 'closeFlow', 'payload': {}}]}]},
        # Fix round 1: an openUrl shaped like a payment page, so the config also
        # fires `external-purchase-link` -- a QUESTION, the one severity that
        # actually moves the verdict line -- and the unconditional assertions below
        # stop being vacuous. The reviewer's measured element (adapted to this
        # config's `_para` convention).
        'el_pay': {
            'id': 'el_pay', 'type': 'text',
            'props': {'content': {'values': {'en': _para('More')}}},
            'interactions': [{'id': 'i_pay', 'trigger': 'tap', 'actions': [
                {'id': 'a_pay', 'type': 'openUrl',
                 'payload': {'url': 'https://external.example.com/payment/confirm'}}]}]},
    }}}],
    'locales': [{'code': 'en'}], 'defaultLocale': 'en'}

rc, so_findings = run(store_only_config, stores='ios')
check('the synthesized config fires (this is what makes the unconditional verdict '
      'assertions below non-vacuous)', bool(so_findings), str(so_findings))
check('...and fires ONLY store-review checks',
      bool(so_findings) and all(f['check'] in STORE_REVIEW_CHECK_NAMES for f in so_findings),
      str(so_findings))
check('...and includes a QUESTION-severity finding -- a risk-only config cannot '
      'distinguish the verdict WITH the partition from the verdict WITHOUT it '
      '(both print READY FOR PRODUCTION; measured), so this is what makes the '
      'verdict assertions below load-bearing rather than vacuous',
      any(f['severity'] == 'question' for f in so_findings), str(so_findings))

rc, so_out = run(store_only_config, stores='ios', report=True)
check('a store-review-only flow still reads READY FOR PRODUCTION',
      'READY FOR PRODUCTION' in so_out and 'NOT READY' not in so_out, so_out[:400])
check('...and is not downgraded to READY, PENDING', 'PENDING' not in so_out, so_out[:400])
check('...and exits 0', rc == 0, f'rc={rc}')
check('...and the STORE REVIEW — ADVISORY section is present with at least one '
      'finding in it -- the conjunct that stops this passing on a report with '
      'nothing in it at all',
      'STORE REVIEW — ADVISORY' in so_out and '1. ' in so_out.split('STORE REVIEW', 1)[1],
      so_out)

# Fix round 1: the previous discriminator here (`'storefront' not in
# nxt.split('Change in the flow')[0]`) can never fail. `storefront` appears only in
# `external-purchase-link`'s own message/fix text, and `_next_step_line` for
# GROUP_ANSWER never prints either -- it calls `_answer_prompt`, which for any check
# outside its named cases falls through to `f'See finding {n} -- your answer may
# change the verdict.'`, containing no such word. It was also vacuous on MULTI
# specifically: `external-purchase-link` never fires there. Replaced with a real
# discriminator run against `store_only_config`'s own WHAT TO DO NEXT, whose only
# `question` (`external-purchase-link`) is a store-review check and therefore (per
# `VERDICT_CONDITIONAL`, which names none of the six) can never produce an Answer
# line -- so `'Answer these'` must be absent from this report outright.
so_nxt = so_out.split('WHAT TO DO NEXT', 1)[1] if 'WHAT TO DO NEXT' in so_out else ''
check('the store-only config has a question-severity finding to test the Answer '
      'group against', bool(so_nxt), so_out)
check('no store-review finding lands in the Answer group -- its only question is a '
      'store-review check, so "Answer these" must not appear at all',
      bool(so_nxt) and 'Answer these' not in so_nxt, so_nxt[:400])

# Every store-review finding must still be routed by WHAT TO DO NEXT -- the guarantee
# that no numbered finding is silently dropped from the plan.
nxt = out.split('WHAT TO DO NEXT', 1)[1] if 'WHAT TO DO NEXT' in out else ''
check('MULTI has at least one store-review finding to route -- the guard that stops '
      'this loop passing vacuously if MULTI ever stops firing one',
      any(f['check'] in STORE_REVIEW_CHECK_NAMES for f in findings), str(findings))
for f in findings:
    if f['check'] in STORE_REVIEW_CHECK_NAMES:
        check(f'{f["check"]} is routed in WHAT TO DO NEXT',
              f['fix'].rstrip('.')[:40] in nxt, nxt[:400])

print('task 8 — before you ship')
bys = out.split('BEFORE YOU SHIP', 1)[1].split('WHAT TO DO NEXT')[0]
check('names the unapproved-products trap', 'App Store Connect' in bys, bys)
check('names the metadata link requirement', 'metadata' in bys.lower(), bys)
check('still names the placement gap', 'placement' in bys, bys)

# The Play new-account bullet was CUT, not gated. It is about the developer ACCOUNT
# rather than the flow, the app or the store; it applies only to a first-time PERSONAL
# account, which excludes nearly every Adapty customer; and it printed on every audit
# forever. Asserted as an absence so nobody re-adds it from the guideline text.
check('the Play 12-testers/14-days account bullet is GONE (cut, not gated)',
      '12 testers' not in bys and '14 consecutive' not in bys, bys)

# The remaining reminders are gated, because unverifiable is not the same as always
# relevant. `vpn-timer-draft.json`: three screens, no bound products, zero findings --
# measured at 21 report lines before this gate and 16 after, the removed 5 being
# boilerplate telling a non-selling flow to get its products approved.
rc, nosell = run(os.path.join(FIX, 'vpn-timer-draft.json'), catalog=None, report=True)
nosell_bys = nosell.split('BEFORE YOU SHIP', 1)[1].split('WHAT TO DO NEXT')[0]
check('a flow that binds no products gets no App Store Connect products reminder',
      'products are approved' not in nosell_bys, nosell_bys)
check('...but still gets the placement reminder, which is unconditional',
      'placement' in nosell_bys, nosell_bys)

# `render(stores=...)` -- the reminders are fixed report text, not findings, so store
# scoping needs its own route. Measured before: `--stores android` printed both App
# Store Connect bullets.
rc, ios_out = run(MULTI, stores='ios', report=True)
rc, and_out = run(MULTI, stores='android', report=True)
ios_bys = ios_out.split('BEFORE YOU SHIP', 1)[1].split('WHAT TO DO NEXT')[0]
and_bys = and_out.split('BEFORE YOU SHIP', 1)[1].split('WHAT TO DO NEXT')[0]
check('the App Store Connect metadata reminder prints for an iOS app',
      'metadata' in ios_bys.lower(), ios_bys)
check('...and is skipped for an app that does not ship on iOS',
      'metadata' not in and_bys.lower(), and_bys)
check('...and still prints when the stores are UNKNOWN (default None keeps the old '
      'behaviour)', 'metadata' in bys.lower(), bys)

if fails:
    print(f'\n{len(fails)} FAILED')
    for f in fails:
        print('  -', f)
    sys.exit(1)
print('\nall passed')

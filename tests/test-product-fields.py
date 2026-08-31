#!/usr/bin/env python3
"""Calibration for the product-variable field check in `references/verify-config.py`.

Repo-only. Runs the shipped script as a subprocess -- never imports it, so nothing writes a
`__pycache__` into `references/`.

Why this exists. The transform service refuses a product variable naming a field outside its
closed set (`unknown_product_field`), and it treats that specifically as the author's own typo --
fixable, unlike the product-registry codes beside it. This repo's price-variable check was keyed
on the substring `.prod_`, so it validated the head of a `prod_*` variable and **skipped every
`offer_*` and `is_*` variable entirely, head included**. Measured before the fix, both silent:

    <valid-uuid>.prod_price_per_fortnight        -- bogus field, valid head
    <bogus-uuid>.offer_price                     -- valid field, bogus head, skipped outright

The second matters more than it looks: the `offer_*` family is what an agent is told to bind for
trial and intro-offer copy, so the least-validated variables were the ones most likely to be
newly authored.

The set is closed and that was checked, not assumed: it comes from the public
[Element variables](https://adapty.io/docs/onboarding-variables.md) page the skill already links,
and the corpus's 15 distinct variableIds use only `prod_price`, `prod_price_per_month` and
`prod_price_per_year` -- nothing product-shaped the set lacks.

    FIRES   -- a field outside the set, in either family; a bad head on an `offer_*` variable
    SILENT  -- every documented field, the non-product variable shapes, and all 12 real configs

Usage: python3 tests/test-product-fields.py     # 0 all pass, 1 a case regressed
"""
import copy, glob, json, os, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERIFY = os.path.join(ROOT, 'skills', 'flow-generator', 'references', 'verify-config.py')
CORPUS = os.path.join(ROOT, 'tests', 'fixtures')
RAW = os.path.join(ROOT, 'tests', 'fixtures-raw')
SEED = os.path.join(CORPUS, 'onboarding-quiz-paywall.json')

FIELD = 'is not a product variable field'
HEAD = 'price variable references a product bound nowhere'
GROUP = 'group-relative price variable on unknown product group'

DOCUMENTED = ['prod_title', 'prod_price', 'prod_price_per_day', 'prod_price_per_week',
              'prod_price_per_month', 'prod_price_per_year', 'offer_price',
              'offer_billing_period', 'offer_full_duration', 'is_free_trial',
              'is_pay_up_front', 'is_pay_as_you_go']

fails = []


def run(doc):
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, 'c.json')
        json.dump(doc, open(path, 'w'))
        r = subprocess.run([sys.executable, VERIFY, path], capture_output=True, text=True)
    if 'Traceback' in r.stderr:
        raise AssertionError(f'verify-config.py crashed:\n{r.stderr}')
    return [l.strip() for l in r.stdout.splitlines()
            if FIELD in l or HEAD in l or GROUP in l]


def fires(name, doc, fragment):
    hits = run(doc)
    if not any(fragment in l for l in hits):
        fails.append(f'{name}: expected {fragment!r}, got {hits!r}')
        print(f'  FAIL  {name}')
    else:
        print(f'  ok    {name}')


def silent(name, doc):
    hits = run(doc)
    if hits:
        fails.append(f'{name}: expected no product-variable finding, got {hits!r}')
        print(f'  FAIL  {name}')
    else:
        print(f'  ok    {name}')


# The seed is a real export carrying real declared products and real price variables. Swapping
# one variableId keeps everything else -- declarations, bindings, hierarchy -- genuine.
SEED_DOC = json.load(open(SEED))
_raw = json.dumps(SEED_DOC)
REAL_VID = sorted({v for v in
                   __import__('re').findall(r'"variableId":\s*"([^"]*prod_[^"]*)"', _raw)})[0]
REAL_UUID = REAL_VID.split('.')[0]


def swapped(new_vid):
    return json.loads(_raw.replace(REAL_VID, new_vid))


# ------------------------------------------------------------------------------- FIRES
print(f'FIRES on a bad field (seed variable: {REAL_VID[:20]}...):')
fires('a plausible-but-wrong period — "prod_price_per_fortnight"',
      swapped(f'{REAL_UUID}.prod_price_per_fortnight'), FIELD)
fires('a misspelled offer field — "offer_prise"',
      swapped(f'{REAL_UUID}.offer_prise'), FIELD)
fires('a misspelled boolean — "is_freetrial"',
      swapped(f'{REAL_UUID}.is_freetrial'), FIELD)
fires('a field from no family at all that still starts prod_ — "prod_savings_percent"',
      swapped(f'{REAL_UUID}.prod_savings_percent'), FIELD)

print('\nFIRES on a bad head, in the families the old check skipped:')
fires('a bogus product uuid on an offer_ variable (was silent before)',
      swapped('00000000-dead-beef-0000-000000000000.offer_price'), HEAD)
fires('a bogus product uuid on an is_ variable (was silent before)',
      swapped('00000000-dead-beef-0000-000000000000.is_free_trial'), HEAD)
fires('a group-relative offer variable on an unknown group',
      swapped('no-such-group.selectedProduct.offer_price'), GROUP)

# ------------------------------------------------------------------------------- SILENT
print('\nSILENT on every documented field (the set must not be under-inclusive):')
for f in DOCUMENTED:
    silent(f'{REAL_UUID[:8]}….{f}', swapped(f'{REAL_UUID}.{f}'))

print('\nSILENT on the other variable shapes — these are not product variables:')
for other in ('email.value', 'first_name.value', 'plans.selectedProduct',
              'quiz.selectedOptionId', 'products.selectedProduct'):
    silent(other, swapped(other))

_paths = sorted(glob.glob(os.path.join(CORPUS, '*.json'))) + \
         sorted(glob.glob(os.path.join(RAW, '*.json')))
print(f'\nSILENT on the corpus ({len(_paths)} configs'
      f'{" — RAW ABSENT, tracked only" if not os.path.isdir(RAW) else ""}):')
for _p in _paths:
    silent(os.path.basename(_p), json.load(open(_p)))

print()
if fails:
    print(f'{len(fails)} FAILED')
    for f in fails:
        print('  -', f)
    sys.exit(1)
print('all checks passed')

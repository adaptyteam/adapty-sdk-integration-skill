#!/usr/bin/env python3
"""Calibration for `skills/flow-generator/references/diff-config.py`.

Repo-only, like everything else under `tests/`. It runs the shipped script as a subprocess --
never imports it, so nothing writes a `__pycache__` into `references/`, which the copy-install
path would ship.

Two halves, and both matter equally. A diff that misses a removal loses a colleague's work; a
diff that reports a builder save as destruction gets ignored within a day, and then it loses a
colleague's work too. So every case below asserts a direction:

    FIRES   -- an injected loss must be reported, with the count the report should collapse to
    SILENT  -- a change that destroys nothing must produce nothing

Usage: python3 tests/test-diff-config.py      # 0 all pass, 1 a case regressed
"""
import copy, json, os, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIFF = os.path.join(ROOT, 'skills', 'flow-generator', 'references', 'diff-config.py')
CORPUS = os.path.join(ROOT, 'tests', 'fixtures')
SRC = os.path.join(CORPUS, 'onboarding-quiz-paywall.json')

fails = []


def run(a, b):
    """Return (rc, removed, changed, added) -- the collapsed item counts the report prints,
    not the raw fact counts, because the item counts are what a reader acts on."""
    with tempfile.TemporaryDirectory() as tmp:
        pa, pb = os.path.join(tmp, 'a.json'), os.path.join(tmp, 'b.json')
        for path, doc in ((pa, a), (pb, b)):
            if isinstance(doc, str):
                path_src = doc
                with open(path, 'w') as fh:
                    fh.write(open(path_src).read())
            else:
                json.dump(doc, open(path, 'w'))
        r = subprocess.run([sys.executable, DIFF, pa, pb], capture_output=True, text=True)
    line = [l for l in r.stdout.splitlines() if l.startswith('summary:')]
    if not line:
        return r.returncode, None, None, None
    nums = line[0].split('summary:')[1].split('(')[0]
    got = [int(x.strip().split()[0]) for x in nums.split(',')]
    return (r.returncode, *got)


def case(label, a, b, rc, removed, changed, added):
    got = run(a, b)
    want = (rc, removed, changed, added)
    ok = got == want
    print(f'{"pass" if ok else "FAIL"}  {label:52} {got}')
    if not ok:
        fails.append(f'{label}: wanted {want}, got {got}')


D = json.load(open(SRC))

# --- SILENT: nothing was destroyed, so nothing may be reported ---------------------------
for name in sorted(os.listdir(CORPUS)):
    if name.endswith('.json'):
        p = os.path.join(CORPUS, name)
        case(f'silent: {name} against itself', p, p, 0, 0, 0, 0)

b = copy.deepcopy(D); b['screens'] = b['screens'][::-1]
case('silent: screens reordered (identity is the id)', D, b, 0, 0, 0, 0)

b = copy.deepcopy(D); b['_meta']['icons'] = b['_meta']['icons'][::-1]
case('silent: _meta.icons re-sorted (a builder save)', D, b, 0, 0, 0, 0)

env = {'config': copy.deepcopy(D), 'remote_configs': [], 'status': 'draft',
       'updated_at': 1756000000}
case('silent: envelope against its own bare config', env, D, 0, 0, 0, 0)

# Key order INSIDE an object, which is a different mechanism from collection order above: this
# one is `canon`'s sorted keys, that one is identity-based addressing. Both need their own case,
# because breaking either leaves the other's case passing.
b = copy.deepcopy(D)
for s_ in b['screens']:
    for e in s_['elements']['map'].values():
        if isinstance(e.get('props'), dict):
            e['props'] = {k: e['props'][k] for k in reversed(list(e['props']))}
case('silent: key order permuted inside every props', D, b, 0, 0, 0, 0)

# The v9 -> v10 fill migration is deliberately NOT silent -- it changes a value's shape. Pinned
# so the number stays honest in merge.md: a block of props changes is the signature to recognise,
# not something the diff hides.
b = copy.deepcopy(D)
rewritten = 0
def to_array(o):
    global rewritten
    if isinstance(o, dict):
        if isinstance(o.get('fill'), dict):
            o['fill'] = [o['fill']]; rewritten += 1
        for v in o.values():
            to_array(v)
    elif isinstance(o, list):
        for v in o:
            to_array(v)
to_array(b['screens'])
assert rewritten == 29, f'fixture drifted: {rewritten} object fills, expected 29'
case('reported: 29 fills object -> array (a builder save)', D, b, 0, 0, 25, 0)

# --- FIRES: a loss must be named, and collapsed to the thing a user recognises ------------
b = copy.deepcopy(D); b['screens'].pop(2)
case('fires: one screen deleted (collapses to 1 line)', D, b, 1, 1, 0, 0)

b = copy.deepcopy(D); b['_meta']['screens'] = {}
case('fires: _meta.screens emptied (script rebuild)', D, b, 1, 2, 0, 0)

b = copy.deepcopy(D)
m = b['screens'][0]['elements']['map']
for k in list(m)[:6]:
    del m[k]
case('fires: 6 elements deleted from one screen', D, b, 1, 6, 0, 0)

b = copy.deepcopy(D)
m = b['screens'][0]['elements']['map']
old = list(m)[3]
e = m.pop(old); e['id'] = old + '_x'; m[old + '_x'] = e
case('fires: element id renamed (1 removed + 1 added)', D, b, 1, 1, 0, 1)

# A locale drop, the loss with no visual tell at all: `config preview` renders one locale, so
# nothing in the render loop can see this one (preview.md). Synthesised, since every tracked
# fixture is single-locale.
two = copy.deepcopy(D)
two['locales'].append({'id': 'de', 'code': 'de', 'name': 'German'})
added = 0
def sprinkle(o):
    global added
    if isinstance(o, dict):
        v = o.get('values')
        if isinstance(v, dict) and 'en' in v and added < 40:
            v['de'] = v['en']; added += 1
        for x in o.values():
            sprinkle(x)
    elif isinstance(o, list):
        for x in o:
            sprinkle(x)
sprinkle(two['screens'])
assert added == 40, f'fixture drifted: only {added} localizable fields found'
case('fires: the de locale dropped (locale + 40 fields)', two, D, 1, 41, 0, 0)

# --- CHANGES are not removals: a rewrite must not read as destruction --------------------
b = copy.deepcopy(D)
def first_string(o):
    if isinstance(o, dict):
        v = o.get('values')
        if isinstance(v, dict) and isinstance(v.get('en'), str):
            v['en'] = 'CHANGED'; return True
        return any(first_string(x) for x in o.values())
    if isinstance(o, list):
        return any(first_string(x) for x in o)
    return False
assert first_string(b['screens']), 'fixture drifted: no plain localizable string found'
case('changes: one string rewritten (exit 0, no removal)', D, b, 0, 0, 1, 0)

# --- The same path twice must be refused, never reported as clean ------------------------
r = subprocess.run([sys.executable, DIFF, SRC, SRC], capture_output=True, text=True)
ok = r.returncode == 2 and 'same file' in r.stdout
print(f'{"pass" if ok else "FAIL"}  {"refused: the same path as both arguments":52} '
      f'(rc={r.returncode})')
if not ok:
    fails.append('same path twice was not refused')

print()
if fails:
    print(f'{len(fails)} FAILED')
    for f in fails:
        print(f'  - {f}')
    sys.exit(1)
print('all checks passed')

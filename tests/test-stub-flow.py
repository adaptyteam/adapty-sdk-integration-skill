"""The shipped stub must clear BOTH gates, and the floor must stay pinned.

Measured 2026-09-03 against the real transform service: a screen with NO
elements is refused (`Generated JSON failed schema validation`) however much
theme it carries, and a one-text config with no theme passes the service but
fails verify-config.py on a dangling font preset. Both directions are pinned
here so nobody "simplifies" the artifact back below the floor.
"""
import json
import pathlib
import subprocess
import sys

sys.dont_write_bytecode = True

ROOT = pathlib.Path(__file__).resolve().parent.parent
STUB = ROOT / 'skills' / 'migrate-placements' / 'references' / 'stub-flow.json'
VERIFY = ROOT / 'skills' / 'flow-generator' / 'references' / 'verify-config.py'

failures = []


def check(label, ok, detail=''):
    print(f'{"ok  " if ok else "FAIL"}  {label}' + (f'  -- {detail}' if detail and not ok else ''))
    if not ok:
        failures.append(label)


def verify(cfg, tmpname):
    path = ROOT / 'tests' / tmpname
    path.write_text(json.dumps(cfg))
    try:
        r = subprocess.run([sys.executable, str(VERIFY), str(path)],
                           capture_output=True, text=True)
        return r.returncode, r.stdout + r.stderr
    finally:
        path.unlink(missing_ok=True)


cfg = json.loads(STUB.read_text())

check('stub is a bare config, not an envelope', 'config' not in cfg and 'screens' in cfg)
check('exactly one screen', len(cfg['screens']) == 1)
scr = cfg['screens'][0]
check('the screen has at least one element -- the measured publishable floor',
      len(scr['elements']['map']) >= 1)
check('every hierarchy child resolves in the map',
      all(c['id'] in scr['elements']['map'] for c in scr['elements']['hierarchy']['children']))

presets = {t['id'] for t in cfg['theme']['typography']}
used = {e['props']['font']['preset'] for e in scr['elements']['map'].values()
        if isinstance(e.get('props', {}).get('font'), dict)}
check('every font preset used is declared in the theme -- the themeless variant failed here',
      used <= presets, f'used={sorted(used)} declared={sorted(presets)}')

colors = {c['id'] for c in cfg['theme']['colors']}
check('theme declares the colors the screen and element reference',
      {'bg', 'ink'} <= colors)

check('the stub binds no products -- it is content-free on purpose',
      cfg['_meta']['screens'] == {})

rc, out = verify(cfg, '_stub_probe.json')
check('verify-config.py accepts the stub', rc == 0, out.strip()[:300])

# The publishable floor (a screen must contain at least one element) is enforced
# locally by the "at least one element" check above, and against the real
# transform service by `flows config validate` at build time. A local test
# cannot prove the service's floor: the SERVICE refuses an empty screen,
# verify-config.py does not, so asserting it here would test nothing.

print()
print(f'{len(failures)} failure(s)' if failures else 'all checks passed')
sys.exit(1 if failures else 0)

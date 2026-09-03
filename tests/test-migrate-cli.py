"""The CLI entry point, driven offline.

`--adapty` is a command STRING, so these tests point it at a stub script that
prints fixture JSON. That keeps `inventory` testable without an account, and
proves the pagination loop issues one call per page.
"""
import json
import os
import pathlib
import subprocess
import sys

sys.dont_write_bytecode = True

ROOT = pathlib.Path(__file__).resolve().parent.parent
MIGRATE = ROOT / 'skills' / 'migrate-placements' / 'references' / 'migrate.py'
TMP = ROOT / 'tests' / '_migrate_cli_tmp'

failures = []


def check(label, ok, detail=''):
    print(f'{"ok  " if ok else "FAIL"}  {label}' + (f'  -- {detail}' if detail and not ok else ''))
    if not ok:
        failures.append(label)


def flag(cmd, name):
    """The value after `name` in an argv list, or None. Defensive on purpose:
    a check that raises aborts the suite, and the checks below it then look
    green by never having run."""
    cmd = cmd or []
    return cmd[cmd.index(name) + 1] if name in cmd and cmd.index(name) + 1 < len(cmd) else None


TMP.mkdir(exist_ok=True)
shim = TMP / 'fake-adapty.py'
shim.write_text('''#!/usr/bin/env python3
"""Stand-in for the adapty CLI. 3 placements over 2 pages at page size 2."""
import json, sys
a = sys.argv[1:]
PL = [
    {"id": "pl-a", "developer_id": "main", "title": "Main"},
    {"id": "pl-b", "developer_id": "onboarding", "title": "Onb"},
    {"id": "pl-c", "developer_id": "settings", "title": "Set"},
]
DETAIL = {
    "pl-a": [{"segment_ids": [], "paywall_id": "pw-1", "priority": 0}],
    "pl-b": [{"segment_ids": ["s1"], "paywall_id": "pw-1", "priority": 0},
             {"segment_ids": ["s2"], "paywall_id": "pw-2", "priority": 1}],
    "pl-c": [{"content_type": "flow", "flow_id": "f-9", "priority": 0}],
}
if a[:2] == ["placements", "list"]:
    size = int(a[a.index("--page-size") + 1]) if "--page-size" in a else 20
    page = int(a[a.index("--page") + 1]) if "--page" in a else 1
    start = (page - 1) * size
    chunk = PL[start:start + size]
    pages = max(1, -(-len(PL) // size))
    print(json.dumps({"data": chunk,
                      "meta": {"pagination": {"count": len(PL), "page": page, "pages": pages}}}))
    sys.exit(0)
if a[:2] == ["placements", "get"]:
    pid = a[a.index("--app") + 2]
    row = next(p for p in PL if p["id"] == pid)
    print(json.dumps(dict(row, audiences=DETAIL[pid])))
    sys.exit(0)
print("unexpected: " + " ".join(a), file=sys.stderr)
sys.exit(9)
''')

ADAPTY = f'{sys.executable} {shim}'
inv = TMP / 'inventory.json'

r = subprocess.run([sys.executable, str(MIGRATE), 'inventory', '--app', 'app-1',
                    '--adapty', ADAPTY, '--page-size', '2', '--out', str(inv)],
                   capture_output=True, text=True)
check('inventory exits 0', r.returncode == 0, r.stderr.strip()[:300])
data = json.loads(inv.read_text()) if inv.exists() else {}
check('inventory wrote a file with every placement -- BOTH pages, not just page 1',
      len(data.get('placements', [])) == 3, str(len(data.get('placements', []))))
check('inventory carries audiences from the per-placement get',
      all('audiences' in p for p in data.get('placements', [])))
check('inventory records the app id', data.get('app') == 'app-1')

r2 = subprocess.run([sys.executable, str(MIGRATE), 'plan', '--inventory', str(inv)],
                    capture_output=True, text=True)
check('plan exits 0', r2.returncode == 0, r2.stderr.strip()[:300])
plan = json.loads(r2.stdout) if r2.returncode == 0 else {}
check('plan needs one flow per distinct paywall (pw-1, pw-2)',
      len(plan.get('flows_needed', [])) == 2, str(plan.get('flows_needed')))
check('plan proposes a new developer id for each migratable placement',
      sorted(p['proposed_developer_id'] for p in plan.get('placements', []))
      == ['main-flow', 'onboarding-flow'], str(plan.get('placements')))
check('plan never proposes an existing developer id',
      not ({p['proposed_developer_id'] for p in plan.get('placements', [])}
           & {'main', 'onboarding', 'settings'}))
check('plan excludes the already-flow placement',
      'settings' not in {p['source_developer_id'] for p in plan.get('placements', [])})
check('plan preserves segment_ids and priority per audience',
      any(a['segment_ids'] == ['s2'] and a['priority'] == 1
          for p in plan.get('placements', []) for a in p['audiences']),
      str(plan.get('placements')))
counts_only = {k: v for k, v in (plan.get('summary') or {}).items()
               if k not in ('scope', 'exposure')}
check('plan carries the summary block through from migratable_summary',
      counts_only == {'placements': 2, 'audiences': 3, 'paywalls': 2,
                      'already_flow': 1, 'empty': 0},
      str(plan.get('summary')))
check('the five counts, the account-wide scope and the plan-row exposure are three '
      'SEPARATE blocks -- none of them silently stands in for another',
      set(plan.get('summary') or {})
      == {'placements', 'audiences', 'paywalls', 'already_flow', 'empty',
          'scope', 'exposure'}, str(sorted(plan.get('summary') or {})))

check('plan without --flows emits no command key -- the flag is purely additive',
      all('command' not in p and 'missing_flows' not in p
          for p in plan.get('placements', [])), str(plan.get('placements')))

r3 = subprocess.run([sys.executable, str(MIGRATE), 'nope'], capture_output=True, text=True)
check('an unknown subcommand exits non-zero', r3.returncode != 0)

# --- A MISBEHAVING CLI RESPONSE IS THE ENVIRONMENT, NOT A TOOL BUG (exit 2) ---
#
# `_read_inventory` cannot help here: these come off `placements list`, not out of a
# file. The two places this module reads into a response -- a summary's `id` and
# `meta.pagination.pages` -- are routed through CliError so they land on 2. Left as
# bare subscripts they were a KeyError and a ValueError reaching the catch-all and
# being reported as "a bug in migrate.py". Found by a mutation that reddened nothing.

bad_shim = TMP / 'fake-adapty-bad.py'
bad_shim.write_text('''#!/usr/bin/env python3
"""Returns a deliberately malformed `placements list`, per BAD_MODE."""
import json, os, sys
a = sys.argv[1:]
mode = os.environ.get("BAD_MODE", "")
if a[:2] == ["placements", "list"]:
    if mode == "no-id":
        rows = [{"developer_id": "main", "title": "Main"}]
        pages = 1
    elif mode == "bad-pages":
        rows = [{"id": "pl-a", "developer_id": "main", "title": "Main"}]
        pages = "lots"
    else:
        rows, pages = [], 1
    print(json.dumps({"data": rows,
                      "meta": {"pagination": {"count": len(rows), "page": 1,
                                              "pages": pages}}}))
    sys.exit(0)
if a[:2] == ["placements", "get"]:
    print(json.dumps({"id": "pl-a", "developer_id": "main", "audiences": []}))
    sys.exit(0)
sys.exit(9)
''')


def bad_response(mode, out_name):
    return subprocess.run(
        [sys.executable, str(MIGRATE), 'inventory', '--app', 'app-1',
         '--adapty', f'{sys.executable} {bad_shim}', '--out', str(TMP / out_name)],
        capture_output=True, text=True, env=dict(os.environ, BAD_MODE=mode))


r21 = bad_response('no-id', 'bad-no-id.json')
check('a `placements list` row with NO usable id exits 2 with its own message',
      r21.returncode == 2 and 'no usable "id"' in r21.stderr,
      f'{r21.returncode} {r21.stderr[:160]}')
check('and it does not blame the tool', 'bug in migrate.py' not in r21.stderr, r21.stderr)
check('and it says which row and what it got',
      'index 0' in r21.stderr and 'no usable "id"' in r21.stderr, r21.stderr)
check('and prints no traceback', 'Traceback' not in r21.stderr, r21.stderr)

r22 = bad_response('bad-pages', 'bad-pages.json')
check('a non-numeric meta.pagination.pages exits 2 with its own message',
      r22.returncode == 2 and 'not a page count' in r22.stderr,
      f'{r22.returncode} {r22.stderr[:160]}')
check('and it does not blame the tool', 'bug in migrate.py' not in r22.stderr, r22.stderr)
check('and it quotes the value it could not read',
      "'lots'" in r22.stderr and 'page count' in r22.stderr, r22.stderr)
check('and prints no traceback', 'Traceback' not in r22.stderr, r22.stderr)

check('an all-unknown inventory records the scope block, so the plan can report it',
      isinstance((plan.get('summary') or {}).get('scope'), dict),
      str(plan.get('summary')))

# --- Task 12: --scope active, driven end to end through a shim that LOGS its calls ---
#
# The saving is entirely in WHERE the filter runs. `is_active` rides on `list`, so
# filtering the list result turns a 150-placement app with 30 active from 2 + 150
# calls into 2 + 30. Filtering after the GET loop would produce an identical
# inventory file and buy nothing -- so the load-bearing assertion is not the
# contents of the file but the number of GETs the CLI was asked for, which is why
# the shim keeps a call log.

scope_shim = TMP / 'fake-adapty-scope.py'
getlog = TMP / 'get-calls.log'
scope_shim.write_text('''#!/usr/bin/env python3
"""5 placements: 3 active, 1 inactive, 1 with NO is_active field at all.

pl-e is the load-bearing one: ACTIVE but already on a flow, so it is NOT
migratable. Without it every placement is migratable and scope/exposure
cannot diverge, which made the divergence check unfailable."""
import json, os, sys
a = sys.argv[1:]
LOG = os.environ["GETLOG"]
PL = [
    {"id": "pl-a", "developer_id": "main", "title": "Main", "is_active": True},
    {"id": "pl-b", "developer_id": "onboarding", "title": "Onb", "is_active": True},
    {"id": "pl-c", "developer_id": "retired", "title": "Old", "is_active": False},
    {"id": "pl-d", "developer_id": "mystery", "title": "Huh"},
    {"id": "pl-e", "developer_id": "already", "title": "Done", "is_active": True},
]
DETAIL = {
    "pl-a": [{"segment_ids": [], "paywall_id": "pw-1", "priority": 0}],
    "pl-b": [{"segment_ids": ["s1"], "paywall_id": "pw-2", "priority": 0}],
    "pl-c": [{"segment_ids": [], "paywall_id": "pw-3", "priority": 0}],
    "pl-d": [{"segment_ids": [], "paywall_id": "pw-4", "priority": 0}],
    "pl-e": [{"content_type": "flow", "flow_id": "f-9", "priority": 0}],
}
if a[:2] == ["placements", "list"]:
    print(json.dumps({"data": PL,
                      "meta": {"pagination": {"count": len(PL), "page": 1, "pages": 1}}}))
    sys.exit(0)
if a[:2] == ["placements", "get"]:
    pid = a[a.index("--app") + 2]
    with open(LOG, "a") as fh:
        fh.write(pid + "\\n")
    row = next(p for p in PL if p["id"] == pid)
    print(json.dumps(dict(row, audiences=DETAIL[pid])))
    sys.exit(0)
print("unexpected: " + " ".join(a), file=sys.stderr)
sys.exit(9)
''')
SCOPE_ADAPTY = f'{sys.executable} {scope_shim}'
env = dict(os.environ, GETLOG=str(getlog))


def run_scope(scope, out_name):
    """inventory through the logging shim. Returns (proc, payload, gets asked for)."""
    if getlog.exists():
        getlog.unlink()
    out = TMP / out_name
    proc = subprocess.run([sys.executable, str(MIGRATE), 'inventory', '--app', 'app-1',
                           '--adapty', SCOPE_ADAPTY, '--scope', scope, '--out', str(out)],
                          capture_output=True, text=True, env=env)
    body = json.loads(out.read_text()) if out.exists() else {}
    gets = getlog.read_text().split() if getlog.exists() else []
    return proc, body, gets, out


pa, all_body, all_gets, all_out = run_scope('all', 'inv-all.json')
check('inventory --scope all exits 0', pa.returncode == 0, pa.stderr.strip()[:300])
check('scope=all spends one get per placement -- all five',
      sorted(all_gets) == ['pl-a', 'pl-b', 'pl-c', 'pl-d', 'pl-e'], str(all_gets))
check('scope=all keeps every placement in the inventory',
      len(all_body.get('placements', [])) == 5, str(len(all_body.get('placements', []))))
check('scope=all still records the three-way partition',
      (all_body.get('scope') or {}).get('active') == 3
      and (all_body.get('scope') or {}).get('inactive') == 1
      and (all_body.get('scope') or {}).get('unknown') == 1, str(all_body.get('scope')))
check('scope=all reports nothing filtered out',
      (all_body.get('scope') or {}).get('filtered_out') == 0, str(all_body.get('scope')))

pb, act_body, act_gets, act_out = run_scope('active', 'inv-active.json')
check('inventory --scope active exits 0', pb.returncode == 0, pb.stderr.strip()[:300])
check('SCOPE=ACTIVE SPENDS NO GET ON THE FILTERED ROWS -- the filter runs on the '
      '`list` result, BEFORE the get loop, which is the whole saving',
      sorted(act_gets) == ['pl-a', 'pl-b', 'pl-e'], str(act_gets))
check('scope=active excludes the inactive placement from the inventory',
      'pl-c' not in {p['id'] for p in act_body.get('placements', [])},
      str([p['id'] for p in act_body.get('placements', [])]))
check('scope=active excludes the placement with NO is_active field -- unknown is '
      'not known-active', 'pl-d' not in {p['id'] for p in act_body.get('placements', [])},
      str([p['id'] for p in act_body.get('placements', [])]))
check('scope=active records what it withheld, broken down',
      (act_body.get('scope') or {}).get('filtered_out') == 2
      and (act_body.get('scope') or {}).get('inactive') == 1
      and (act_body.get('scope') or {}).get('unknown') == 1, str(act_body.get('scope')))
check('scope=active did not fall back -- the field is present on this account',
      (act_body.get('scope') or {}).get('fallback') is False, str(act_body.get('scope')))
check('inventory PRINTS the filtered-out count on stdout, every run -- never a '
      'silent exclusion', '2 filtered out' in pb.stdout, pb.stdout)
check('the printed line names all three counts',
      '3 active' in pb.stdout and '1 inactive' in pb.stdout and '1 unknown' in pb.stdout,
      pb.stdout)

r12 = subprocess.run([sys.executable, str(MIGRATE), 'plan', '--inventory', str(act_out)],
                     capture_output=True, text=True)
check('plan over a scoped inventory exits 0', r12.returncode == 0, r12.stderr.strip()[:300])
scoped_plan = json.loads(r12.stdout) if r12.returncode == 0 else {}
check('PLAN SURFACES THE FILTERED-OUT COUNT IN ITS SUMMARY -- the plan is what '
      'later phases read, so a count that stops at the inventory file is unseen',
      (scoped_plan.get('summary') or {}).get('scope', {}).get('filtered_out') == 2,
      str(scoped_plan.get('summary')))
check('plan also prints the scope line on STDERR, so a run that redirects the '
      'JSON still sees what was withheld', '2 filtered out' in r12.stderr, r12.stderr)

# EXPOSURE at the CLI level. Phase 6 quotes this and NOT scope, because scope counts
# the account while exposure counts the placements the plan would create.
r19 = subprocess.run([sys.executable, str(MIGRATE), 'plan', '--inventory', str(all_out)],
                     capture_output=True, text=True)
wide = json.loads(r19.stdout)['summary'] if r19.returncode == 0 else {}
check('plan over a --scope all inventory exits 0', r19.returncode == 0, r19.stderr[:200])
check('EXPOSURE AND SCOPE DIVERGE ON A REAL INVENTORY, compared field to field: '
      'the account holds 3 active placements but only 2 of them are migratable, so '
      'scope.active is 3 while exposure.active is 2 -- quoting scope in phase 6 '
      'would overstate the live exposure by exactly that difference',
      (wide.get('scope') or {}).get('active') == 3
      and (wide.get('exposure') or {}).get('active') == 2,
      str(wide))
check('and the divergence is not a rounding artifact: the account has 5 placements '
      'and the plan emits 4 rows, because the active already-flow one is excluded',
      (wide.get('scope') or {}).get('kept') == 5
      and (wide.get('exposure') or {}).get('placements') == 4, str(wide))
check('exposure splits the plan rows three ways, same rules as the filter',
      [(wide.get('exposure') or {}).get(k) for k in ('active', 'inactive', 'unknown')]
      == [2, 1, 1], str(wide.get('exposure')))
check('exposure.status_readable is True when the field is present',
      (wide.get('exposure') or {}).get('status_readable') is True, str(wide.get('exposure')))
check('the withheld-unknown ESCALATION reaches the payload, not just the prose',
      (act_body.get('scope') or {}).get('unknown_withheld') is True,
      str(act_body.get('scope')))
check('and the printed line carries it too',
      'not as inactive' in pb.stdout, pb.stdout)
check('scope=all raises no unknown escalation -- it withheld nothing',
      (all_body.get('scope') or {}).get('unknown_withheld') is False,
      str(all_body.get('scope')))
check('the scope block uses status_readable, and the old field_present name is gone',
      'status_readable' in (all_body.get('scope') or {})
      and 'field_present' not in (all_body.get('scope') or {}),
      str(sorted(all_body.get('scope') or {})))

# --- the fallback: an account where NO placement carries is_active ---
#
# Measured 2026-09-03: that is EVERY account, in prod and on the pod alike. So this
# is the shape the filter meets today, and returning an empty set here would report
# an empty migration -- a silent, total failure that reads as a clean result.

pc, fb_body, fb_gets, fb_out = None, None, None, None
if getlog.exists():
    getlog.unlink()
fb_out = TMP / 'inv-fallback.json'
pc = subprocess.run([sys.executable, str(MIGRATE), 'inventory', '--app', 'app-1',
                     '--adapty', ADAPTY, '--scope', 'active', '--out', str(fb_out)],
                    capture_output=True, text=True)
fb_body = json.loads(fb_out.read_text()) if fb_out.exists() else {}
check('an all-absent account under --scope active exits 0', pc.returncode == 0,
      pc.stderr.strip()[:300])
check('AN ALL-ABSENT ACCOUNT UNDER --scope active KEEPS EVERY PLACEMENT, never an '
      'empty migration', len(fb_body.get('placements', [])) == 3,
      str(len(fb_body.get('placements', []))))
check('the fallback is recorded in the inventory',
      (fb_body.get('scope') or {}).get('fallback') is True, str(fb_body.get('scope')))
check('the fallback records `all` as applied though `active` was requested',
      (fb_body.get('scope') or {}).get('requested') == 'active'
      and (fb_body.get('scope') or {}).get('applied') == 'all', str(fb_body.get('scope')))
check('all three placements read as unknown, and none as inactive',
      (fb_body.get('scope') or {}).get('unknown') == 3
      and (fb_body.get('scope') or {}).get('inactive') == 0, str(fb_body.get('scope')))
check('the fallback is announced on stdout', 'fell back to all' in pc.stdout, pc.stdout)
check('the fallback raises no unknown escalation -- it withheld nothing, and the '
      'fallback line already says what happened',
      (fb_body.get('scope') or {}).get('unknown_withheld') is False,
      str(fb_body.get('scope')))

r20 = subprocess.run([sys.executable, str(MIGRATE), 'plan', '--inventory', str(fb_out)],
                     capture_output=True, text=True)
fb_summary = json.loads(r20.stdout)['summary'] if r20.returncode == 0 else {}
check('plan over the fallback inventory exits 0', r20.returncode == 0, r20.stderr[:200])
check('exposure.status_readable is FALSE on an all-absent account, which is what '
      'routes phase 6 to the verbatim acknowledgment rather than a fabricated count',
      (fb_summary.get('exposure') or {}).get('status_readable') is False,
      str(fb_summary.get('exposure')))
check('and every plan row reads as unknown, none as inactive',
      (fb_summary.get('exposure') or {}).get('unknown')
      == (fb_summary.get('exposure') or {}).get('placements')
      and (fb_summary.get('exposure') or {}).get('inactive') == 0,
      str(fb_summary.get('exposure')))

r13 = subprocess.run([sys.executable, str(MIGRATE), 'inventory', '--app', 'app-1',
                      '--adapty', ADAPTY, '--scope', 'live', '--out', str(TMP / 'x.json')],
                     capture_output=True, text=True)
check('an unknown --scope value is refused by argparse rather than guessed',
      r13.returncode == 2 and 'live' in r13.stderr, f'{r13.returncode} {r13.stderr[:200]}')

r14 = subprocess.run([sys.executable, str(MIGRATE), 'inventory', '--app', 'app-1',
                      '--adapty', ADAPTY, '--out', str(TMP / 'inv-default.json')],
                     capture_output=True, text=True)
check('--scope DEFAULTS to all, so an unscoped call can never hide work',
      r14.returncode == 0 and 'scope=all' in r14.stdout, r14.stdout)

# --- plan --flows: phase 7's argv comes out of build_create_command, never retyped ---
#
# The whole point of the flag is that the guards ride along: content_type on every
# entry (the CLI exits 2 without it), segment_ids/priority verbatim (they are the
# targeting), and a raise rather than a broken argv when the ledger is incomplete.

ledger = TMP / 'flows.json'
ledger.write_text(json.dumps({'pw-1': 'flow-one', 'pw-2': 'flow-two'}))
r8 = subprocess.run([sys.executable, str(MIGRATE), 'plan', '--inventory', str(inv),
                     '--flows', str(ledger)], capture_output=True, text=True)
check('plan --flows exits 0', r8.returncode == 0, r8.stderr.strip()[:300])
fplan = json.loads(r8.stdout) if r8.returncode == 0 else {}
frows = fplan.get('placements', [])
check('plan --flows emits a command for every migratable placement',
      len(frows) == 2 and all(isinstance(p.get('command'), list) for p in frows),
      str(frows))
check('the emitted command is a placements create, never an update',
      all(p.get('command', [])[:2] == ['placements', 'create'] for p in frows), str(frows))
check('the emitted command carries the app id and the approved developer id',
      bool(frows) and all(flag(p.get('command'), '--app') == 'app-1'
                          and flag(p.get('command'), '--developer-id')
                          == p['proposed_developer_id'] for p in frows), str(frows))

audience_arrays = {p['proposed_developer_id']:
                   json.loads(flag(p.get('command'), '--audiences') or '[]')
                   for p in frows}
check('every emitted audience entry carries content_type: flow -- the CLI exits 2 without it',
      any(audience_arrays.values())
      and all(e.get('content_type') == 'flow' for arr in audience_arrays.values() for e in arr),
      str(audience_arrays))
check('every emitted audience entry names a flow_id from the ledger, never a paywall_id',
      any(audience_arrays.values())
      and all(e.get('flow_id') in ('flow-one', 'flow-two') and 'paywall_id' not in e
              for arr in audience_arrays.values() for e in arr), str(audience_arrays))
check('the emitted argv preserves segment_ids and priority verbatim',
      any(e['segment_ids'] == ['s2'] and e['priority'] == 1
          for e in audience_arrays.get('onboarding-flow') or []), str(audience_arrays))
check('a placement using two paywalls emits one audience entry per source audience',
      len(audience_arrays.get('onboarding-flow') or []) == 2, str(audience_arrays))

partial = TMP / 'flows-partial.json'
partial.write_text(json.dumps({'pw-1': 'flow-one'}))
r9 = subprocess.run([sys.executable, str(MIGRATE), 'plan', '--inventory', str(inv),
                     '--flows', str(partial)], capture_output=True, text=True)
check('plan --flows with an incomplete ledger still exits 0', r9.returncode == 0,
      r9.stderr.strip()[:300])
prows = ({p['proposed_developer_id']: p for p in json.loads(r9.stdout)['placements']}
         if r9.returncode == 0 else {})
check('a row whose paywall is missing from the ledger gets NO command',
      'onboarding-flow' in prows and 'command' not in prows['onboarding-flow'],
      str(prows.get('onboarding-flow')))
check('a row whose paywall is missing from the ledger says which paywall',
      (prows.get('onboarding-flow') or {}).get('missing_flows') == ['pw-2']
      and 'pw-2' in (prows.get('onboarding-flow') or {}).get('command_unavailable', ''),
      str(prows.get('onboarding-flow')))
check('a row the ledger DOES cover still gets its command',
      isinstance((prows.get('main-flow') or {}).get('command'), list),
      str(prows.get('main-flow')))

bad_ledger = TMP / 'flows-bad.json'
bad_ledger.write_text(json.dumps(['pw-1', 'flow-one']))
r10 = subprocess.run([sys.executable, str(MIGRATE), 'plan', '--inventory', str(inv),
                      '--flows', str(bad_ledger)], capture_output=True, text=True)
check('a ledger that is not an object exits 2', r10.returncode == 2, str(r10.returncode))
check('a ledger that is not an object prints no traceback',
      'Traceback' not in r10.stderr, r10.stderr)

# --- A MALFORMED ROW IS AN INPUT ERROR (exit 2), NOT A TOOL BUG (exit 3) ---
#
# Reproduced by the reviewer: a row with no `developer_id` printed a raw
# `KeyError: 'developer_id'`. The first fix caught it in the catch-all, which made it
# exit 3 and report "a bug in migrate.py, your inventory may be fine" -- MISDIRECTING
# the only person who could fix it, and worse than the traceback it replaced. An
# exit-code split is only worth having if the boundary is real, so every shape `plan`
# subscripts is now validated in `_read_inventory` and reported at 2 with the row
# index named. What is asserted here is the BOUNDARY, in both directions.

no_dev = TMP / 'no-developer-id.json'
no_dev.write_text(json.dumps({'app': 'app-1', 'placements': [
    {'id': 'pl-x', 'title': 'X', 'audiences': [{'paywall_id': 'pw-1', 'priority': 0}]}]}))
r11 = subprocess.run([sys.executable, str(MIGRATE), 'plan', '--inventory', str(no_dev)],
                     capture_output=True, text=True)
check('A ROW MISSING developer_id IS AN INPUT ERROR: exit 2, with its own message',
      r11.returncode == 2 and "has no usable 'developer_id'" in r11.stderr,
      f'{r11.returncode} {r11.stderr[:160]}')
check('and it is the row guard talking, not the catch-all',
      'not classified' not in r11.stderr, r11.stderr)
check('it does NOT claim to be a bug in the tool -- that misdirects the one person '
      'who can fix it', 'bug in migrate.py' not in r11.stderr, r11.stderr)
check('it names the missing field', "'developer_id'" in r11.stderr, r11.stderr)
check('it names WHICH row, by index', 'placements[0]' in r11.stderr, r11.stderr)
check('it prints no traceback at all', 'Traceback' not in r11.stderr, r11.stderr)
check('it writes nothing to stdout', r11.stdout.strip() == '', r11.stdout)

not_a_dict = TMP / 'row-not-a-dict.json'
not_a_dict.write_text(json.dumps({'app': 'app-1', 'placements': ['not-a-dict']}))
r15 = subprocess.run([sys.executable, str(MIGRATE), 'plan', '--inventory', str(not_a_dict)],
                     capture_output=True, text=True)
check('a placements entry that is not an object exits 2, with its own message',
      r15.returncode == 2 and 'not a placement object' in r15.stderr,
      f'{r15.returncode} {r15.stderr[:160]}')
check('and says what it got instead, naming the row',
      'str' in r15.stderr and 'placements[0]' in r15.stderr, r15.stderr)
check('and does not blame the tool', 'bug in migrate.py' not in r15.stderr, r15.stderr)

no_id = TMP / 'no-id.json'
no_id.write_text(json.dumps({'app': 'app-1', 'placements': [{'developer_id': 'main'}]}))
r16 = subprocess.run([sys.executable, str(MIGRATE), 'plan', '--inventory', str(no_id)],
                     capture_output=True, text=True)
check('a row missing `id` exits 2 with the CAUSE-SPECIFIC message -- asserting '
      'only the code would pass on the catch-all too, now that unclassified '
      'failures are also 2, so the code alone no longer proves the guard ran',
      r16.returncode == 2 and "has no usable 'id'" in r16.stderr,
      f'{r16.returncode} {r16.stderr[:160]}')
check('and the row-missing-id path is NOT the unclassified one',
      'not classified' not in r16.stderr, r16.stderr)
empty_dev = TMP / 'empty-dev.json'
empty_dev.write_text(json.dumps({'app': 'app-1',
                                 'placements': [{'id': 'p', 'developer_id': ''}]}))
r16b = subprocess.run([sys.executable, str(MIGRATE), 'plan', '--inventory', str(empty_dev)],
                      capture_output=True, text=True)
check('an EMPTY developer_id is refused like a missing one -- propose_developer_id '
      'would otherwise raise, and a bare suffix is not a usable placement id',
      r16b.returncode == 2 and "has no usable 'developer_id'" in r16b.stderr,
      f'{r16b.returncode} {r16b.stderr[:160]}')

bad_auds = TMP / 'bad-audiences.json'
bad_auds.write_text(json.dumps({'app': 'app-1', 'placements': [
    {'id': 'p', 'developer_id': 'main', 'audiences': {'paywall_id': 'pw-1'}}]}))
r17 = subprocess.run([sys.executable, str(MIGRATE), 'plan', '--inventory', str(bad_auds)],
                     capture_output=True, text=True)
check('an `audiences` that is an object rather than a list exits 2', r17.returncode == 2,
      str(r17.returncode))
check('and it is the guard talking, not the catch-all',
      'not classified' not in r17.stderr, r17.stderr)
check('and does not blame the tool', 'bug in migrate.py' not in r17.stderr, r17.stderr)
check('and it is the LIST-SHAPE guard that says so, naming "not a list" -- the exit '
      'code alone cannot tell, because `enumerate` on a dict walks its KEYS, so '
      'without this guard the entry check reports a phantom audiences[0] "is a str"',
      'not a list' in r17.stderr, r17.stderr)

# --- THE AUDIENCE-ENTRY LEAK (round 2). The exit-code boundary leaked a second
# time, one level down from the row: `normalize_audience` RETURNS EARLY when
# `content_type` is already declared, so it never checks that the matching id is
# actually there -- and `entry['paywall_id']` is subscripted in `group_by_paywall`.
# Every case below used to be exit 3 with "a bug in migrate.py … your inventory may
# be fine", on a file the user could have fixed in a second.

def audience_case(name, entries):
    """plan over an inventory whose one placement carries `entries`."""
    path = TMP / f'aud-{name}.json'
    path.write_text(json.dumps({'app': 'app-1', 'placements': [
        {'id': 'pl-x', 'developer_id': 'main', 'title': 'X', 'audiences': entries}]}))
    return subprocess.run([sys.executable, str(MIGRATE), 'plan', '--inventory', str(path)],
                          capture_output=True, text=True)


AUD = {
    'declared-paywall-no-id': [{'content_type': 'paywall', 'priority': 0}],
    'declared-flow-no-id': [{'content_type': 'flow', 'priority': 0}],
    'no-derivable-type': [{'priority': 0}],
    'entry-is-a-string': ['nope'],
    'unknown-content-type': [{'content_type': 'onboarding'}],
    'empty-paywall-id': [{'paywall_id': ''}],
    'non-string-paywall-id': [{'content_type': 'paywall', 'paywall_id': 42}],
    'second-entry-bad': [{'paywall_id': 'pw-1'}, {'content_type': 'paywall'}],
}
aud_runs = {name: audience_case(name, entries) for name, entries in AUD.items()}

check('EVERY MALFORMED AUDIENCE ENTRY IS AN INPUT ERROR: exit 2, not the tool-bug 3',
      {name: r.returncode for name, r in aud_runs.items()}
      == {name: 2 for name in AUD},
      str({name: r.returncode for name, r in aud_runs.items()}))
check('and NOT ONE of them claims to be a bug in migrate.py -- this is the exact '
      'false claim the exit-code split existed to prevent',
      not any('bug in migrate.py' in r.stderr for r in aud_runs.values()),
      str([n for n, r in aud_runs.items() if 'bug in migrate.py' in r.stderr]))
check('none of them prints a traceback',
      not any('Traceback' in r.stderr for r in aud_runs.values()),
      str([n for n, r in aud_runs.items() if 'Traceback' in r.stderr]))
check('each names the placement and the entry index',
      all("placements[0] ('main') audiences[" in r.stderr for r in aud_runs.values()),
      str({n: r.stderr.strip()[:70] for n, r in aud_runs.items()}))
check('a declared paywall type with no paywall_id says which field is missing -- '
      'the case that was reported',
      "'paywall_id'" in aud_runs['declared-paywall-no-id'].stderr,
      aud_runs['declared-paywall-no-id'].stderr)
check('and says why the shape is wrong: a declared type and a present id are two '
      'separate facts',
      'two separate facts' in aud_runs['declared-paywall-no-id'].stderr,
      aud_runs['declared-paywall-no-id'].stderr)
check('a declared FLOW type with no flow_id is refused too -- nothing here '
      'subscripts it, but every write needs it',
      "'flow_id'" in aud_runs['declared-flow-no-id'].stderr,
      aud_runs['declared-flow-no-id'].stderr)
check('a non-object entry names the type it got',
      'is a str' in aud_runs['entry-is-a-string'].stderr,
      aud_runs['entry-is-a-string'].stderr)
check('the SECOND entry being bad is caught too, and reported at index 1 -- the '
      'walk does not stop at the first entry',
      'audiences[1]' in aud_runs['second-entry-bad'].stderr,
      aud_runs['second-entry-bad'].stderr)
check('a VALID audience array is untouched by the new validation -- the guard does '
      'not fire on the shape it exists to protect',
      audience_case('valid', [{'paywall_id': 'pw-1', 'segment_ids': [], 'priority': 0}]
                    ).returncode == 0)
check('a valid POD-shaped entry (content_type already present) still passes -- the '
      'id check must not break the post-merge read',
      audience_case('valid-pod', [{'content_type': 'paywall', 'paywall_id': 'pw-1',
                                   'segment_ids': [], 'priority': 0}]).returncode == 0)
check('a valid already-flow entry still passes',
      audience_case('valid-flow', [{'content_type': 'flow', 'flow_id': 'f-1',
                                    'priority': 0}]).returncode == 0)
check('an EMPTY audience array is legal -- a placement with no audiences is a real '
      'and reportable state, not a malformed one',
      audience_case('valid-empty', []).returncode == 0)

SHAPE_SHIM_SRC = '#!/usr/bin/env python3\n"""Prints whatever raw `placements list` body BODY holds -- malformed on purpose.\n\nTaking the body verbatim from the environment keeps the malformed shapes in the\ntest beside their assertions, instead of in a lookup table inside a nested\nstring where the quoting is its own hazard.\n"""\nimport json, os, sys\na = sys.argv[1:]\nif a[:2] == ["placements", "list"]:\n    print(os.environ["BODY"])\n    sys.exit(0)\nif a[:2] == ["placements", "get"]:\n    print(json.dumps({"id": "p", "developer_id": "d", "audiences": []}))\n    sys.exit(0)\nsys.exit(9)\n'

# --- THE NINE SHAPES THAT STILL LEAKED AFTER ROUND 2, plus the silent one ---
#
# All ten were measured at exit 3 with "a bug in migrate.py ... your inventory may
# be fine". The inversion alone would land them on 2; each also gets a
# cause-specific message, because a generic message on a shape we CAN name is a
# worse report than necessary. The MESSAGES are asserted, not just the codes -- the
# masking bug found in round 2 proved a code can be right for the wrong reason.

def seg_case(name, value_json):
    """An inventory whose one audience carries `segment_ids: <value_json>`."""
    path = TMP / ('seg-%s.json' % name)
    path.write_text('{"app":"app-1","placements":[{"id":"p","developer_id":"m",'
                    '"audiences":[{"paywall_id":"pw1","segment_ids":'
                    + value_json + '}]}]}')
    return path


def plan_over(path, *extra):
    return subprocess.run([sys.executable, str(MIGRATE), 'plan',
                           '--inventory', str(path), *extra],
                          capture_output=True, text=True)


SEG = {'int': '5', 'string': '"ab"', 'dict': '{}', 'bad-element': '[5]',
       'null-element': '[null]'}
seg_runs = {name: plan_over(seg_case(name, raw)) for name, raw in SEG.items()}

check('a non-list segment_ids exits 2 in every malformed form',
      {n: r.returncode for n, r in seg_runs.items()} == {n: 2 for n in SEG},
      str({n: r.returncode for n, r in seg_runs.items()}))
check('and none of them claims a tool bug',
      not any('bug in migrate.py' in r.stderr for r in seg_runs.values()),
      str([n for n, r in seg_runs.items() if 'bug in migrate.py' in r.stderr]))
check('A STRING segment_ids IS REJECTED, and it is the worst of these cases '
      'because it does NOT crash: a string is iterable, so it spreads one segment '
      'per character and ships as CORRUPTED TARGETING on a placement that cannot '
      'be deleted',
      seg_runs['string'].returncode == 2
      and 'must be a list' in seg_runs['string'].stderr,
      seg_runs['string'].stderr)
check('and the message explains the per-character spread, so a reader learns why '
      'a plausible-looking value was refused',
      'per CHARACTER' in seg_runs['string'].stderr, seg_runs['string'].stderr)
check('an int segment_ids names the type it got',
      'has a int segment_ids' in seg_runs['int'].stderr, seg_runs['int'].stderr)
check('a bad ELEMENT inside a list is refused too -- the array is the targeting '
      'and is carried over verbatim, so a non-id in it gets written as one',
      'not a segment id' in seg_runs['bad-element'].stderr,
      seg_runs['bad-element'].stderr)
check('a VALID segment_ids list is untouched by the new guard',
      plan_over(seg_case('valid', '["s1","s2"]')).returncode == 0)
check('an EMPTY segment_ids list is legal -- it is the commonest real value',
      plan_over(seg_case('empty', '[]')).returncode == 0)

absent = TMP / 'seg-absent.json'
absent.write_text(json.dumps({'app': 'app-1', 'placements': [
    {'id': 'p', 'developer_id': 'm',
     'audiences': [{'paywall_id': 'pw1', 'priority': 0}]}]}))
check('an ABSENT segment_ids is legal -- a read may omit it, and rejecting that '
      'would refuse valid inventories', plan_over(absent).returncode == 0)

seg_flows = plan_over(seg_case('string2', '"ab"'), '--flows', str(ledger))
check('the string segment_ids is refused WITH --flows too, which is the path that '
      'builds the irreversible argv', seg_flows.returncode == 2
      and 'must be a list' in seg_flows.stderr,
      '%s %s' % (seg_flows.returncode, seg_flows.stderr[:150]))
check('and no command reached stdout for it', seg_flows.stdout.strip() == '',
      seg_flows.stdout[:200])

# --- six malformed `placements list` response shapes: API faults, so exit 2 ---

shape_shim = TMP / 'fake-adapty-shapes.py'
shape_shim.write_text(SHAPE_SHIM_SRC)

SHAPES = {
    'top-list': '[{"id":"p"}]',
    'top-string': '"hello"',
    'top-null': 'null',
    'meta-not-object': '{"data":[{"id":"p","developer_id":"d"}],"meta":[1]}',
    'pagination-not-object':
        '{"data":[{"id":"p","developer_id":"d"}],"meta":{"pagination":[1]}}',
    'rows-not-objects': '{"data":["abc"],"meta":{"pagination":{"pages":1}}}',
    'data-not-list': '{"data":{"id":"p"},"meta":{"pagination":{"pages":1}}}',
}
shape_runs = {
    name: subprocess.run(
        [sys.executable, str(MIGRATE), 'inventory', '--app', 'app-1',
         '--adapty', '%s %s' % (sys.executable, shape_shim),
         '--out', str(TMP / ('shape-%s.json' % name))],
        capture_output=True, text=True, env=dict(os.environ, BODY=body))
    for name, body in SHAPES.items()
}

check('EVERY MALFORMED `placements list` SHAPE EXITS 2 -- an API fault is the '
      'environment, not this tool, and no enumeration of such shapes was ever '
      'going to be complete, which is why the catch-all now agrees with these '
      'guards instead of contradicting them',
      {s: r.returncode for s, r in shape_runs.items()}
      == {s: 2 for s in SHAPES},
      str({s: r.returncode for s, r in shape_runs.items()}))
check('and not one claims a bug in migrate.py',
      not any('bug in migrate.py' in r.stderr for r in shape_runs.values()),
      str([s for s, r in shape_runs.items() if 'bug in migrate.py' in r.stderr]))
check('and not one tells the user their input may be fine',
      not any('may be fine' in r.stderr for r in shape_runs.values()),
      str([s for s, r in shape_runs.items() if 'may be fine' in r.stderr]))
check('a non-object top-level body says so, rather than dying on .get two frames '
      'from the cause',
      all('where an object was expected' in shape_runs[s].stderr
          for s in ('top-list', 'top-string', 'top-null')),
      str({s: shape_runs[s].stderr.strip()[:70]
           for s in ('top-list', 'top-string', 'top-null')}))
check('a "meta" of the wrong TYPE is named -- the `or {}` idiom this replaced '
      'guarded falsiness, so a non-empty list passed straight through it',
      '"meta" is list' in shape_runs['meta-not-object'].stderr,
      shape_runs['meta-not-object'].stderr)
check('a "pagination" of the wrong type is named',
      '"pagination" is list' in shape_runs['pagination-not-object'].stderr,
      shape_runs['pagination-not-object'].stderr)
check('a "data" of the wrong type is named',
      '"data" is dict' in shape_runs['data-not-list'].stderr,
      shape_runs['data-not-list'].stderr)
check('a non-object ROW inside data is named with its index',
      'data[0] is a str' in shape_runs['rows-not-objects'].stderr,
      shape_runs['rows-not-objects'].stderr)
check('none of the shape failures prints a traceback',
      not any('Traceback' in r.stderr for r in shape_runs.values()),
      str([s for s, r in shape_runs.items() if 'Traceback' in r.stderr]))

# --- the caller flag: a fifth kind of outside data, absent from the old
# enumeration entirely, and the natural mistake since api-surface.md documents
# the cap it violates.

flag_runs = {
    value: subprocess.run(
        [sys.executable, str(MIGRATE), 'inventory', '--app', 'app-1',
         '--adapty', ADAPTY, '--page-size', value, '--out', str(TMP / 'ps.json')],
        capture_output=True, text=True)
    for value in ('0', '101', '-5')
}
check('a --page-size outside 1..100 exits 2 and names THE FLAG rather than an '
      'internal parameter -- the agent typed a flag, so the message uses its name',
      all(r.returncode == 2
          and '--page-size must be between 1 and 100' in r.stderr
          for r in flag_runs.values()),
      str({v: (r.returncode, r.stderr.strip()[:60])
           for v, r in flag_runs.items()}))
check('and it explains the cap rather than only asserting it',
      'API caps a page' in flag_runs['101'].stderr, flag_runs['101'].stderr)
check('and it does not claim a tool bug',
      not any('bug in migrate.py' in r.stderr for r in flag_runs.values()))
check('the boundary values 1 and 100 are ACCEPTED -- the guard is the API range, '
      'not a superstition about round numbers',
      all(subprocess.run([sys.executable, str(MIGRATE), 'inventory',
                          '--app', 'app-1', '--adapty', ADAPTY,
                          '--page-size', v, '--out', str(TMP / 'ps-ok.json')],
                         capture_output=True, text=True).returncode == 0
          for v in ('1', '100')))

# --- THE INVERSION: the catch-all is exit 2, and exit 3 is OPT-IN ---
#
# Exit 3 as the catch-all was a CLAIM -- "a bug in migrate.py, your inventory may be
# fine" -- asserted about every failure nobody had classified. Three attempts to
# enumerate those failures each left holes, so the tool kept telling users their file
# was fine when their file was the problem. Inverted, an unguarded site is vague but
# TRUE, and the confident claim exists only where someone wrote `raise InternalError`.
#
# What is asserted here is the inversion in BOTH directions: an unclassified failure
# lands on 2 and never claims a tool bug, AND the deliberate path still reaches 3.

unclassified = TMP / 'unclassified.py'
unclassified.write_text(f'''
import sys
sys.dont_write_bytecode = True
sys.path.insert(0, {str(MIGRATE.parent)!r})
import migrate
def boom(*a, **k):
    raise RuntimeError('simulated unclassified failure')
migrate.build_plan = boom          # not an InternalError -- unclassified
sys.exit(migrate.main(['plan', '--inventory', sys.argv[1]]))
''')
r23 = subprocess.run([sys.executable, str(unclassified), str(inv)],
                     capture_output=True, text=True)
check('AN UNCLASSIFIED FAILURE EXITS 2, not 3 -- unknown is reported as "did not '
      'work", never as "your input is fine"', r23.returncode == 2,
      f'{r23.returncode} {r23.stderr[:200]}')
check('and it does NOT claim to be a bug in migrate.py',
      'bug in migrate.py' not in r23.stderr, r23.stderr)
check('and it does NOT tell the user their input may be fine -- that is the '
      'sentence that made the old design wrong',
      'may be fine' not in r23.stderr, r23.stderr)
check('and it does NOT tell them to avoid editing their files',
      'editing your files' not in r23.stderr, r23.stderr)
check('it says plainly that the cause is UNKNOWN, which is the honest claim',
      'not classified' in r23.stderr and 'unknown' in r23.stderr, r23.stderr)
check('it still names the exception so the failure is actionable',
      'RuntimeError' in r23.stderr, r23.stderr)
check('it still prints the traceback tail', '  | ' in r23.stderr, r23.stderr)
check('and no UNHANDLED traceback reaches the user',
      'Traceback (most recent call last)' not in r23.stderr, r23.stderr)

internal = TMP / 'internal.py'
internal.write_text(f'''
import sys
sys.dont_write_bytecode = True
sys.path.insert(0, {str(MIGRATE.parent)!r})
import migrate
# Break an invariant migrate.py COMPUTES ITSELF: the exposure partition must
# cover exactly the plan rows. Both sides are local, so no input can cause this.
_real = migrate.partition_by_activity
def lossy(rows):
    out = _real(rows)
    for key in out:                # drop every row -> the sum cannot match
        out[key] = []
    return out
migrate.partition_by_activity = lossy
sys.exit(migrate.main(['plan', '--inventory', sys.argv[1]]))
''')
r18 = subprocess.run([sys.executable, str(internal), str(inv)],
                     capture_output=True, text=True)
check('A DELIBERATE INTERNAL-INVARIANT VIOLATION STILL REACHES 3 -- the opt-in path '
      'is live, not merely unreachable', r18.returncode == 3,
      f'{r18.returncode} {r18.stderr[:250]}')
check('the exit-3 message names the violated invariant',
      'invariant violated' in r18.stderr, r18.stderr)
check('exit 3 is the ONE place the strong claim about the input is earned',
      'bug in migrate.py' in r18.stderr
      and 'input is almost certainly fine' in r18.stderr, r18.stderr)
check('and it is the only place "do not start editing your files" may appear',
      'editing your files' in r18.stderr, r18.stderr)
check('exit 3 keeps the traceback tail', '  | ' in r18.stderr, r18.stderr)
check('exit 3 writes nothing to stdout', r18.stdout.strip() == '', r18.stdout)
internal2 = TMP / 'internal2.py'
internal2.write_text(f'''
import sys
sys.dont_write_bytecode = True
sys.path.insert(0, {str(MIGRATE.parent)!r})
import migrate
# Break the OTHER computed invariant: select_scope's kept + filtered_out must
# account for every row it was given. Both sides are local to that function.
_real = migrate.partition_by_activity
def lossy(rows):
    out = _real(rows)
    out[migrate.UNKNOWN] = []
    return out
migrate.partition_by_activity = lossy
sys.exit(migrate.main(['inventory', '--app', 'app-1', '--adapty', sys.argv[1],
                       '--scope', 'active', '--out', sys.argv[2]]))
''')
r24 = subprocess.run([sys.executable, str(internal2), ADAPTY, str(TMP / 'i2.json')],
                     capture_output=True, text=True)
check('THE SECOND InternalError SITE ALSO REACHES 3 -- select_scope\'s accounting '
      'invariant, exercised so that a mutation on it cannot pass unnoticed',
      r24.returncode == 3, f'{r24.returncode} {r24.stderr[:200]}')
check('and it names the withheld count as the thing that cannot be trusted',
      'withheld count' in r24.stderr, r24.stderr)
check('and it earns the strong claim about the input',
      'input is almost certainly fine' in r24.stderr, r24.stderr)

check('InternalError is raised at more than one site, so the opt-in path is a real '
      'mechanism rather than one test\'s hook',
      MIGRATE.read_text().count('raise InternalError') >= 2,
      str(MIGRATE.read_text().count('raise InternalError')))
check('the module docstring states the RULE rather than promising an inventory of '
      'failures -- an inventory only covers what its author remembered',
      'unknown is reported as 2' in MIGRATE.read_text().replace('\n    ', ' ')
      or 'An unclassified failure is UNKNOWN' in MIGRATE.read_text(),
      'rule statement missing from docstring')
check('the docstring names CALLER FLAGS among the outside-data kinds -- the '
      'category the old enumeration omitted entirely',
      'CALLER FLAGS' in MIGRATE.read_text())

# --- bad-input handling: main() must report cleanly at exit 2, never a traceback ---

missing = TMP / 'does-not-exist.json'
r4 = subprocess.run([sys.executable, str(MIGRATE), 'plan', '--inventory', str(missing)],
                    capture_output=True, text=True)
check('a missing --inventory file exits 2', r4.returncode == 2, str(r4.returncode))
check('a missing --inventory file names the path in stderr', str(missing) in r4.stderr, r4.stderr)
check('a missing --inventory file prints no traceback', 'Traceback' not in r4.stderr, r4.stderr)

malformed = TMP / 'malformed.json'
malformed.write_text('{not json')
r5 = subprocess.run([sys.executable, str(MIGRATE), 'plan', '--inventory', str(malformed)],
                    capture_output=True, text=True)
check('malformed JSON exits 2', r5.returncode == 2, str(r5.returncode))
check('malformed JSON names the path in stderr', str(malformed) in r5.stderr, r5.stderr)
check('malformed JSON prints no traceback', 'Traceback' not in r5.stderr, r5.stderr)

no_placements = TMP / 'no-placements.json'
no_placements.write_text(json.dumps({'app': 'app-1'}))
r6 = subprocess.run([sys.executable, str(MIGRATE), 'plan', '--inventory', str(no_placements)],
                    capture_output=True, text=True)
check('JSON with no placements list exits 2', r6.returncode == 2, str(r6.returncode))
check('JSON with no placements list names the path in stderr',
      str(no_placements) in r6.stderr, r6.stderr)
check('JSON with no placements list prints no traceback', 'Traceback' not in r6.stderr, r6.stderr)

unwritable_out = TMP / 'no-such-dir' / 'out.json'
r7 = subprocess.run([sys.executable, str(MIGRATE), 'inventory', '--app', 'app-1',
                    '--adapty', ADAPTY, '--out', str(unwritable_out)],
                   capture_output=True, text=True)
check('an unwritable --out path exits 2', r7.returncode == 2, str(r7.returncode))
check('an unwritable --out path names the path in stderr', str(unwritable_out) in r7.stderr, r7.stderr)
check('an unwritable --out path prints no traceback', 'Traceback' not in r7.stderr, r7.stderr)

# THE CONTRAST. Stated as a named inventory rather than a count, because "all TEN
# input errors are 2" is only ever true of the ten it tests -- and that framing is
# what let the audience-entry leak survive a fix round. Every malformed-input case
# in this file is enumerated here, so adding a case without adding it to this list
# is the omission to guard against.
BAD_INPUT = {
    'missing file': r4, 'malformed JSON': r5, 'no placements list': r6,
    'unwritable --out': r7, 'ledger not an object': r10,
    'row missing developer_id': r11, 'row not a dict': r15, 'row missing id': r16,
    'row empty developer_id': r16b, 'audiences not a list': r17,
    'list row with no id': r21, 'non-numeric pages': r22,
    **{f'segment_ids: {name}': run for name, run in seg_runs.items()},
    'segment_ids string with --flows': seg_flows,
    **{f'response shape: {name}': run for name, run in shape_runs.items()},
    **{f'--page-size {value}': run for value, run in flag_runs.items()},
    'unclassified failure': r23,
    **{f'audience: {name}': run for name, run in aud_runs.items()},
}
check(f'EXIT 3 IS OPT-IN AND NOTHING FROM OUTSIDE REACHES IT -- all '
      f'{len(BAD_INPUT)} cases here (malformed files, malformed responses, a bad '
      f'caller flag, and an UNCLASSIFIED internal failure) exit 2, and only the '
      f'deliberate invariant violation exits 3',
      {name: r.returncode for name, r in BAD_INPUT.items()}
      == {name: 2 for name in BAD_INPUT} and r18.returncode == 3,
      str({n: r.returncode for n, r in BAD_INPUT.items() if r.returncode != 2})
      + f' bug={r18.returncode}')
check('and NO input error claims to be a bug in the tool -- the boundary is real in '
      'the message as well as in the code',
      not any('bug in migrate.py' in r.stderr for r in BAD_INPUT.values()),
      str([n for n, r in BAD_INPUT.items() if 'bug in migrate.py' in r.stderr]))
check('AND NO CAUSE-SPECIFIC CASE IS SERVED BY THE CATCH-ALL. This is the '
      'inversion\'s one cost: exit 2 is now both the specific and the generic '
      'answer, so a code-only assertion cannot tell a working guard from a '
      'deleted one. Every named case must carry its own wording.',
      not any('not classified' in r.stderr for name, r in BAD_INPUT.items()
              if name != 'unclassified failure'),
      str([n for n, r in BAD_INPUT.items()
           if n != 'unclassified failure' and 'not classified' in r.stderr]))
check('the contrast spans every kind of outside data, so it cannot be true only '
      'of the cases someone remembered: file, row, audience entry, segment_ids, '
      'CLI response, caller flag, and unclassified',
      all(any(n.startswith(prefix) for n in BAD_INPUT) for prefix in
          ('row ', 'audience: ', 'segment_ids', 'response shape: ', '--page-size',
           'unclassified')), str(sorted(BAD_INPUT)))
check('and the UNCLASSIFIED case is inside it, which is the inversion itself: a '
      'failure nobody categorised is reported as 2, so a future unguarded site '
      'degrades to vague-but-true rather than to a confident false claim',
      BAD_INPUT['unclassified failure'].returncode == 2)

for f in sorted(TMP.rglob('*'), reverse=True):
    f.unlink() if f.is_file() else f.rmdir()
TMP.rmdir()

print()
print(f'{len(failures)} failure(s)' if failures else 'all checks passed')
sys.exit(1 if failures else 0)

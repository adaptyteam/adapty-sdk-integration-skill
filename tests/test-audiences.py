"""Audience normalization, both directions.

Prod (pre-!13221) returns audiences WITHOUT content_type; the pod returns them
WITH it; and the CLI REQUIRES it on write (exit 2, no request). So a read must
be normalized before it can be written back, and the normalizer has to be a
no-op on an already-normalized entry.
"""
import pathlib
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent
                       / 'skills' / 'migrate-placements' / 'references'))
import migrate as m

failures = []


def check(label, ok, detail=''):
    print(f'{"ok  " if ok else "FAIL"}  {label}' + (f'  -- {detail}' if detail and not ok else ''))
    if not ok:
        failures.append(label)


def rget(mapping, key):
    """`mapping[key]` as a check-safe read.

    Defensive on purpose, and the reason is a measured one: a direct subscript
    on a report dict raises KeyError at module level, which ABORTS the suite --
    and Python exits 1 for an uncaught exception, the same code these suites
    use for "a check failed". So an aborted run is indistinguishable from a
    failing one at a glance, and every check after the abort looks green by
    never having run. Found while negative-testing the `field_present` ->
    `status_readable` rename, which aborted this file at the first subscript
    and reported zero failures. Same lesson as `flag()` in test-migrate-cli.py.
    """
    return (mapping or {}).get(key)


def raises(exc, fn, *a):
    try:
        fn(*a)
    except exc:
        return True
    except Exception:
        return False
    return False


# ---------- Task 2 ----------

PROD_READ = {'segment_ids': [], 'paywall_id': 'pw-1', 'priority': 0}
POD_READ = {'segment_ids': [], 'priority': 0, 'content_type': 'paywall', 'paywall_id': 'pw-1'}

check('a prod read (no content_type) is normalized to paywall',
      m.normalize_audience(PROD_READ)['content_type'] == m.CONTENT_PAYWALL)
check('a pod read is returned unchanged -- normalization is a no-op post-merge',
      m.normalize_audience(POD_READ) == POD_READ)
m.normalize_audience(PROD_READ)
check('normalization does not mutate its input', 'content_type' not in PROD_READ)
check('a flow_id entry normalizes to flow',
      m.normalize_audience({'flow_id': 'f-1', 'priority': 0})['content_type'] == m.CONTENT_FLOW)
check('an entry with neither id field raises rather than guessing',
      raises(ValueError, m.normalize_audience, {'segment_ids': [], 'priority': 0}))
check('an unknown content_type raises rather than passing through',
      raises(ValueError, m.normalize_audience, {'content_type': 'onboarding', 'priority': 0}))
check('a non-dict entry raises TypeError', raises(TypeError, m.normalize_audience, ['nope']))

conv = m.to_flow_audience({'segment_ids': ['s-1', 's-2'], 'paywall_id': 'pw-1', 'priority': 3}, 'f-9')
check('conversion carries content_type=flow', conv['content_type'] == m.CONTENT_FLOW)
check('conversion preserves segment_ids exactly', conv['segment_ids'] == ['s-1', 's-2'])
check('conversion preserves priority exactly', conv['priority'] == 3)
check('conversion drops paywall_id -- mixing the two id fields is meaningless',
      'paywall_id' not in conv)
check('conversion sets the given flow_id', conv['flow_id'] == 'f-9')
src_segments = ['s1']
converted = m.to_flow_audience({'segment_ids': src_segments, 'paywall_id': 'p'}, 'f')
src_segments.append('s2')
check('conversion COPIES segment_ids rather than aliasing the caller\'s list',
      converted['segment_ids'] == ['s1'], str(converted['segment_ids']))
check('a missing priority defaults to 0',
      m.to_flow_audience({'paywall_id': 'p'}, 'f')['priority'] == 0)

check('content_types reads through un-normalized entries',
      m.content_types([PROD_READ, {'flow_id': 'f-1'}]) == {'paywall', 'flow'})
check('is_mixed is True for a paywall+flow array -- a backend 400',
      m.is_mixed([PROD_READ, {'flow_id': 'f-1'}]) is True)
check('is_mixed is False for an all-flow array',
      m.is_mixed([{'flow_id': 'f-1'}, {'flow_id': 'f-2'}]) is False)
check('is_mixed is False for a single entry', m.is_mixed([PROD_READ]) is False)
check('is_mixed is False for an empty array', m.is_mixed([]) is False)

# ---------- Task 3: enumeration and grouping ----------

def fake_fetch(total, page_size_seen):
    """Serve `total` items across pages, recording the page size asked for."""
    items = [{'id': f'pl-{i}', 'developer_id': f'dev-{i}', 'title': f'T{i}'}
             for i in range(total)]

    def fetch(page, page_size):
        page_size_seen.append(page_size)
        start = (page - 1) * page_size
        chunk = items[start:start + page_size]
        pages = max(1, -(-total // page_size))
        return chunk, {'count': total, 'page': page, 'pages': pages}

    return fetch


seen = []
got = m.paginate(fake_fetch(192, seen), page_size=100)
check('paginate reads EVERY page -- 192 items, not the first page', len(got) == 192,
      f'got {len(got)}')
check('paginate asks for the max page size, not the default 20',
      seen and set(seen) == {100}, f'sizes={sorted(set(seen))}')
check('paginate preserves order', [g['id'] for g in got[:3]] == ['pl-0', 'pl-1', 'pl-2'])

seen2 = []
check('a single short page still works', len(m.paginate(fake_fetch(3, seen2), page_size=100)) == 3)
seen3 = []
check('zero items is not an error', m.paginate(fake_fetch(0, seen3), page_size=100) == [])
seen4 = []
check('an exact multiple of the page size does not over-read',
      len(m.paginate(fake_fetch(200, seen4), page_size=100)) == 200)

PLACEMENTS = [
    {'id': 'pl-a', 'developer_id': 'main', 'title': 'Main',
     'audiences': [{'segment_ids': [], 'paywall_id': 'pw-1', 'priority': 0}]},
    {'id': 'pl-b', 'developer_id': 'onboarding', 'title': 'Onb',
     'audiences': [{'segment_ids': ['s1'], 'paywall_id': 'pw-1', 'priority': 0},
                   {'segment_ids': ['s2'], 'paywall_id': 'pw-2', 'priority': 1}]},
    {'id': 'pl-c', 'developer_id': 'done', 'title': 'Done',
     'audiences': [{'content_type': 'flow', 'flow_id': 'f-1', 'priority': 0}]},
    {'id': 'pl-d', 'developer_id': 'bare', 'title': 'Bare'},
]

groups = m.group_by_paywall(PLACEMENTS)
check('grouping is keyed by distinct paywall -- one reusable flow per paywall',
      sorted(groups) == ['pw-1', 'pw-2'], f'{sorted(groups)}')
check('a paywall used by two placements collects both references',
      sorted(groups['pw-1']) == [('pl-a', 0), ('pl-b', 0)], f"{sorted(groups['pw-1'])}")
check('the audience INDEX is carried, so a multi-audience placement stays addressable',
      groups['pw-2'] == [('pl-b', 1)])
check('an already-flow placement is not grouped for migration',
      all('pl-c' != pid for refs in groups.values() for pid, _ in refs))

summary = m.migratable_summary(PLACEMENTS)
check('summary counts placements holding a migratable paywall audience',
      summary['placements'] == 2, str(summary))
check('summary counts migratable audiences, not placements',
      summary['audiences'] == 3, str(summary))
check('summary counts distinct paywalls == flows needed',
      summary['paywalls'] == 2, str(summary))
check('summary counts already-migrated placements', summary['already_flow'] == 1, str(summary))
check('summary counts placements with no audiences at all', summary['empty'] == 1, str(summary))

# ---------- Task 4: ID proposal and command emission ----------

check('a free suffixed id is proposed as-is',
      m.propose_developer_id('main', {'main'}) == 'main-flow')
check('the ORIGINAL id is never proposed -- IDs are unique across types',
      m.propose_developer_id('main', {'main'}) != 'main')
check('a taken suffixed id escalates to -2',
      m.propose_developer_id('main', {'main', 'main-flow'}) == 'main-flow-2')
check('escalation keeps counting past -2',
      m.propose_developer_id('main', {'main', 'main-flow', 'main-flow-2'}) == 'main-flow-3')
check('a custom suffix is honoured',
      m.propose_developer_id('main', {'main'}, suffix='_v2') == 'main_v2')
check('an empty original raises rather than proposing a bare suffix',
      raises(ValueError, m.propose_developer_id, '', {'main'}))

argv = m.build_create_command('app-1', 'Main', 'main-flow',
                              [{'flow_id': 'f-1', 'segment_ids': [], 'priority': 0}])
check('the emitted command is placements create', argv[:2] == ['placements', 'create'])
check('the emitted command carries --app', 'app-1' in argv)
check('the emitted command carries the proposed developer id', 'main-flow' in argv)
import json as _json
payload = _json.loads(argv[argv.index('--audiences') + 1])
check('every emitted audience entry carries content_type -- else the CLI exits 2',
      all('content_type' in e for e in payload))
check('every emitted audience entry is a flow -- mixed types are a backend 400',
      {e['content_type'] for e in payload} == {'flow'})
check('emission refuses a mixed array rather than sending a 400',
      raises(ValueError, m.build_create_command, 'app-1', 'T', 'd',
             [{'flow_id': 'f-1'}, {'paywall_id': 'pw-1'}]))
check('emission refuses an empty audience array',
      raises(ValueError, m.build_create_command, 'app-1', 'T', 'd', []))

# ---------- Task 12: is_active as the scope filter ----------
#
# `is_active` is owner-confirmed as the placement's own enabled/disabled status on
# both `list` and `get`, and was measured ABSENT in prod AND on the MR !13221 pod.
# So the shape that matters most is the one where NO row carries it, and the rule
# that must not be softened is that absence is UNKNOWN, never False.

ACT = {'id': 'pl-on', 'developer_id': 'on', 'is_active': True}
INACT = {'id': 'pl-off', 'developer_id': 'off', 'is_active': False}
UNK = {'id': 'pl-unk', 'developer_id': 'unk'}
MIXED = [ACT, INACT, UNK]

check('is_active: true reads as active', m.activity(ACT) == m.ACTIVE)
check('is_active: false reads as inactive', m.activity(INACT) == m.INACTIVE)
check('AN ABSENT is_active READS AS UNKNOWN, NOT INACTIVE -- the rule that must '
      'not be softened', m.activity(UNK) == m.UNKNOWN, m.activity(UNK))
check('a NULL is_active is unknown too -- present but unreadable is not a status',
      m.activity({'is_active': None}) == m.UNKNOWN)
check('is_active: 1 is unknown, not active -- `1 == True` in Python, so this '
      'pins `is` over `==`', m.activity({'is_active': 1}) == m.UNKNOWN,
      m.activity({'is_active': 1}))
check('is_active: 0 is unknown, not inactive -- the same trap from the other side',
      m.activity({'is_active': 0}) == m.UNKNOWN, m.activity({'is_active': 0}))
check('a string is_active is unknown rather than truthy',
      m.activity({'is_active': 'true'}) == m.UNKNOWN)

parts = m.partition_by_activity(MIXED)
check('the partition is three-way, never two',
      sorted(parts) == ['active', 'inactive', 'unknown'], str(sorted(parts)))
check('a mixed set partitions correctly',
      [len(parts[k]) for k in (m.ACTIVE, m.INACTIVE, m.UNKNOWN)] == [1, 1, 1],
      str({k: len(v) for k, v in parts.items()}))
check('the partition keeps the rows themselves, not just counts',
      parts[m.ACTIVE] == [ACT] and parts[m.INACTIVE] == [INACT])
check('every partition key exists even when empty -- a caller can index it blind',
      m.partition_by_activity([]) == {'active': [], 'inactive': [], 'unknown': []})

kept, rep = m.select_scope(MIXED, m.SCOPE_ALL)
check('scope=all keeps every row', len(kept) == 3, str(len(kept)))
check('scope=all filters nothing out', rget(rep, 'filtered_out') == 0, str(rep))
check('scope=all still REPORTS the partition -- the counts do not depend on filtering',
      (rget(rep, 'active'), rget(rep, 'inactive'), rget(rep, 'unknown')) == (1, 1, 1), str(rep))

kept, rep = m.select_scope(MIXED, m.SCOPE_ACTIVE)
check('scope=active EXCLUDES the inactive row', INACT not in kept, str(kept))
check('scope=active keeps the active row', kept == [ACT], str(kept))
check('scope=active excludes the UNKNOWN row too -- unknown is not known-active',
      UNK not in kept, str(kept))
check('scope=active reports the filtered-OUT count alongside the kept count -- '
      'a filter that hides work is worse than no filter',
      (rget(rep, 'kept'), rget(rep, 'filtered_out')) == (1, 2), str(rep))
check('the report breaks the excluded rows down, so "I disabled these" is '
      'distinguishable from "I could not tell"',
      (rget(rep, 'inactive'), rget(rep, 'unknown')) == (1, 1), str(rep))
check('a mixed set does NOT trigger the fallback -- the field is present',
      rget(rep, 'fallback') is False and rget(rep, 'applied') == 'active', str(rep))
check('the report names what was asked for as well as what was applied',
      rget(rep, 'requested') == 'active', str(rep))

ALL_UNKNOWN = [UNK, {'id': 'pl-2', 'developer_id': 'two'}]
kept, rep = m.select_scope(ALL_UNKNOWN, m.SCOPE_ACTIVE)
check('AN ALL-ABSENT SET UNDER scope=active FALLS BACK TO EVERY ROW, never empty '
      '-- on today\'s API this is every account', kept == ALL_UNKNOWN, str(kept))
check('the fallback is RECORDED, so the skill can say it happened',
      rget(rep, 'fallback') is True, str(rep))
check('the fallback records that `all` was applied though `active` was requested',
      (rget(rep, 'requested'), rget(rep, 'applied')) == ('active', 'all'), str(rep))
check('the fallback says WHY in words, not just a boolean',
      'unknown' in rep.get('fallback_reason', '')
      and 'inactive' in rep.get('fallback_reason', ''), str(rep.get('fallback_reason')))
check('the fallback filters nothing out', rget(rep, 'filtered_out') == 0, str(rep))
check('status_readable is False only when NO row carries a readable is_active',
      rget(rep, 'status_readable') is False
      and rget(m.select_scope(MIXED, m.SCOPE_ACTIVE)[1], 'status_readable') is True)
check('status_readable is False for a row whose is_active is null -- the field is '
      'PRESENT and reports no status, which is what the name means',
      rget(m.select_scope([{'id': 'p', 'is_active': None}], m.SCOPE_ACTIVE)[1], 'status_readable')
      is False)
check('the old name is gone, not aliased -- one name per fact',
      'field_present' not in m.select_scope(MIXED, m.SCOPE_ALL)[1],
      str(sorted(m.select_scope(MIXED, m.SCOPE_ALL)[1])))
check('one known-inactive row is enough to make the status readable -- the fallback '
      'keys on the FIELD, not on finding something active',
      rget(m.select_scope([INACT, UNK], m.SCOPE_ACTIVE)[1], 'fallback') is False)

# unknown_withheld: the escalation is a flag in the DATA, not a line of prose an
# agent has to remember to look for. The exclusion behaviour itself is unchanged.
_, unk_rep = m.select_scope(MIXED, m.SCOPE_ACTIVE)
check('withholding an unknown row RAISES A FLAG IN THE PAYLOAD, so phase 4\'s widen '
      'question is triggered by data rather than by remembering to look',
      rget(unk_rep, 'unknown_withheld') is True, str(unk_rep))
check('the unknown flag carries a reason naming the count',
      '1 placement(s)' in unk_rep.get('unknown_reason', ''), str(unk_rep.get('unknown_reason')))
check('the unknown flag says the rows were withheld as unknown, NOT as inactive',
      'not as inactive' in unk_rep.get('unknown_reason', ''),
      str(unk_rep.get('unknown_reason')))
check('no unknown rows withheld => the flag stays False, so it never cries wolf',
      rget(m.select_scope([ACT, INACT], m.SCOPE_ACTIVE)[1], 'unknown_withheld') is False)
check('scope=all withholds nothing, so the flag is False even with unknown rows '
      'present -- it flags an EXCLUSION, not the mere existence of unknowns',
      rget(m.select_scope(MIXED, m.SCOPE_ALL)[1], 'unknown_withheld') is False,
      str(m.select_scope(MIXED, m.SCOPE_ALL)[1]))
check('the all-unknown FALLBACK does not raise the flag either -- it withheld '
      'nothing, and the fallback already says what happened',
      rget(m.select_scope(ALL_UNKNOWN, m.SCOPE_ACTIVE)[1], 'unknown_withheld') is False,
      str(m.select_scope(ALL_UNKNOWN, m.SCOPE_ACTIVE)[1]))
check('describe_scope surfaces the unknown escalation in its one line',
      'not as inactive' in m.describe_scope(unk_rep), m.describe_scope(unk_rep))
off_kept, off_rep = m.select_scope([INACT], m.SCOPE_ACTIVE)
check('an all-inactive account under scope=active is legitimately EMPTY, and is '
      'NOT a fallback -- that is a real answer, not a missing field',
      off_kept == [] and rget(off_rep, 'fallback') is False, f'{off_kept} {off_rep}')
check('and it still reports the one row it withheld',
      rget(off_rep, 'filtered_out') == 1 and rget(off_rep, 'inactive') == 1, str(off_rep))

empty_kept, empty_rep = m.select_scope([], m.SCOPE_ACTIVE)
check('an empty account is not a fallback -- there is nothing to fall back to',
      empty_kept == [] and rget(empty_rep, 'fallback') is False, str(empty_rep))
check('an unknown scope raises rather than silently keeping everything',
      raises(ValueError, m.select_scope, MIXED, 'live'))
check('select_scope does not alias the caller\'s list',
      m.select_scope(MIXED, m.SCOPE_ALL)[0] is not MIXED)

line = m.describe_scope(m.select_scope(MIXED, m.SCOPE_ACTIVE)[1])
check('describe_scope names the filtered-out count in words',
      '2 filtered out' in line, line)
check('describe_scope names every one of the three counts',
      '1 active' in line and '1 inactive' in line and '1 unknown' in line, line)
fb_line = m.describe_scope(m.select_scope(ALL_UNKNOWN, m.SCOPE_ACTIVE)[1])
check('describe_scope announces the fallback', 'fell back to all' in fb_line, fb_line)
check('describe_scope prints ? rather than raising on a partial scope block -- it '
      'is called on a block read from a user-editable file',
      '?' in m.describe_scope({'applied': 'active'}))

# ---------- Fix round 2: the audience-entry shape check ----------
#
# `normalize_audience` returns EARLY when content_type is declared, so it validates
# the type and never the id. `group_by_paywall` then subscripts entry['paywall_id'].
# `_audience_problem` is the check that closes that gap; these pin the two facts it
# has to keep separate -- a declared type, and a present id.

check('a declared paywall type with NO paywall_id is a problem -- the exact leak, '
      'and the case normalize_audience passes',
      m._audience_problem({'content_type': 'paywall', 'priority': 0}) is not None)
check('normalize_audience itself still ACCEPTS that entry, which is why the check '
      'has to live outside it rather than inside',
      m.normalize_audience({'content_type': 'paywall', 'priority': 0})
      ['content_type'] == 'paywall')
check('the problem names the missing field', "'paywall_id'" in
      (m._audience_problem({'content_type': 'paywall'}) or ''))
check('a declared flow type with no flow_id is a problem too', "'flow_id'" in
      (m._audience_problem({'content_type': 'flow'}) or ''))
check('an empty-string paywall_id is a problem, not a usable id',
      m._audience_problem({'content_type': 'paywall', 'paywall_id': ''}) is not None)
check('a non-string paywall_id is a problem',
      m._audience_problem({'content_type': 'paywall', 'paywall_id': 42}) is not None)
check('a non-dict entry is a problem, and names the type it got',
      'is a str' in (m._audience_problem('nope') or ''))
check('an entry with no derivable type is a problem, reusing normalize_audience\'s '
      'own message rather than inventing a second wording',
      'cannot be derived' in (m._audience_problem({'priority': 0}) or ''))
check('an unknown content_type is a problem',
      'unknown content_type' in (m._audience_problem({'content_type': 'onboarding'}) or ''))
check('a VALID pre-!13221 entry is NOT a problem -- the check must not fire on the '
      'shape it exists to protect',
      m._audience_problem({'paywall_id': 'pw-1', 'segment_ids': [], 'priority': 0}) is None)
check('a VALID pod-shaped entry is not a problem either',
      m._audience_problem({'content_type': 'paywall', 'paywall_id': 'pw-1'}) is None)
check('a valid flow entry is not a problem',
      m._audience_problem({'content_type': 'flow', 'flow_id': 'f-1'}) is None)
check('a derived-type entry is not a problem -- deriving the type also proves the '
      'id was there, so the two paths agree',
      m._audience_problem({'flow_id': 'f-1'}) is None)
check('the problem is a one-line string, never a raise -- the caller turns it into '
      'a message, and an exception here would land on the tool-bug exit code',
      isinstance(m._audience_problem({'content_type': 'paywall'}), str))

# ---------- Fix round 3: segment_ids, _api_field, and the opt-in exit 3 ----------

check('a STRING segment_ids is a problem -- it does not crash, it spreads one '
      'segment per character and ships corrupted targeting',
      m._audience_problem({'paywall_id': 'pw', 'segment_ids': 'ab'}) is not None)
check('and the reason names the per-character spread',
      'per CHARACTER' in (m._audience_problem(
          {'paywall_id': 'pw', 'segment_ids': 'ab'}) or ''))
check('the corruption it prevents is real: list("ab") really is two segments',
      list('ab') == ['a', 'b'])
check('an int segment_ids is a problem', m._audience_problem(
    {'paywall_id': 'pw', 'segment_ids': 5}) is not None)
check('a dict segment_ids is a problem', m._audience_problem(
    {'paywall_id': 'pw', 'segment_ids': {}}) is not None)
check('a non-string ELEMENT is a problem -- the array is carried over verbatim',
      m._audience_problem({'paywall_id': 'pw', 'segment_ids': [5]}) is not None)
check('an empty-string element is a problem too',
      m._audience_problem({'paywall_id': 'pw', 'segment_ids': ['']}) is not None)
check('a valid list of segment ids is NOT a problem',
      m._audience_problem({'paywall_id': 'pw', 'segment_ids': ['s1']}) is None)
check('an EMPTY list is not a problem -- it is the commonest real value',
      m._audience_problem({'paywall_id': 'pw', 'segment_ids': []}) is None)
check('an ABSENT segment_ids is not a problem -- a read may omit it, and '
      'rejecting that would refuse valid inventories',
      m._audience_problem({'paywall_id': 'pw'}) is None)

def fetch_returning(pagination):
    def fetch(page, size):
        return [{'id': 'p'}], pagination
    return fetch


check('paginate refuses a non-object pagination -- it is public and takes any '
      '`fetch`, so it cannot rely on fetch_placements having checked first',
      raises(m.CliError, m.paginate, fetch_returning([1])))
check('paginate refuses a non-numeric pages with a CliError, not a bare ValueError',
      raises(m.CliError, m.paginate, fetch_returning({'pages': 'lots'})))
check('paginate accepts a missing pagination as one page',
      len(m.paginate(fetch_returning(None))) == 1)
check('paginate accepts a numeric-string pages, which JSON APIs do emit',
      len(m.paginate(fetch_returning({'pages': '1'}))) == 1)

check('_api_field returns the value when the type matches',
      m._api_field({'meta': {'a': 1}}, 'meta', dict, {}, 'x') == {'a': 1})
check('_api_field returns the default when the key is absent',
      m._api_field({}, 'meta', dict, {'d': 1}, 'x') == {'d': 1})
check('_api_field returns the default for an explicit null',
      m._api_field({'meta': None}, 'meta', dict, {'d': 1}, 'x') == {'d': 1})
check('_api_field returns an EMPTY value of the right type as itself, not the '
      'default -- an empty page of results is a real answer',
      m._api_field({'data': []}, 'data', list, ['fallback'], 'x') == [])
check('_API_FIELD RAISES ON A NON-EMPTY VALUE OF THE WRONG TYPE, which is exactly '
      'what `x.get(k) or {}` let through: falsiness was guarded, type was not',
      raises(m.CliError, m._api_field, {'meta': [1]}, 'meta', dict, {}, 'x'))
check('and it raises when the CONTAINER is not an object either',
      raises(m.CliError, m._api_field, ['nope'], 'meta', dict, {}, 'x'))
check('it raises CliError specifically, so the failure lands on exit 2 as an '
      'environment problem rather than on the internal path',
      raises(m.CliError, m._api_field, {'meta': 'str'}, 'meta', dict, {}, 'x'))
try:
    m._api_field({'meta': [1]}, 'meta', dict, {}, 'the list response')
    api_msg = ''
except m.CliError as exc:
    api_msg = str(exc)
check('the message names the key, the type it got and the type it wanted',
      all(tok in api_msg for tok in ('"meta"', 'list', 'dict')), api_msg)
check('and it names WHERE, so the reader knows which response was wrong',
      'the list response' in api_msg, api_msg)

check('InternalError is a distinct exception, not an alias of CliError -- the two '
      'route to different exit codes',
      issubclass(m.InternalError, Exception)
      and not issubclass(m.InternalError, m.CliError)
      and not issubclass(m.CliError, m.InternalError))
check('select_scope asserts its own accounting invariant, and it holds on every '
      'shape used above',
      all(m.select_scope(rows, scope)[1]['kept']
          + m.select_scope(rows, scope)[1]['filtered_out'] == len(rows)
          for rows in (MIXED, ALL_UNKNOWN, [INACT], [])
          for scope in (m.SCOPE_ACTIVE, m.SCOPE_ALL)))

plan_scoped = m.build_plan(PLACEMENTS, scope={'kept': 2, 'filtered_out': 7})
check('build_plan carries the scope block into summary, so the phase-3 report '
      'cannot omit it', plan_scoped['summary'].get('scope', {}).get('filtered_out') == 7,
      str(plan_scoped['summary']))
check('build_plan with no scope adds no scope key, but keeps the five counts',
      set(m.build_plan(PLACEMENTS)['summary'])
      == {'placements', 'audiences', 'paywalls', 'already_flow', 'empty', 'exposure'},
      str(sorted(m.build_plan(PLACEMENTS)['summary'])))

# EXPOSURE vs SCOPE. `scope` partitions the whole `list`; `exposure` partitions the
# placements the plan would actually CREATE, which excludes already-flow and empty
# ones. Phase 6 quotes the live exposure a stub causes, so reading `scope` there
# overstates it -- the reviewer measured 3 vs 1 on exactly this fixture.

ALL_ON = [dict(p, is_active=True) for p in PLACEMENTS]
exp = rget(m.build_plan(ALL_ON)['summary'], 'exposure')
check('exposure is always emitted, with no scope block needed',
      isinstance(exp, dict), str(exp))
check('EXPOSURE COUNTS THE PLAN ROWS, NOT THE ACCOUNT -- 4 placements all active, '
      'but only 2 are migratable, so exposure.active is 2 and not 4',
      (rget(exp, 'placements'), rget(exp, 'active')) == (2, 2), str(exp))
scope_wide = m.select_scope(ALL_ON, m.SCOPE_ALL)[1]
check('and the two numbers genuinely DIVERGE on this fixture, which is why one '
      'cannot be substituted for the other',
      rget(scope_wide, 'active') == 4 and rget(exp, 'active') == 2,
      f"scope.active={rget(scope_wide, 'active')} exposure.active={rget(exp, 'active')}")
check('exposure sums to the number of plan rows',
      sum(rget(exp, k) or 0 for k in ('active', 'inactive', 'unknown'))
      == rget(exp, 'placements'), str(exp))
check('exposure matches the row count build_plan actually emitted',
      rget(exp, 'placements') == len(m.build_plan(ALL_ON)['placements']), str(exp))

MIXED_MIGRATABLE = [
    {'id': 'pl-a', 'developer_id': 'main', 'is_active': True,
     'audiences': [{'paywall_id': 'pw-1', 'priority': 0}]},
    {'id': 'pl-b', 'developer_id': 'old', 'is_active': False,
     'audiences': [{'paywall_id': 'pw-2', 'priority': 0}]},
    {'id': 'pl-c', 'developer_id': 'huh',
     'audiences': [{'paywall_id': 'pw-3', 'priority': 0}]},
    {'id': 'pl-d', 'developer_id': 'gone', 'is_active': True,
     'audiences': [{'content_type': 'flow', 'flow_id': 'f-1', 'priority': 0}]},
]
exp2 = rget(m.build_plan(MIXED_MIGRATABLE)['summary'], 'exposure')
check('exposure splits the plan rows three ways, same rules as the scope filter',
      (rget(exp2, 'active'), rget(exp2, 'inactive'), rget(exp2, 'unknown')) == (1, 1, 1), str(exp2))
check('an ACTIVE already-flow placement is excluded from exposure -- it is not '
      'being migrated, so it is not exposed', rget(exp2, 'placements') == 3, str(exp2))
check('exposure.status_readable is True when any plan row has a readable status',
      rget(exp2, 'status_readable') is True, str(exp2))
exp3 = rget(m.build_plan(PLACEMENTS)['summary'], 'exposure')
check('the exposure partition covers exactly the plan rows on every fixture here',
      all(sum((rget(m.build_plan(rows)['summary'], 'exposure') or {}).get(k) or 0
              for k in ('active', 'inactive', 'unknown'))
          == len(m.build_plan(rows)['placements'])
          for rows in (PLACEMENTS, ALL_ON, MIXED_MIGRATABLE)))

check('exposure.status_readable is FALSE on today\'s API, which is what routes '
      'phase 6 to the verbatim acknowledgment instead of a fabricated count',
      rget(exp3, 'status_readable') is False and rget(exp3, 'unknown') == rget(exp3, 'placements'),
      str(exp3))

print()
print(f'{len(failures)} failure(s)' if failures else 'all checks passed')
sys.exit(1 if failures else 0)

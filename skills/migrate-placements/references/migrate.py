#!/usr/bin/env python3
"""Placement migration helpers: paywall placements -> new flow placements.

Stdlib only. Two traps live here rather than in prose, because prose lost to
both of them before:

1. PAGINATION. `--page-size` defaults to 20 and the response carries
   meta.pagination {count, page, pages}. Reading page 1 and reporting its
   length under-reports a 150-placement app by 130.
2. content_type. A pre-!13221 read omits it and every write requires it
   (CLI-side, exit 2, no request). So a read cannot be written back without
   normalization. The pod already returns it, so this is a compatibility
   shim that becomes a no-op -- it must accept both shapes.

3. is_active. Owner-confirmed as the placement's own enabled/disabled status,
   on both `list` and `get` -- and measured ABSENT in production and on the
   MR !13221 pod. So absence is the common case, absence means UNKNOWN, and
   `select_scope` partitions three ways rather than two.

This module NEVER emits a `placements update` that changes content type: the
backend refuses it with `Placement type can not be changed.`

`plan --flows <ledger>` is how the create argv is produced. `placements
create` has no preview and no prompt, so whatever argv is sent is sent --
which is why the argv is GENERATED here, through `build_create_command` and
`to_flow_audience`, rather than retyped from a doc where the mixed-audience
raise and the `content_type` injection can be skipped by hand.

EXIT CODES, and the split is deliberate because the two demand different
actions from the caller:

    0  fine
    2  it did not work, and the cause was not positively identified as
       internal. Covers everything from "your file has a typo on row 3" to
       "something unexpected happened" -- the message says which, and says
       plainly when it does not know. Read it, check your input, re-run.
    3  a bug in this tool: an invariant THIS MODULE COMPUTED was violated.
       Your input is almost certainly fine. Stop and report it.

THE DEFAULT IS 2 AND EXIT 3 IS OPT-IN. That inversion is the whole design,
and it is here because the other arrangement failed three times.

Exit 3 used to be the catch-all, which made it a claim -- "this is a bug in
migrate.py, your inventory may be fine" -- asserted about every failure
nobody had classified yet. Its correctness therefore depended on having
exhaustively enumerated every way this module can fail, and three successive
attempts to write that enumeration each left holes: a row missing a field, an
audience entry with a declared type and no id, a malformed API response, a
`segment_ids` that is a string. Each attempt was believed complete. The
obligation is not meetable, because an enumeration only ever covers what its
author remembered, while the module keeps growing.

So the promise is gone and a rule stands in its place:

    An unclassified failure is UNKNOWN, and unknown is reported as 2.
    Exit 3 is raised only by `raise InternalError(...)`, at a site where the
    code can say WHY the failure is internal.

The failure mode moves from confidently-wrong to honestly-uncertain. Before,
an unguarded site told the user their file was fine when their file was the
problem; now it tells them something broke and it is not sure why. The false
claim is UNREPRESENTABLE except where somebody deliberately wrote it, which
is this repo's own standard -- make the wrong shape unrepresentable rather
than merely detectable -- applied to the classifier instead of to a config.

Guidance for adding to this module, in place of the old inventory:

  * Validating an input near where it is read still buys a better message,
    and is still worth doing. It is no longer load-bearing for correctness.
  * WHERE YOU GUARD A VALUE'S PRESENCE, GUARD ITS TYPE IN THE SAME PLACE.
    Three separate leaks were this one mistake: `x.get(k) or {}` guards
    FALSINESS, so a list where an object belongs passes and dies on the next
    subscript. `_api_field` exists for exactly this.
  * Never raise `InternalError` for anything a caller handed you -- a file, a
    flag, a CLI response. Those are 2 whether or not you classified them.
  * Do not reintroduce "your input may be fine" on the catch-all path. It is
    the sentence that made the old design wrong.

Five kinds of data arrive from outside and none of them can produce a 3: the
INVENTORY FILE, the FLOWS LEDGER, CLI RESPONSES, CALLER FLAGS (`--page-size`
has an API-imposed range and an agent raising it is the natural mistake), and
the FILESYSTEM. Data this module built itself is the only place an internal
invariant can be asserted about.
"""
import json
import pathlib

CONTENT_PAYWALL = 'paywall'
CONTENT_FLOW = 'flow'
CONTENT_TYPES = (CONTENT_PAYWALL, CONTENT_FLOW)


def normalize_audience(entry):
    """Return a copy of `entry` with `content_type` filled in.

    Derives it from whichever id field is present, because that is the only
    signal a pre-!13221 read gives. Refuses to guess when there is none.
    """
    if not isinstance(entry, dict):
        raise TypeError(f'an audience entry must be a dict, got {type(entry).__name__}')
    out = dict(entry)
    declared = out.get('content_type')
    if declared in CONTENT_TYPES:
        return out
    if declared is not None:
        raise ValueError(
            f'unknown content_type {declared!r}; the CLI accepts only '
            f'{CONTENT_PAYWALL!r} or {CONTENT_FLOW!r}')
    if 'paywall_id' in out:
        out['content_type'] = CONTENT_PAYWALL
    elif 'flow_id' in out:
        out['content_type'] = CONTENT_FLOW
    else:
        raise ValueError(
            'audience entry has no content_type and neither paywall_id nor '
            'flow_id, so its type cannot be derived: ' + repr(entry))
    return out


def to_flow_audience(entry, flow_id):
    """Build the flow audience that replaces a paywall audience.

    `segment_ids` and `priority` are carried over verbatim -- they are the
    targeting the migration must not silently change.
    """
    if not flow_id:
        raise ValueError('to_flow_audience needs a flow_id')
    src = normalize_audience(entry)
    return {
        'content_type': CONTENT_FLOW,
        'flow_id': flow_id,
        'segment_ids': list(src.get('segment_ids') or []),
        'priority': src.get('priority', 0),
    }


def content_types(entries):
    """The set of content types in an audience array, normalizing as it reads."""
    return {normalize_audience(e)['content_type'] for e in entries}


def is_mixed(entries):
    """True when an array mixes paywall and flow entries -- a backend 400."""
    return len(content_types(entries)) > 1


class CliError(Exception):
    """A CLI call failed, or its response was not the shape we can read.

    Both are the environment misbehaving, not this module, so both land on
    exit 2. Raised rather than left to a subscript so the message can name
    the field and the value.
    """


class InternalError(Exception):
    """An invariant THIS MODULE COMPUTED has been violated.

    THE ONLY ROUTE TO EXIT 3, deliberately. Raise it where the code can state
    why the failure has to be internal -- both sides of the broken equation
    were produced here, from data this module already validated. If you
    cannot name that reason at the raise site, it is not an InternalError:
    let it fall to the catch-all, which reports 2 and says it is unsure.

    Never raise it about a file, a flag or a CLI response. Those come from
    outside and are exit 2 whether or not anyone classified them.
    """


def _api_field(container, key, kind, default, where):
    """`container[key]`, type-checked, or `default` when absent.

    GUARDS PRESENCE AND TYPE IN ONE PLACE, which is the point. The idiom this
    replaces -- `container.get(key) or {}` -- guards only FALSINESS, so a
    non-empty value of the wrong type (`meta: [1]`, `data: {...}`) passes the
    guard untouched and dies on the next subscript with an `AttributeError`
    about `.get`. That single mistake accounted for three separate leaks of
    the exit-code boundary, so it is now one function with one behaviour.
    """
    if not isinstance(container, dict):
        raise CliError(f'{where}: expected an object, got '
                       f'{type(container).__name__}')
    value = container.get(key)
    if value is None:
        return default
    if not isinstance(value, kind):
        raise CliError(f'{where}: "{key}" is {type(value).__name__}, expected '
                       f'{kind.__name__} -- the response is not the shape this '
                       'tool can read')
    return value


MAX_PAGE_SIZE = 100


def paginate(fetch, page_size=MAX_PAGE_SIZE):
    """Read every page. `fetch(page, page_size)` returns (items, pagination).

    `pagination` is the response's meta.pagination: {'count','page','pages'}.
    This exists because `--page-size` defaults to 20, so the obvious
    single call under-reports any app with more than 20 rows.
    """
    if not 1 <= page_size <= MAX_PAGE_SIZE:
        raise ValueError(f'page_size must be 1..{MAX_PAGE_SIZE}, got {page_size}')
    items, pagination = fetch(1, page_size)
    out = list(items)
    # `pages` comes off the API. A non-numeric value is the environment
    # misbehaving, not a bug here, so it is routed rather than left to raise a
    # bare ValueError into the catch-all.
    if pagination is not None and not isinstance(pagination, dict):
        raise CliError(f'meta.pagination is a {type(pagination).__name__}, not an '
                       'object; the response is not the shape this tool can read')
    raw_pages = (pagination or {}).get('pages') or 1
    try:
        pages = int(raw_pages)
    except (TypeError, ValueError):
        raise CliError(
            f'meta.pagination.pages is {raw_pages!r}, which is not a page '
            'count; cannot tell how many pages to read') from None
    for page in range(2, pages + 1):
        more, _ = fetch(page, page_size)
        out.extend(more)
    return out


ACTIVE = 'active'
INACTIVE = 'inactive'
UNKNOWN = 'unknown'
SCOPE_ACTIVE = 'active'
SCOPE_ALL = 'all'
SCOPES = (SCOPE_ACTIVE, SCOPE_ALL)


def activity(placement):
    """Which of THREE states a placement's `is_active` reports.

    `is_active` is owner-confirmed (2026-09-03) as the placement's own
    enabled/disabled status, returned on both `list` and `get`. It was also
    measured that day to be ABSENT in production and absent on the MR !13221
    pod -- so on today's API this returns UNKNOWN for every placement, and
    that is the case the caller must survive.

    ABSENT IS NOT FALSE. Reading absence as `False` filters an entire
    present-day account out and reports an empty migration: a silent, total
    failure that looks like a clean result. It is the same class of error as
    reading a pre-!13221 audience with no `content_type` as having no type.

    `is` rather than `==` is load-bearing: `1 == True` and `0 == False` in
    Python, so `==` would read a non-boolean value as a status the API never
    sent. A present-but-unreadable value (null, a number, a string) is
    UNKNOWN, because "we cannot tell" is what it means.
    """
    value = (placement or {}).get('is_active')
    if value is True:
        return ACTIVE
    if value is False:
        return INACTIVE
    return UNKNOWN


def partition_by_activity(placements):
    """Three lists keyed by `activity()`. Never two, and never collapsed."""
    out = {ACTIVE: [], INACTIVE: [], UNKNOWN: []}
    for placement in placements:
        out[activity(placement)].append(placement)
    return out


def select_scope(placements, scope=SCOPE_ALL):
    """(rows to spend GETs on, a report of what was kept AND withheld).

    Called on the `list` result, BEFORE the per-placement GETs. That position
    is the call saving -- `list` is owner-stated to carry `is_active` while
    audiences are only on `get`, so filtering first turns a 150-placement app
    with 30 active from 2 + 150 calls into 2 + 30.

    THE POSITION IS SEPARABLE FROM THE PARTITION, and only the position rests
    on `is_active` being on `list`. If it ships on `get` only, this function
    moves after the GET loop and everything it reports -- the three-way split,
    the withheld counts, the fallback -- is unchanged and still needed by the
    scope question, the stub exposure count and the rehearsal order. The only
    casualty is the arithmetic above.

    Two rules are mechanical here rather than remembered:

    1. An all-unknown set under `scope=active` FALLS BACK to every row
       instead of returning empty, and records that it did. On today's API
       that is every account, so the alternative is a tool that reports
       "nothing to migrate" for everyone.
    2. The withheld count is produced by the same code that withholds, so a
       caller cannot report the kept count alone. A filter that hides work is
       worse than no filter -- if `is_active`'s real semantics turn out
       narrower than owner-stated, the filter would skip placements that need
       migrating and the user would never see them.

    Note what is deliberately NOT done: under `scope=active` an unknown row
    is filtered out (it is not known-active), but it is counted separately
    from the inactive rows, so the report distinguishes "you disabled these"
    from "I could not tell".
    """
    if scope not in SCOPES:
        raise ValueError(f'scope must be one of {SCOPES}, got {scope!r}')
    rows = list(placements)
    parts = partition_by_activity(rows)
    if sum(len(bucket) for bucket in parts.values()) != len(rows):
        # INTERNAL: `parts` was built here from `rows`, both local, so no input
        # can make this false. If the partition loses a row, every count in the
        # report is computed against a population that is not the account --
        # the withheld count under-reports what was hidden, which is the one
        # thing this function exists to prevent.
        #
        # NOTE the invariant this replaced: `kept + filtered_out == len(rows)`.
        # That one was TAUTOLOGICAL -- `filtered_out` is defined as
        # `len(rows) - len(selected)` and `kept` as `len(selected)`, so it
        # could not fail for any partition at all. An invariant that cannot be
        # violated is an assertion that cannot fail, which is worse than none:
        # it reads as coverage. Found by a mutation on the partition that this
        # check did not notice.
        raise InternalError(
            f'partition_by_activity returned '
            f'{sum(len(b) for b in parts.values())} rows for an input of '
            f'{len(rows)}; every count in the scope report, including the '
            'withheld count, would be measured against the wrong population')
    report = {
        'requested': scope,
        'applied': scope,
        ACTIVE: len(parts[ACTIVE]),
        INACTIVE: len(parts[INACTIVE]),
        UNKNOWN: len(parts[UNKNOWN]),
        # `status_readable`, not `field_present`: `is_active: null` has the field
        # present and reports no status. What the fallback turns on is whether any
        # row carried a READABLE boolean, so the name says that.
        'status_readable': bool(parts[ACTIVE] or parts[INACTIVE]),
        'fallback': False,
        'unknown_withheld': False,
        'kept': len(rows),
        'filtered_out': 0,
    }
    if scope == SCOPE_ALL:
        return rows, report
    if rows and not report['status_readable']:
        report['applied'] = SCOPE_ALL
        report['fallback'] = True
        report['fallback_reason'] = (
            'no placement carries is_active, so activity is unknown rather than '
            'inactive; --scope active was ignored and every placement kept')
        return rows, report
    selected = parts[ACTIVE]
    report['kept'] = len(selected)
    report['filtered_out'] = len(rows) - len(selected)
    # An unknown row is withheld under `active` because it is not known-active --
    # but "I could not tell" is a different thing to tell a user than "you
    # disabled this", and it is the one that should prompt an offer to widen. So
    # the escalation is a FLAG IN THE DATA rather than a line of prose an agent
    # has to remember to look for. The exclusion itself is unchanged.
    if parts[UNKNOWN]:
        report['unknown_withheld'] = True
        report['unknown_reason'] = (
            f'{len(parts[UNKNOWN])} placement(s) carry no readable is_active and '
            'were withheld as unknown, not as inactive; offer --scope all')
    return selected, report


def describe_scope(report):
    """One line naming what was kept AND what was withheld.

    Exists so that reporting the exclusion is the same act as making it. A
    caller that prints this cannot accidentally report only the kept count.

    Every read is a `.get` with a visible `?` default, because this is also
    called on a scope block read back out of an inventory FILE, which a user
    can edit. A missing key must print `?` rather than raise: raising would
    route a bad input into the exit-3 tool-bug guard and blame the tool for
    the user's file. `?` still discloses -- it never reads as zero.
    """
    def n(key):
        return report.get(key, '?')

    counts = (f'{n(ACTIVE)} active', f'{n(INACTIVE)} inactive',
              f'{n(UNKNOWN)} unknown')
    line = (f'scope={n("applied")}: {n("kept")} kept, '
            f'{n("filtered_out")} filtered out ({", ".join(counts)})')
    if report.get('fallback'):
        line += ' -- fell back to all: ' + str(report.get('fallback_reason', ''))
    if report.get('unknown_withheld'):
        line += ' -- ' + str(report.get('unknown_reason', 'unknown rows withheld'))
    return line


def group_by_paywall(placements):
    """paywall_id -> [(placement_id, audience_index)] for migratable audiences.

    The grouping key is the PAYWALL, which is what makes "one reusable flow
    per distinct paywall, shared by every placement using it" fall out.
    """
    groups = {}
    for placement in placements:
        for index, raw in enumerate(placement.get('audiences') or []):
            entry = normalize_audience(raw)
            if entry['content_type'] != CONTENT_PAYWALL:
                continue
            groups.setdefault(entry['paywall_id'], []).append((placement['id'], index))
    return groups


def migratable_summary(placements):
    """Counts for the phase-3 report -- never print one row per placement."""
    groups = group_by_paywall(placements)
    referenced = {pid for refs in groups.values() for pid, _ in refs}
    already_flow = 0
    empty = 0
    for placement in placements:
        audiences = placement.get('audiences') or []
        if not audiences:
            empty += 1
            continue
        if CONTENT_PAYWALL not in content_types(audiences):
            already_flow += 1
    return {
        'placements': len(referenced),
        'audiences': sum(len(refs) for refs in groups.values()),
        'paywalls': len(groups),
        'already_flow': already_flow,
        'empty': empty,
    }


def propose_developer_id(original, taken, suffix='-flow'):
    """Propose a developer id for the NEW flow placement.

    The original can never be reused: placement IDs are unique across every
    placement in the app whatever the type, and a placement cannot be
    deleted, so a collision is permanent. The result is always shown to the
    user for approval before anything is created.
    """
    if not original:
        raise ValueError('propose_developer_id needs the original developer id')
    taken = set(taken or ())
    candidate = f'{original}{suffix}'
    if candidate not in taken:
        return candidate
    n = 2
    while f'{candidate}-{n}' in taken:
        n += 1
    return f'{candidate}-{n}'


def build_create_command(app_id, title, developer_id, audiences):
    """argv for `placements create`. Never `placements update` -- a type change
    is refused by the backend, so every migration is a create."""
    if not audiences:
        raise ValueError('a placement needs at least one audience entry')
    normalized = [normalize_audience(e) for e in audiences]
    kinds = {e['content_type'] for e in normalized}
    if kinds != {CONTENT_FLOW}:
        raise ValueError(
            f'a created flow placement must be all-flow, got {sorted(kinds)}; '
            'mixed paywall+flow audiences are refused by the backend')
    return [
        'placements', 'create',
        '--app', app_id,
        '--title', title,
        '--developer-id', developer_id,
        '--audiences', json.dumps(normalized, separators=(',', ':')),
    ]


def cli_json(adapty, args):
    """Run `<adapty> <args> --json` and parse stdout.

    `adapty` is a command STRING (`adapty`, or `npx --yes adapty@beta`) so the
    caller controls how the CLI is invoked and tests can substitute a stub.

    IT VALIDATES JSON-NESS *AND* OBJECT-NESS. Checking only that stdout parsed
    was one of the three "guarded presence, not type" leaks: a response of
    `[...]`, `"hello"` or `null` parses perfectly and then dies on `.get`
    with an `AttributeError` two frames away from the cause.
    """
    import shlex
    import subprocess
    cmd = shlex.split(adapty) + list(args) + ['--json']
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise CliError(f'{" ".join(cmd)} exited {proc.returncode}: {proc.stderr.strip()}')
    try:
        body = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise CliError(f'{" ".join(cmd)} did not print JSON: {exc}') from exc
    if not isinstance(body, dict):
        raise CliError(f'{" ".join(cmd)} printed a JSON '
                       f'{type(body).__name__} where an object was expected')
    return body


def fetch_placements(adapty, app_id, page_size=MAX_PAGE_SIZE):
    """Every placement summary, all pages.

    Every read of the response goes through `_api_field`, which checks type as
    well as presence. The `or {}` / `or []` idiom this replaces guarded only
    falsiness, so `meta: [1]` or `data: {...}` passed straight through it.
    """
    where = '`placements list` response'

    def fetch(page, size):
        body = cli_json(adapty, ['placements', 'list', '--app', app_id,
                                 '--page', str(page), '--page-size', str(size)])
        rows = _api_field(body, 'data', list, [], where)
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                raise CliError(f'{where}: data[{index}] is a '
                               f'{type(row).__name__}, not a placement object')
        meta = _api_field(body, 'meta', dict, {}, where)
        pagination = _api_field(meta, 'pagination', dict, {}, f'{where} meta')
        return rows, pagination
    return paginate(fetch, page_size=page_size)


def fetch_details(adapty, app_id, placements):
    """One `placements get` per placement -- `list` returns no audiences.

    The `id` read is routed through `CliError` rather than left to subscript,
    because a summary with no usable id is the API or the CLI misbehaving --
    an environment problem, which is exit 2's class -- and not a bug in this
    module. Left bare it was a `KeyError` reaching the catch-all and being
    reported as "a bug in migrate.py".
    """
    out = []
    for index, summary in enumerate(placements):
        placement_id = (summary or {}).get('id')
        if not isinstance(placement_id, str) or not placement_id:
            raise CliError(
                f'`placements list` returned a row at index {index} with no '
                f'usable "id" (got {placement_id!r}), so its audiences cannot '
                'be fetched')
        out.append(cli_json(adapty, ['placements', 'get', '--app', app_id,
                                     placement_id]))
    return out


def build_plan(placements, suffix='-flow', flows=None, app_id=None, scope=None):
    """What to create, with every proposed id pre-checked for collisions.

    `flows` is the phase-5 ledger, `paywall_id -> flow_id`. When it is given,
    every row gains a `command` -- the exact argv for `placements create`,
    built by `build_create_command` from audiences built by
    `to_flow_audience`. That is the point: the guards (the mixed-audience
    raise, the `content_type` injection, the verbatim `segment_ids`/
    `priority`) sit on the documented path rather than beside a
    hand-retyped command block. A row whose paywall is not in the ledger
    gets `missing_flows` and NO `command` -- a broken argv is worse than a
    missing one, because `placements create` has no preview and no prompt.

    With `flows=None` the output is exactly what it was before the flag
    existed: no `command` key anywhere.

    `scope` is the block `inventory` recorded (`select_scope`'s report). It
    is copied into `summary['scope']` so the phase-3 report cannot omit what
    the inventory filtered out -- the plan is the only thing later phases
    read, so a count that stops at the inventory file is a count nobody sees.
    An inventory written before the flag existed carries no scope, and then
    `summary` carries no `scope` key.

    `summary['exposure']` is ALWAYS emitted and is a DIFFERENT number: the
    activity split over the placements this plan would actually create, which
    is what phase 6's stub warning has to quote. See the comment at its
    construction for why the two cannot be substituted for one another.
    """
    if flows is not None and not app_id:
        raise ValueError('build_plan needs app_id to emit a command; the '
                         'inventory file carries it as its "app" key')
    groups = group_by_paywall(placements)
    by_id = {p['id']: p for p in placements}
    taken = {p.get('developer_id') for p in placements if p.get('developer_id')}
    rows = []
    for placement_id in sorted({pid for refs in groups.values() for pid, _ in refs}):
        placement = by_id[placement_id]
        audiences = [normalize_audience(a) for a in (placement.get('audiences') or [])]
        migratable = [a for a in audiences if a['content_type'] == CONTENT_PAYWALL]
        proposed = propose_developer_id(placement['developer_id'], taken, suffix=suffix)
        taken.add(proposed)
        row = {
            'source_placement_id': placement_id,
            'source_developer_id': placement['developer_id'],
            'title': placement.get('title') or placement['developer_id'],
            'proposed_developer_id': proposed,
            'audiences': [{'paywall_id': a['paywall_id'],
                           'segment_ids': list(a.get('segment_ids') or []),
                           'priority': a.get('priority', 0)} for a in migratable],
        }
        if flows is not None:
            missing = sorted({a['paywall_id'] for a in migratable
                              if not flows.get(a['paywall_id'])})
            if missing:
                row['missing_flows'] = missing
                row['command_unavailable'] = (
                    'no published flow recorded for ' + ', '.join(missing) +
                    ' -- finish phase 5 for those paywalls, then re-run plan')
            else:
                row['command'] = build_create_command(
                    app_id, row['title'], proposed,
                    [to_flow_audience(a, flows[a['paywall_id']]) for a in migratable])
        rows.append(row)
    summary = migratable_summary(placements)
    if scope is not None:
        summary['scope'] = scope
    # EXPOSURE IS COMPUTED OVER THE PLAN ROWS, and it is not the same number as
    # `scope`. `scope` partitions the whole `list`; these rows exclude every
    # already-flow and every empty placement, so on a 3-row account whose
    # placements are all active, `scope.active` is 3 and the rows are 1. Phase 6
    # names the live exposure a stub creates, so it must read THIS -- reading
    # `scope` there overstates it, which defeats the point of replacing a blind
    # acknowledgment with a number.
    exposed = partition_by_activity(by_id[r['source_placement_id']] for r in rows)
    if sum(len(v) for v in exposed.values()) != len(rows):
        # INTERNAL: `exposed` was built from `rows` a line above, both local.
        # A mismatch means phase 6 would quote an exposure count that does not
        # describe the placements being created.
        raise InternalError(
            f'exposure partitioned {sum(len(v) for v in exposed.values())} of '
            f'{len(rows)} plan rows; the stub exposure count would be wrong')
    summary['exposure'] = {
        'placements': len(rows),
        ACTIVE: len(exposed[ACTIVE]),
        INACTIVE: len(exposed[INACTIVE]),
        UNKNOWN: len(exposed[UNKNOWN]),
        'status_readable': bool(exposed[ACTIVE] or exposed[INACTIVE]),
    }
    return {
        'summary': summary,
        'flows_needed': [{'paywall_id': pw, 'used_by': sorted({pid for pid, _ in refs})}
                         for pw, refs in sorted(groups.items())],
        'placements': rows,
    }


def _read_inventory(path):
    """Load and validate the inventory file `plan` needs.

    Returns (body, None) on success or (None, error_message) on any
    input/IO problem -- never raises, so `main` can report one clear line
    and exit 2 instead of a traceback.

    THE PER-ROW VALIDATION IS WHAT KEEPS EXIT 3 HONEST. `plan` subscripts
    `developer_id` and `id` directly, so a hand-edited or truncated file used
    to reach the catch-all and be reported as "a bug in migrate.py, your
    inventory may be fine" -- actively misdirecting the one person who could
    fix it. An exit-code split is only worth having if the split is real, so
    every shape `plan` requires is checked HERE, at exit 2, with the row
    index named. Exit 3 is then left meaning what it says.

    Deliberately shallow: it checks the fields `plan` will subscript and no
    more. `audiences` entries are left to `normalize_audience`, which already
    raises a message naming the offending entry.
    """
    p = pathlib.Path(path)
    try:
        text = p.read_text()
    except OSError as exc:
        return None, f'could not read {path}: {exc.strerror or exc}'
    try:
        body = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, f'{path} is not valid JSON: {exc}'
    if not isinstance(body, dict) or not isinstance(body.get('placements'), list):
        return None, f'{path} has no \'placements\' list'
    for index, row in enumerate(body['placements']):
        where = f'{path}: placements[{index}]'
        if not isinstance(row, dict):
            return None, (f'{where} is a {type(row).__name__}, not a placement '
                          'object; re-run inventory to regenerate the file')
        for field in ('id', 'developer_id'):
            value = row.get(field)
            if not isinstance(value, str) or not value:
                return None, (
                    f'{where} has no usable {field!r} (got {value!r}); every '
                    'placement needs one, and `plan` cannot propose an id '
                    'without it. Re-run inventory to regenerate the file.')
        if 'audiences' in row and not isinstance(row['audiences'], list):
            return None, (f'{where} has an \'audiences\' that is a '
                          f'{type(row["audiences"]).__name__}, not a list')
        for spot, entry in enumerate(row.get('audiences') or []):
            problem = _audience_problem(entry)
            if problem:
                return None, (f'{where} ({row["developer_id"]!r}) '
                              f'audiences[{spot}]: {problem}')
    return body, None


def _audience_problem(entry):
    """A one-line reason this audience entry is unusable, or None.

    THE ID CHECK IS THE POINT, and it is a hole `normalize_audience` cannot
    close on its own: that function RETURNS EARLY when `content_type` is
    already declared, so `{'content_type': 'paywall', 'priority': 0}` passes
    it and then dies on `entry['paywall_id']` in `group_by_paywall`. Declared
    type and present id are two separate facts and only the first was ever
    checked.

    `paywall_id` is the one this module subscripts; `flow_id` is required
    because it is the content reference every write needs, so an entry
    lacking it is malformed for the same reason even though nothing here
    reads it.
    """
    if not isinstance(entry, dict):
        return (f'is a {type(entry).__name__}, not an audience object; re-run '
                'inventory to regenerate the file')
    try:
        kind = normalize_audience(entry)['content_type']
    except (TypeError, ValueError) as exc:
        return str(exc)
    field = 'paywall_id' if kind == CONTENT_PAYWALL else 'flow_id'
    value = entry.get(field)
    if not isinstance(value, str) or not value:
        return (f'declares content_type {kind!r} but has no usable {field!r} '
                f'(got {value!r}); a declared type and a present id are two '
                'separate facts, and this entry has only the first')
    # segment_ids IS THE MOST IMPORTANT CHECK IN THIS FUNCTION, and not because
    # of the crash. `to_flow_audience` does `list(src.get('segment_ids') or [])`,
    # so an int raises TypeError -- noisy, recoverable -- but a STRING is
    # iterable, and "ab" becomes ['a','b'] silently. That is corrupted targeting
    # written verbatim onto a placement that cannot be deleted, arriving as a
    # clean-looking plan that every gate passes. A crash is recoverable; a wrong
    # audience on a permanent placement is not.
    segments = entry.get('segment_ids')
    if segments is not None:
        if isinstance(segments, str) or not isinstance(segments, list):
            return (f'has a {type(segments).__name__} segment_ids ({segments!r}); '
                    'it must be a list. A string would be silently spread into '
                    "one segment per CHARACTER -- 'ab' becomes ['a', 'b'] -- and "
                    'written as the targeting of a placement that cannot be '
                    'deleted')
        # `isinstance` repeated rather than relying on the branch above having
        # returned. Two sequential lines in one function is exactly the coupling
        # this module keeps getting wrong -- guard the type where you use the
        # value, not once at the top and never again.
        bad = [s for s in segments if not isinstance(s, str) or not s] \
            if isinstance(segments, list) else []
        if bad:
            return (f'has a segment_ids entry that is not a segment id '
                    f'({bad[0]!r}); every entry must be a non-empty string, '
                    'because this array is the targeting and it is carried '
                    'over verbatim')
    return None


def _read_flows(path):
    """Load the phase-5 ledger: a JSON object of `paywall_id -> flow_id`.

    Same contract as `_read_inventory` -- returns (mapping, None) or
    (None, error_message) and never raises. The file is written by the run
    itself, one line per flow that reached `published`, so a truncated or
    half-written file is a real possibility rather than a hypothetical.
    """
    p = pathlib.Path(path)
    try:
        text = p.read_text()
    except OSError as exc:
        return None, f'could not read {path}: {exc.strerror or exc}'
    try:
        body = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, f'{path} is not valid JSON: {exc}'
    if not isinstance(body, dict):
        return None, (f'{path} must be a JSON object mapping paywall_id -> '
                      f'flow_id, got {type(body).__name__}')
    bad = sorted(k for k, v in body.items() if not isinstance(v, str) or not v)
    if bad:
        return None, (f'{path} maps {bad[0]!r} to something that is not a flow id; '
                      'every value must be a non-empty flow id string')
    return body, None


def main(argv=None):
    import argparse
    import sys
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='cmd', required=True)

    inv = sub.add_parser('inventory', help='read every placement and its audiences')
    inv.add_argument('--app', required=True)
    inv.add_argument('--adapty', default='adapty', help='how to invoke the CLI')
    inv.add_argument('--page-size', type=int, default=MAX_PAGE_SIZE)
    inv.add_argument('--out', required=True)
    inv.add_argument('--scope', choices=SCOPES, default=SCOPE_ALL,
                     help='which placements to spend a per-placement `get` on. '
                          '`active` keeps only is_active: true, which is the '
                          'saving -- the filter runs on the `list` result, '
                          'before the GETs. Defaults to `all` so that an '
                          'unscoped call can never hide work; an all-unknown '
                          'account falls back to `all` and says so, because '
                          'an absent is_active means unknown, not false.')

    pl = sub.add_parser('plan', help='group by paywall and propose placement ids')
    pl.add_argument('--inventory', required=True)
    pl.add_argument('--suffix', default='-flow')
    pl.add_argument('--flows', help='phase-5 ledger (paywall_id -> flow_id JSON); '
                                    'with it, every row gains the exact `placements '
                                    'create` argv as `command`')

    args = parser.parse_args(argv)
    # THE CATCH-ALL IS EXIT 2, AND EXIT 3 IS OPT-IN. See the module docstring for
    # why: as the catch-all, 3 asserted "this is a bug in migrate.py, your inventory
    # may be fine" about every failure nobody had classified -- and three attempts to
    # enumerate those failures each left holes, so the tool kept telling users their
    # file was fine when their file was the problem.
    #
    # Inverted, an unguarded site produces a message that is vague but TRUE. The
    # confident false claim now exists only where someone wrote `raise
    # InternalError`, which is a line a reviewer can find and question.
    #
    # The 4-line traceback TAIL stays on both paths: it is what makes any of this
    # debuggable, and only an *unhandled* traceback is the failure.
    def tail():
        import traceback
        for ln in traceback.format_exc().rstrip().splitlines()[-4:]:
            print(f'  | {ln}', file=sys.stderr)

    try:
        return _run(args)
    except InternalError as exc:
        # The ONLY route to 3. Reached only from a site that named its invariant,
        # so this is the one place the strong claim about the input is earned.
        print(f'TOOL ERROR  internal invariant violated: {exc}', file=sys.stderr)
        print('This is a bug in migrate.py. Your input is almost certainly fine -- '
              'do not start editing your files to appease it. Please report it, with '
              'the command you ran. Traceback:', file=sys.stderr)
        tail()
        return 3
    except CliError as exc:
        print(f'the adapty CLI or its response was unusable: {exc}', file=sys.stderr)
        return 2
    except Exception as exc:                              # noqa: BLE001 - breadth is the point
        # Deliberately says it does not know. An unclassified failure is UNKNOWN,
        # and the honest report of unknown is 2.
        print(f'FAILED  {type(exc).__name__}: {exc}', file=sys.stderr)
        print('This failure was not classified, so the cause is unknown: it may be '
              'something in your input that this tool does not check for, or it may '
              'be a bug here. Check the values named above against your file first. '
              'Traceback:', file=sys.stderr)
        tail()
        return 2

def _run(args):
    import sys
    if args.cmd == 'inventory':
        # A caller flag, so it is checked here where the flag's name is known.
        # `paginate` also refuses it, but its ValueError names `page_size`, its
        # own parameter, which is not what the agent typed.
        if not 1 <= args.page_size <= MAX_PAGE_SIZE:
            print(f'--page-size must be between 1 and {MAX_PAGE_SIZE}, got '
                  f'{args.page_size}; the API caps a page at {MAX_PAGE_SIZE} '
                  'rows, so a larger value cannot be served', file=sys.stderr)
            return 2
        summaries = fetch_placements(args.adapty, args.app, page_size=args.page_size)
        # The filter runs HERE, on the `list` result, and not after the GET loop:
        # spending 150 GETs and then discarding 120 of them buys nothing.
        selected, scope = select_scope(summaries, args.scope)
        details = fetch_details(args.adapty, args.app, selected)
        payload = {'app': args.app, 'scope': scope, 'placements': details}
        try:
            pathlib.Path(args.out).write_text(json.dumps(payload, indent=2))
        except OSError as exc:
            print(f'could not write {args.out}: {exc.strerror or exc}', file=sys.stderr)
            return 2
        print(f'{len(details)} placement(s) read -> {args.out}')
        print(describe_scope(scope))
        return 0

    body, error = _read_inventory(args.inventory)
    if error:
        print(error, file=sys.stderr)
        return 2
    flows = None
    if args.flows:
        flows, error = _read_flows(args.flows)
        if error:
            print(error, file=sys.stderr)
            return 2
        if not body.get('app'):
            print(f'{args.inventory} has no \'app\' id, so `placements create` argv '
                  'cannot be built; re-run inventory to regenerate it', file=sys.stderr)
            return 2
    scope = body.get('scope') if isinstance(body.get('scope'), dict) else None
    print(json.dumps(build_plan(body['placements'], suffix=args.suffix,
                                flows=flows, app_id=body.get('app'),
                                scope=scope), indent=2))
    # On STDERR, because plan's stdout is JSON and is routinely redirected to a
    # file. A run that pipes the plan away must still see what was withheld.
    if scope:
        print(describe_scope(scope), file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

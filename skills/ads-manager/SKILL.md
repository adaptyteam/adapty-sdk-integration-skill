---
name: ads-manager
description: Use when managing Apple Search Ads through the Adapty CLI — reading campaign, ad group, keyword or ad performance, changing bids or budgets, adding or pausing keywords, launching or pausing a campaign, harvesting search terms, or setting up rule-based ad automations.
---

# Apple Search Ads through the Adapty CLI

Reads and `automations run --dry-run` cost nothing. Every other `asa` command reaches Apple
within seconds and spends real money, and nothing it creates can be deleted or undone.

Open the reference a workflow names before running its commands:

- `references/asa-management.md` — campaigns, ad groups, ads, keywords, negative keywords,
  product pages, creatives, automations.
- `references/asa-metrics.md` — `metrics`, `metrics overview`, `search-terms list`,
  `competitors summary`.

## The CLI

**Resolve `$ADAPTY` once, before your first `asa` call, and use it for every command you run.** A
global `adapty` is frequently old — the `asa` topic ships in **0.4.0**, and an older install answers
every command in this skill with `unknown command`, which reads like the command does not exist
rather than like a stale CLI:

```bash
adapty --version                                   # >= 0.4.0 ?  ADAPTY="adapty", done
npm i -g adapty@latest >/dev/null 2>&1 \
  && ADAPTY="adapty" \
  || ADAPTY="npx --yes adapty@latest"              # fallback: prefix not writable
```

**Install once; do not wrap every call in `npx`.** The wrapper costs ~1 s *per call* against 0.07 s
installed, and an optimization pass makes dozens of calls. Where the global prefix is not writable
the `npx` form still works, and there `--yes` is not optional: without it npx stops to ask
permission to install, and a headless run has nobody to answer.

**Writing a command out for the user? Expand it to a literal `adapty`.** Their shell has no
`$ADAPTY`. Same split as `--yes` below — what you run carries the variable, what they run carries
the command name.

**In `zsh`, the macOS default, a multi-word `$ADAPTY` is not split into words**, so the command
fails with `command not found: npx --yes adapty@latest`. Run `setopt shwordsplit` once in the same
shell, or write `npx --yes adapty@latest` out in full. That error is a shell problem, never evidence
that the CLI or the command is missing.

Declare an `asa` command unavailable only after `npx --yes adapty@latest` lacks it — never from a
version number you read somewhere.

## Account surface

- `$ADAPTY asa whoami` — company, how access was granted, Apple connection state. Run it first.
- `$ADAPTY asa connect [--no-wait]` — prints the Apple authorization link and waits; `--no-wait`
  returns immediately.
- `$ADAPTY asa orgs list` — ASA organizations. Each row carries two identifiers, not
  interchangeable: `internal_id`, the UUID `--org` takes on `campaigns create` and
  `--campaign-group` takes on the lists that accept scope filters, and `org_id`, Apple's numeric id,
  which both reject. `--org` itself exists only on `campaigns create`; no list accepts it.
- `$ADAPTY asa apps list` — apps promoted in Apple Search Ads. Each row carries two identifiers,
  not interchangeable: Apple's numeric adam-id (`--adam-id`) and the ASA app UUID (`--app`).
- Those two and `automations list` take pagination only — no scope filters exist.
- Scope is the token's company. No `asa` command takes `--app` to select scope — `--app` is a
  list filter only.
- `402 ads_manager_subscription_required` — no Ads Manager subscription. `404` — not theirs, or
  does not exist.
- `--json` for machine-readable output on reads; a write under `--json` refuses and exits `2`.
  `--page` (default `1`), `--page-size` (default `100`, max `1000`) on every list — prefer one big
  page to a pagination loop.
- `ADAPTY_ASA_API_URL` overrides the ASA base URL, independently of `ADAPTY_API_URL`.

## The two templates

Fill every slot. A slot you cannot fill from a read is one you ask about, not one you drop.

```
$ADAPTY asa <topic> list --<filter-from-that-list-s-matrix-row> <id-from-a-previous-list> [--status <enum>]
$ADAPTY asa <topic> <create|update|add> [<id>] <field flags> --idempotency-key <key>
```

**The scope filter is a required slot, and the matrix is the only place it comes from** — read that
list's own row in `references/asa-management.md`, `## Scope filters`, and fill the slot from it. A
flag you saw on a create command, or on a different list, is not a filter for this one: `--org`
belongs to `campaigns create`, and the equivalent on the lists that take scope filters at all is
`--campaign-group`. Required on a
session's first list as much as its fifth — a filter changes the query the server ranks, while page
size only changes how much of the wrong answer you see.

**Two entities the user named separately are two lookups.** "The best-performing campaign" and "the
brand ad group" are not parent and child unless the user said so. Resolve each by its own name
(`ad-groups list --search <name>`), and never scope one lookup with an id produced by resolving the
other — that filter asserts a relationship the user did not state, and the write that follows lands
somewhere plausible and wrong without erroring. More than one match is where you ask, not pick.

**`--idempotency-key` is a required slot**, distinct per write in a chain and per batch within a
write. The CLI's auto key covers a network retry inside one invocation, not the person who
re-runs your create step after an ambiguous result — new invocation, fresh key, second campaign.
That, plus `422 cli_idempotency_key_reuse` and `409 cli_idempotency_in_progress`:
`references/asa-management.md`, `## Writes and idempotency`.

**`--yes` is not in the template, because whether it belongs depends on who runs the command.**

- **The user runs it** — you are writing commands out for them. Omit `--yes`. At their terminal the
  CLI prints the exact request body and waits; that prompt is their confirmation, and `--yes` is the
  one flag that deletes it. Nothing in your surrounding text puts it back, so no warning, STOP
  block, or stated assumption substitutes for leaving the flag off.
- **You run it** — in this session. Ask, get an explicit yes, then append `--yes` to the command you
  run.

`metrics`, `metrics overview`, `search-terms list` and `competitors summary` share **2 concurrent
queries per company**: `429 cli_analytics_busy` is a full pool, `429 cli_rate_limit_exceeded` a
full window, and
`429 cli_cooldown_active` the escalating **5m → 30m → 3h** lockout. See
`references/asa-metrics.md`, `## The analytics pool`.

## One question, one call

The server aggregates and the server ranks. Decide the single call that answers the question before
running anything; the metrics budget is **5 calls per minute** (`references/asa-metrics.md`).

- Totals: one `metrics overview` call.
- Best or worst N: one `metrics --order-by <metric> --page-size N` call, `--order asc` for worst.
- Trend or period comparison: one call — a per-period series already contains both periods.
- Counting entities: no metrics call at all. Any list with `--page-size 1` returns
  `meta.pagination.count`.
- `metrics` and `metrics overview` take no scope filters at all. You narrow by entity level and
  window, then match the returned rows against the ids from a scoped list.
- A window too wide for its bucket is cured by coarsening, never by splitting. Caps: **90 days** at
  day grain or with no period grouping, **180** by week, **365** by month and coarser. A year of
  data is one call at `--group-by month` (or `--period-unit month`), not four 90-day calls.

Never sum pages client-side, never call once per period, and never add a comparison the user did not
ask for — propose that in the answer instead.

## Never

- **Never settle a superlative yourself.** "Best-performing", "losing", "terrible ROAS" are
  business definitions, not query results. Name the metric and the window, get the user's yes on
  that definition, then write.
- **Never write without naming the change in chat first** — which campaign, which budget, how
  many keywords.
- **Never put more than 15 keywords in one `keywords add` or `negative-keywords add` call.** The
  cap is 100; the practice is 15.
- **Never loop on a `429`.** The CLI already waited the exact `Retry-After` and retried once, so a
  `429` that reaches you means the budget is genuinely gone. Cut the number of calls, or tell the
  user when to retry.
- **Never guess or probe a metric name.** The vocabulary is in `references/asa-metrics.md`. A wrong
  name fails listing every valid one, so a typo costs one call — spending a call to see what works
  is the failure. Cohort metrics rank by their expanded names: `--order-by gross_roas`, not
  `--order-by roas`.
- **Never invent an id, adam-id, budget or bid.** Read it from the matching list, or ask.
- **Never put `--yes` on a command the user will run.** It deletes the preview they would have read.
  `--yes` belongs only on a command you run yourself, after an explicit yes.
- **Never write a teardown.** No delete exists in the `asa` topic and there is no undo;
  `--status PAUSED` is the only stop.

## Rationalizations

| What the agent told itself | What is actually true |
|---|---|
| "40 keywords is under the CLI's 100-per-call batch limit, so this is one call, not a loop." | Under the cap is not the same as safe. Nine rejected rows inside a 40-item response is a repair job; inside a 15-item call it is a re-run. |
| "I'd use ROAS over a trailing window as the default definition of "best-performing," and ask the user to confirm/override it before step 5 — but here is the command that answers it." | Handing over the command does not obtain the sign-off you just said had to come first. If the definition needs confirming, stop at the definition. |

## Red Flags — STOP

- A `list` with no scope filter — including the first one, and the one you are "only glancing at"
- A scope filter on `orgs list`, `apps list` or `automations list`
- A filter you did not read off that list's own row in the matrix — a create flag such as `--org`,
  or another list's filter, is not one
- `--yes` on a command you are handing to the user — it deletes the preview they were going to read
- A lookup scoped by an id that came from resolving a different entity the user named separately
- A create in a chain of dependent creates with no `--idempotency-key` pinned
- More than 15 keywords in one call
- A write whose target you picked by your own definition of "best", "losing" or "terrible"
- `--order-by-day` with no matching `--by-days` window in the same call
- You stated a rule, and three commands later are making a silent exception to it

Observed in CLI-side sessions rather than in this skill's own baseline:

- Looping `--page 1..4` to build a total, instead of one `overview` call or one big page
- Spending a call to discover which metric names are valid
- Adding a period comparison the user did not ask for
- Retrying a `429` after a guessed `sleep` instead of the `Retry-After` value

**All of these mean: stop, read first, ask.**

## Workflows

**1. Orient.** `whoami` → `connect` if Apple is unlinked → `orgs list` → `apps list`.
Prerequisite for everything below. → `references/asa-management.md`,
`## Account and discovery`.

**2. Report performance.** Totals and any trend take the first shape; best or worst N takes the
second, with `--order asc` for worst. Dates are required on both — without them the command exits
before it reaches Apple. Counting needs no metrics call: any list at `--page-size 1` carries
`meta.pagination.count`. `--by-days` takes max **16 windows per call**, and `--order-by-day` may
only name one of those values. → `references/asa-metrics.md`, `## Cohort windows`.

```
$ADAPTY asa metrics overview --entity <level> --date-from <YYYY-MM-DD> --date-to <YYYY-MM-DD> [--period-unit <bucket>]
$ADAPTY asa metrics --entity <ad|ad-group|campaign|keyword> --date-from <YYYY-MM-DD> --date-to <YYYY-MM-DD> --order-by <metric> --page-size <n>
```

**3. Launch a campaign.** Read `orgs list` → `--org` and `apps list` → `--adam-id` first; then
each create consumes an id the previous printed. Neither the order nor any key is optional.
Mint `<run>` once per launch, so a second launch cannot collide. Create the campaign `PAUSED`,
verify the structure, then enable it with workflow 6 — nothing spends until you do. Set
`--match-type` yourself: it defaults to `BROAD`, which is the widest, most expensive targeting. →
`references/asa-management.md`, `## Writes and idempotency`.

```
$ADAPTY asa campaigns create --org <id> --adam-id <adam-id> --name <name> --country <country-code> --daily-budget <amount> --status PAUSED --idempotency-key <run>-camp
$ADAPTY asa ad-groups create --campaign <id> --name <name> --default-bid <amount> --idempotency-key <run>-ag
$ADAPTY asa creatives list --app <app-uuid>   # → --creative-id; no creatives create exists
$ADAPTY asa ads create --ad-group <id> --creative-id <id> --name <name> --idempotency-key <run>-ad
$ADAPTY asa keywords add --ad-group <id> --text <keyword> --match-type <EXACT|BROAD> --idempotency-key <run>-kw-1   # ≤15 per call, fresh key per batch
```

**4. Harvest keywords.** Read `search-terms list --ad-group <id> --date-from <YYYY-MM-DD>
--date-to <YYYY-MM-DD>` (dates default to today, so pass them), then
promote converting terms with `keywords add --ad-group <id>` and block wasteful ones with
`negative-keywords add --ad-group <id>` — 15 per call, own key per call. →
`references/asa-metrics.md`, `## The analytics pool`, and `references/asa-management.md`.

**5. Optimization pass.** Read `metrics --entity keyword --date-from <YYYY-MM-DD> --date-to
<YYYY-MM-DD> --by-days 7 --by-days 90 --order-by gross_roas --order-by-day 90` — `--order asc` asks
that same call for the losers instead of the winners — and `keywords list --ad-group <id> --status
ACTIVE` for ids. Get the user's
cutoff before any write. Then `keywords update <ids> --bid <amount>` on winners,
`keywords update <ids> --status PAUSED` on losers, `campaigns update <id> --daily-budget <n>` to
shift spend — each with its own `--idempotency-key`. Confirm the budget separately from the
bids; separate decisions. → `references/asa-metrics.md`, `## Cohort windows`, and
`references/asa-management.md`.

**6. Pause or resume.** Campaigns, ad groups, ads:
`update <id> --status ENABLED|PAUSED --idempotency-key <key>`. Keywords:
`update <id> [<id>…] --status ACTIVE|PAUSED --idempotency-key <key>`. The keyword enum differs
from every other entity's, and there is no `DISABLED` anywhere in the surface. Ids come from a
scoped list first. → `references/asa-management.md`, `## Status`.

**7. Custom product page → ad.** `product-pages sync [--adam-id <adam-id>] --idempotency-key <key>`
— a write, queued rather than awaited. Then `product-pages list --app <app-uuid>` →
`creatives list --app <app-uuid>` →
`ads create --ad-group <id> --creative-id <id> --name <name> --idempotency-key <key>`. →
`references/asa-management.md`.

**8. Diagnose a dead ad.** `ads get <id>`, read `serving_state_reasons`; if that does not
explain it, walk up to `ad-groups get <id>` status, then `campaigns get <id>` status and daily
budget. All reads. → `references/asa-management.md`.

**9. Rule automations.** `automations create --file rule.json --idempotency-key <key>` →
`automations run <id> --dry-run` → `automations runs <id>` to read what it would have done →
`automations update <id> --start`, only after the user has seen that outcome. Dry-run every rule
touching a bid or a budget. → `references/asa-management.md`.

**10. Competitor check.** `competitors summary --app-ids <adam-id>,<adam-id>` — **1–5** Apple
App Store IDs. Last full month, every country; no period or country flags exist. Read-only, shares
the analytics pool, slow on a cold cache. → `references/asa-metrics.md`.

## Anything not covered here

1. This file and its two references are the source of truth for the `asa` surface.
2. `$ADAPTY asa <topic> <command> --help` — exact flag syntax for the installed version.
3. The CLI repo, https://github.com/adaptyteam/adapty-cli (default branch): `README.md`, then
   `skills/adapty-cli/references/cli-commands.md` — both can lag the installed CLI — then
   `src/commands/asa/**`, where a command's own `static flags` declaration outranks any table and
   settles a disagreement between prose and commands.

Do not guess a flag, a command, or a URL path. If none of the three confirms it, say so.

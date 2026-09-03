# The placement and publish surface, as measured

Every fact here was measured **2026-09-03** and names the environment it came from. Two
environments, and they disagree — which is the whole reason this file exists:

- **prod** — `adapty` 0.8.3-beta.1 against the default API.
- **the pod** — the same CLI with `ADAPTY_API_URL` pointed at the MR !13221 environment
  (`dashboard-manual-mr-13221-production.manual.adpinfra.dev/api/v1/developer`, over https),
  which has the placement-audience union deployed. **The pod is backed by production data** —
  same app UUIDs, same `public_live_` SDK keys — so a write through it is a real write. Every
  test below is a read or a rejected write except the one probe flow noted at the end.

Error strings are quoted exactly. An agent routes on them, so a paraphrase here is a bug.

## Capability state by environment

| Operation | prod | pod (!13221) |
|---|---|---|
| `flows publish` | `http_404` | route works — `Flow has no current version.` on a config-less flow |
| `flows update --name` | `Method "PUT" not allowed` (`method_not_allowed`) | not retested |
| flow audience on `placements create` | `audiences.0.paywall_id: Field required` | accepted; a draft flow refused (below) |
| flow audience on `placements update` | `audiences.0.paywall_id: Field required` | **`Placement type can not be changed.`** (`validation_error`) |
| `placements get` audiences | **omits** `content_type` | **includes** `content_type` |
| `is_active` on a placement | **absent** | **absent** — declared in the source at `!13221 @ d0b878cb`, not yet released |

**None of ADP-6502 is live in production.** So the skill probes rather than assumes, and it
degrades on those exact error shapes. `audiences.0.paywall_id: Field required` in response to a
flow audience is the API rejecting the *union* — the server still models an audience as
paywall-only — and it is not a malformed request.

**The publish gate, observed on the pod.** `placements create` naming a flow whose status is
`draft`:

```
ApiError: Flow must be published before placing in a placement.
Code: validation_error
```

That is the ticket's `FlowNotPublishedError`, reached on the **create** path. On the *update* path
the type check fires first, so it is unreachable there. Hence the phase ordering: publish, poll
until `published`, then create the placement.

**`flows publish` is asynchronous.** Success logs `Publishing started — status: publishing.` — the
status is `publishing`, never `published`. A run that reports the flow as live off that response is
reporting a state nobody observed. On a 400 (`validation_error`) it exits **1** with remediation
links, one of which is https://adapty.io/docs/flow-generator-skill.

## Why every migration is a create

**A placement's content type cannot be changed after creation.** On the pod, which accepts flow
audiences on `create`:

```
$ placements update --app <APP> <PLACEMENT> --title Main --developer-id main \
    --audiences '[{"content_type":"flow","flow_id":"<FLOW>","segment_ids":[],"priority":0}]'
ApiError: Placement type can not be changed.
Code: validation_error
```

**This is not a deployment gap.** The pod has the union deployed and still refuses. So in-place
conversion is impossible at the backend, not merely unimplemented in the CLI, and every "migrate"
operation is a `placements create`.

Two consequences worth stating separately:

- **ADP-6502's own QA case C7 cannot pass.** The ticket lists *"convert an existing placement to a
  flow"* via `placements update` as an expected success. Report that to the CLI/API team; do not
  design around it as though it works.
- **A wrongly-created placement is permanent.** The docs, verbatim: *"Placement IDs are unique
  across every placement in the app, whatever the type, so the same ID can't serve a flow in one
  place and a paywall in another."* ([placements.md](https://adapty.io/docs/placements.md)) So a
  new flow placement cannot reuse the paywall placement's ID, and placement delete is out of
  scope — there is no undo for a created placement. Every proposed ID is pre-checked against
  `placements list` and approved before anything is created.

## Pagination

From `paginationFlags`, read off the flag declaration rather than the prose docs:

| | |
|---|---|
| `--page` | default **1** |
| `--page-size` | default **20**, max **100** |
| sent as | `page[number]` / `page[size]` |
| response carries | `meta.pagination {count, page, pages}` |

**The default of 20 is the trap.** One `placements list` call and a report of its length
under-reports the 150-placement app below by 130, with nothing in the output saying so —
`meta.pagination`
is there to be read, and a run that ignores it looks exactly like a run on a small app.
`migrate.py`'s `paginate()` owns this mechanically: it reads `pages` from page 1 and loops.

## Summary vs detail

**`placements list` returns `PlacementSummaryDTO` — `{developer_id, id, title}`, with no
`audiences`.** Only `placements get` returns `PlacementDetailDTO`, which carries `audiences?`.
There is no bulk read, so classifying N placements costs N GETs.

**`paywalls placements <paywall_id>` is un-paginated** — no `paginationFlags`, and `printList` is
called without pagination — and returns summaries only. It answers *which* placements use a
paywall; it does not carry the `segment_ids`, `priority` or `title` a write needs.

**And it is FILTERED, which limits it further than the missing fields do.** From the source
(`adapty-dashboard-api!13221 @ d0b878cb`): *"Filtered to live (state=LIVE), paywall-typed
(content_type=PAYWALL), non-deleted placements."* So the reverse index **cannot find an inactive
placement at all** — a narrow "just these paywalls" run built on it silently sees only the live
ones, which is the wrong shape for a migration that may deliberately start with the inactive
placements. It also omits `is_active` by design (see below), so it cannot report what it filtered.

Cost for a 150-placement / 192-paywall app, which settles which primitive to enumerate on:

| Route | Calls | Yields what a write needs? |
|---|---|---|
| placement-first: `placements list` paged + N×`get` | 2 + 150 = **152** | **yes** |
| paywall-first: `paywalls list` paged + M×`paywalls placements` | 2 + 192 = 194, **then still** N×`get` | no |

**Enumerate placement-first and derive the paywall grouping by grouping on `paywall_id`.** The
reverse index is worth reaching for only on a narrow "just these paywalls" run, where M is small
and a full sweep is the wrong shape.

## The publishable floor

Measured with `flows config validate` (advisory, saves nothing) against the real transform service
in **prod**, then with `flow-generator`'s `verify-config.py`:

| Config | `validate` | `verify-config.py` |
|---|---|---|
| `{"screens":[],"locales":[]}` — the CLI's **own example** | `Invalid flow input` | — |
| `{}` | `Invalid flow input` | — |
| one **empty** screen, no theme | `Generated JSON failed schema validation` | — |
| one **empty** screen, **full** theme | same | — |
| one `text`, **no theme** (903 B) | **`valid: true`** | **ERROR** `font.preset not in theme.typography: ['body']` |
| one `text` + `bg`/`ink` + `body` preset (1,160 B) | **`valid: true`** | **OK** |

Two findings.

**A screen must contain at least one element, and the theme is not required to publish.** An empty
screen fails no matter how much theme it carries, and a themed screen with one `text` passes. The
message for the empty case is the location-free `Generated JSON failed schema validation`, which
names no field — so an agent authoring its own stub rediscovers this floor by bisection, every run.

**The themeless variant passes the service and fails our own checker**, on a `body` preset the theme
does not declare. That is the documented trust order doing its job rather than a contradiction: a
clean `validate` is a floor, not a proof. The shipped `references/stub-flow.json` is the last row —
the artifact that clears **both** gates. **Its size depends on how you serialize it:** `wc -c` on the
shipped file reads **1,160** bytes (compact separators, as written), and the same document
re-serialized with `json.dumps`' default spacing reads 1,290 — which is the figure the original
measurement notes carry. Same config either way; quote the one whose measurement you mean.

## content_type is read-asymmetric

| | |
|---|---|
| prod `placements get` | **omits** `content_type` from each audience |
| pod `placements get` | **includes** it |
| every write (`create`, `update`) | **requires** it |

So a read cannot be written back unchanged. `migrate.py`'s `normalize_audience()` derives it from
whichever id field is present (`paywall_id` → `paywall`, `flow_id` → `flow`) and refuses to guess
when there is neither.

**That normalization is a pre-!13221 compatibility shim, not a permanent transform.** The pod
already returns the field, so it becomes a no-op after the merge — which is exactly why it must
accept both shapes rather than injecting unconditionally.

The CLI validates the field itself, before any request. `audienceEntryProblem` (**exit 2**, no
request sent): `content_type` is required and must be one of `{paywall, flow}`; a paywall entry
requires `paywall_id`, a flow entry requires `flow_id`. Reported as `--audiences[<i>]: <problem>`.

## `is_active` — the scope filter

**Read from the API source** — `adapty-dashboard-api!13221 @ d0b878cb` — and no longer
owner-stated. The source comment, verbatim: *"`is_active` is the placement activation state
(true=Live, false=Inactive), matching the dashboard."*

| | |
|---|---|
| shape | `is_active: true \| false` |
| declared on | **both** `PlacementSummaryDTO` and `PlacementDetailDTO`, read from `placement.is_active` |
| meaning | the **placement's activation state** — Live / Inactive, the dashboard's own toggle |
| explicitly not | traffic-derived, and not "has an audience configured" |

So `placements list` **and** `placements get` both carry it, which is what makes the pre-GET filter
a real saving rather than a hope. This supersedes the earlier owner-stated entry; the semantics are
now source-backed, and the guidance not to build finer edge behaviour than
*true = Live, false = Inactive* stands because that is all the source defines.

**Measured 2026-09-03, and still true: the field is absent in production and absent on the MR
!13221 pod**, on every placement in both. Source-confirmed semantics and deployed availability are
different facts — the code is written and not yet released — so nothing can be filtered on it today.

**`paywalls placements` OMITS `is_active` PERMANENTLY, BY DESIGN.** The source excludes it
explicitly, `model_dump(exclude={'is_active'})`, with the reason: *"these placements come from the
paywall latest-placement query, which does not annotate the activation state, so the entity would
carry the meaningless getattr default. It is exposed only on the placement list/retrieve reads,
whose queryset annotates it."*

**That retroactively justifies the `unknown` bucket, and upgrades it from defensive to required.**
`unknown` was built for a rollout gap that will close; it turns out to be the permanent shape of an
endpoint this skill uses. So the three-way partition is not a hedge against release timing that can
be simplified away once the field ships — one of our own read paths will always return placements
with no activation state, and collapsing `unknown` into `inactive` would mark every one of them
disabled. Keep the third bucket.

**The consequence that shapes `migrate.py`: absence is a THIRD state.** `select_scope` partitions
active / inactive / **unknown** and never collapses the third into the second, because on today's
API every placement is unknown — so reading absence as `false` would filter an entire account out
and report an empty migration, a silent and total failure that looks like a clean result. It is the
same class of error as reading a pre-!13221 audience with no `content_type` as having no type. An
all-unknown set under `--scope active` therefore **falls back to every row and records that it did**.

**And the withheld count is reported every run, kept alongside the count kept.** If the field's real
semantics turn out narrower than the status above, a filter would skip placements that needed
migrating and the user would never see them — so `describe_scope` produces the exclusion count from
the same code that makes the exclusion, and `plan` carries it into `summary.scope`.

**What it buys, in the mechanism's own terms.** The field is **declared on both DTOs in the API
source** and `list` costs 2 calls; the audiences are **measured** to be only on `get`, which costs
one per placement. So filtering the `list` result **before**
the GET loop turns a 150-placement app with 30 active from `2 + 150 = 152` calls into `2 + 30 = 32`.
Filtering after the loop yields a byte-identical inventory and saves nothing, which is why the scope
is an argument to `inventory` rather than something applied to its output.

**Verify on the pod the day it lands, in this order.** Is it on `list` as well as `get` — the call
saving dies if it is `get`-only. Is it a bare boolean rather than a string or a nullable. And does
`false` really mean the placement is disabled rather than untrafficked.

### If it ships `get`-only

**Keep the partition and the reporting; move the filter after the GET loop; delete the arithmetic
above.** Only the *position* of the filter depends on the field being on `list`. Three of the four
things it feeds need **activity**, not the pre-GET position:

| Consumer | Needs | Survives `get`-only? |
|---|---|---|
| the phase-4 three-way scope choice | activity | **yes** |
| the phase-6 stub exposure count | activity | **yes** |
| the rehearsal order | activity | **yes** |
| `2 + 150` → `2 + 30` | the field on `list` | **no** — the only casualty |

So `--scope` stays and keeps filtering; it just stops being a saving. Do not remove it, and do not
leave the arithmetic claim standing — a flag whose documentation promises a saving it cannot deliver
is worse than one that says plainly it only narrows the plan.

## Confirmation asymmetry

**`flows publish` has a full confirmation contract, and `placements create|update` have none.** That
is the measured asymmetry and it is stated without a theory attached: nothing here establishes what
publishing can or cannot be undone by, and there is no unpublish command to appeal to.

`confirmMutation`, which `flows publish` uses:

- `--yes` / `-y` proceeds.
- `--json` **or** a non-TTY stdin **refuses** with exit **2** — `Re-run with --yes to apply it
  without a prompt.` Fail-closed, so a headless run cannot hang.
- Otherwise it prompts `Apply? [y/N]` on **stderr**, so `--json` stdout stays parseable.
- A non-`y` answer exits **1** — `Cancelled, nothing was sent.`

`placements create` and `placements update` have **no prompt and no preview** at any verbosity.
Whatever argv you hand them is sent. And the warnings are on the wrong path: the **deprecated**
`--paywall-id` form prints two stderr warnings, including that it *"will rewrite all audiences on
this placement"*, while the **recommended** `--audiences` form prints none — even though
`placements update` requires `--title` and `--developer-id` and sets `audiences: null,
paywall_id: null` before filling one, i.e. it is a **full replace**.

Worth reporting to the CLI/API team alongside QA case C7.

## Blind spots in the reads themselves

**`placements get` SILENTLY OMITS an audience that is neither paywall nor flow.**
`PlacementDetailDTO.factory` appends only `PAYWALL` and `FLOW` entries; the source's own test
`test_factory_skips_content_that_is_neither_paywall_nor_flow` exercises it with
`PlacementContentType.AB_TEST`. So a placement carrying an A/B-test audience **reports fewer
audiences than it has**, and every count derived from that read — including this skill's — is short
by exactly the entries the DTO dropped.

**We cannot detect it, and saying so is the honest answer rather than inventing a check.** The read
is the only view we have; a placement with 3 audiences of which 1 is an A/B test is
indistinguishable from a placement with 2. Nothing in the response says an entry was skipped, so
there is no count to compare against and no flag to test. The only way to know is to look at the
placement in the dashboard.

**What follows for the migration, stated precisely.** This skill creates and never updates, so
nothing is destroyed and the source placement keeps its A/B-test audience serving. But the **new
flow placement would not carry that audience**, because the read never showed it — so the migration
is incomplete in a way the plan cannot show. Disclose it wherever audience counts are reported:
they are counts of what the API returned, not necessarily of what exists.

## What the write requires, and why we carry values verbatim

From the same source, the audience array a `placements create` must satisfy:

| Constraint | |
|---|---|
| `segment_ids` per entry | **at most one** — a `field_validator` refuses more (see the legacy trap below) |
| exactly one entry | must have `segment_ids=[]`, the default, and it must hold the **highest priority** |
| `priority` values | must be **unique** across the array |
| `segment_ids` values | must be **unique** across the array |

**This is the argument for carrying `segment_ids` and `priority` over verbatim rather than
normalising them.** A valid source placement already satisfies every row above, so copying the
targeting unchanged yields a valid target by construction — while any normalisation we invented
(renumbering priorities, reordering, filling a default) could break a constraint the source was
respecting, and would change who sees what. `to_flow_audience` therefore copies and does not think.

**The one exception, and it is the legacy trap: a multi-segment audience is READABLE and
UNWRITABLE.** The `field_validator` capping `segment_ids` at one entry is deliberately bypassed on
the read paths — `model_construct`, commented *"bypass the 1-segment cap so legacy multi-segment
rows survive read round-trips"* — so a legacy row reads back perfectly and is refused on write.
Carrying it verbatim, which is right for every other field, therefore produces an argv the API will
reject at the one irreversible command in the skill. `migrate.py` detects `len(segment_ids) > 1`,
emits **no `command`** for that placement, and reports it as work the user must resolve in the
dashboard — it does not split or drop a segment, because that is a targeting decision.

## What is still unverified

Stated as open rather than smoothed over, because the skill's phases rest on it.

- **A successful `placements create` with a published flow has not been run.** It is the one call
  the whole migration depends on. Testing it is a real production write that leaves a permanent,
  undeletable placement, so it was deferred. Unknown until then: the success payload shape, whether
  `content_type` comes back on the new placement, and whether a duplicate `developer_id` is refused
  client-side or by the backend.
- **`flows update --name` is untested on the pod** — only its prod `Method "PUT" not allowed` was
  measured.
- **Whether a `dirty` flow is attachable.** Only `published` is treated as safe.
- **Housekeeping:** probe flow `776194c6-a0ff-4074-99cc-0eabe8ccb0ec` ("ZZ ADP-6502 publish
  probe - delete me") was created in `app_finance` during this investigation. There is no
  `flows delete`, so it has to be removed from https://app.adapty.io/flows.

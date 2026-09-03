---
name: flow-audit
description: Use when a client asks whether a Flow Builder flow is ready for production, wants it audited or checked, or asks something like "did I forget anything — triggers, products, variables?", "is this ready to publish?", or "check my paywall/flow". Answers one question — is this flow safe to put in front of paying users — with a verdict and ranked findings. Read-only: never writes to a flow. Complements `flow-generator` (which owns writes) and `paywall-teardown` (which owns conversion advice).
---

# flow-audit

## What this answers

**Is this flow ready for production?** Not "here is a list of things about your flow" —
a verdict: ready, or not ready and why, backed by ranked findings that each carry a
concrete fix. A **blocker** is precisely a reason to answer no.

This skill is **read-only**. It never calls `flows config update`, `products create`, or
`flows create`. It cross-references the flow's config against the live dashboard
(catalog, access levels) to catch what an offline checker structurally cannot — a bound
product that does not exist, one with no store binding, a card whose copy claims a
period the product does not have. When the user wants something fixed, hand it to
`flow-generator`, which owns the backup, the approval gate, and the write. This skill
does not implement transforms and does not touch the config on disk beyond the working
copy it fetches to check.

## Phase 1 — resolve and authenticate

Resolve `$ADAPTY` once, exactly as `flow-generator` does:

```bash
if [ "$(printf '%s\n' "$(adapty --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+')" "0.8.0" | sort -V | head -1)" = "0.8.0" ]; then
  ADAPTY=adapty
else
  ADAPTY="npx --yes adapty@latest"
fi
$ADAPTY auth status
```

`--yes` on the npx fallback is load-bearing: without it, npx asks permission to install
an uncached package, and a headless run has nobody to answer. If `auth status` shows no
session, stop and tell the user to run `adapty auth login` — this skill cannot
authenticate for them.

Resolve the app:

```bash
$ADAPTY apps list --json
```

If the user already named the app, match it by title and skip asking. Otherwise show
the list and ask which one.

## Phase 2 — select the flow

```bash
$ADAPTY flows list --app "$APP" --json
```

Returns `{id, name, status, updated_at}` per flow — `status` alone is a finding source
(a flow sitting in `publication_failed` is worth saying out loud even before any check
runs). If the user named a flow ("audit my Havn onboarding flow"), match it by name and
skip the prompt. If they did not, show name + status for each and ask which one.

**Never audit a flow the user did not name or select.** A silent pick on the wrong flow
wastes the whole run and can mislead the user into thinking a different flow was
checked.

## Phase 3 — fetch

```bash
$ADAPTY flows config get "$FLOW" --app "$APP" --json > flow.envelope.json
python3 -c "import json; d = json.load(open('flow.envelope.json')); \
json.dump(d['config'], open('flow.config.json', 'w'))"
$ADAPTY products list --app "$APP" --json > catalog.json
```

`flows config get` returns an **envelope** — `{config, remote_configs, updated_at,
status}` — not a bare config. Every check in Phase 4 wants the bare config, so extract
`config` before running anything. `products list --json` returns `{"data": [...]}`; the
audit script accepts either that wrapper or a bare array.

The catalog fetch happens **before** the checks run, in this same phase, because every
product finding in Phase 4 is a comparison against it — a bound product absent from the
catalog can't be detected without it.

## Phase 4 — check

Three commands, in this order. The order matters: the two local checks name every
defect in one pass over the file already on disk, while `flows config validate` is a
network round trip — running it last means the local checks have already caught
everything they can before paying for a network call.

`verify-config.py` lives in the **`flow-generator`** skill directory, not this one — resolve
it there. Both skills ship in the same plugin, so it is always present in a plugin install;
`$FG` below is that skill's directory (a sibling of this one under `skills/`).

```bash
FG="$(dirname "<skill>")/flow-generator"        # sibling skill directory
python3 "$FG/references/verify-config.py" flow.config.json
python3 <skill>/references/audit-flow.py flow.config.json --catalog catalog.json \
  --report --name "$NAME" --status "$STATUS" --flow-id "$FLOW"
$ADAPTY flows config validate "$FLOW" --app "$APP" --config-file flow.config.json --json
```

If `verify-config.py` is not at that path, this skill was copied out on its own without
`flow-generator`. Say so and continue with the other two gates rather than skipping silently —
it owns checks nothing else here repeats, so its absence narrows the audit and the report must
admit that.

`verify-config.py` is `flow-generator`'s structural checker (shapes, invariants,
referential integrity) — run it and report its output, never reimplement any check it
already owns. `audit-flow.py` is this skill's own script: the six completeness families
(triggers, store compliance, products, variables, localization, placeholders). Both are
stdlib-only and take the bare config, never the envelope.

`audit-flow.py` also runs six **store-review** checks — `trial-toggle`,
`billed-amount-not-shown`, `derived-price-louder`, `no-period-disclosed`,
`trial-terms-incomplete` and `external-purchase-link` — which ask whether this paywall
carries a shape that has actually drawn a store rejection. **Their findings are
advisory: they never change the verdict.** They are `risk`/`question` only, they are
printed in their own section, and **every `question` among them is excluded from the
pending count** — `external-purchase-link` always asks one, and
`billed-amount-not-shown` degrades to one when a catalogued product's row states no
billing period, so "the one question" is two checks, not one. A store-review section
can be full and the verdict can still read a clean `READY FOR PRODUCTION` — that is
correct, not a bug. Evidence and calibration:
`references/store-review.md`.

`flows config validate` takes `--config-file`, **not** `--config` (that flag wants a
literal JSON string and fails with `Invalid --config JSON` on a file path). It also
rejects the envelope — pass the same `flow.config.json` extracted in Phase 3.

If a `product-store-gap` question fires (a product has no store binding for a store the
audit can't confirm the app ships on), **ask the user which stores they ship on** —
never guess — then re-run `audit-flow.py` with `--stores ios,android` (or whichever
subset applies). That re-run promotes any matching question to a blocker or clears it;
report the second run's verdict, not the first.

## Phase 5 — report

Print `audit-flow.py --report`'s output as the verdict block. Two gates ran alongside it
and neither gets its own section:

- **A green gate prints nothing.** `verify-config.py` returning `OK` or `validate`
  returning `{"valid": true, "issues": []}` tells a client nothing they need to act on.
- **A failing gate becomes a blocker in the list**, restated in the user's own terms —
  never pasted through as raw tool output. If `verify-config.py` warns that a `const`
  purchase has no declared product, say "this card's purchase has no product
  declaration, so the flow won't publish" — not the tool's own wording. If `validate`
  returns `valid: false`, translate its `issues[]` entries into the same blocker/fix
  shape every other finding uses.

There is no separate "gates" heading anywhere in the output. A client reading the report
should never see the names `verify-config.py`, `flows config validate`, or
`audit-flow.py` — only what they mean.

If any store-review check fired, the report carries a `STORE REVIEW — ADVISORY` section
with a **fixed disclaimer** printed under it. **Report it as printed.** Never paraphrase
the disclaimer away, and never restate a store-review risk as a blocker or as a reason
the flow is not ready — those findings are hazards, not verdicts, and the verdict line
above them already accounts for everything that gates a release. Its checks and the
reason they are advisory are in `references/store-review.md`.

**Hand the user one link alongside that section** —
`https://adapty.io/docs/prepare-your-app-for-store-review` — as the page to read next.
Every finding in the section cites its own guideline number (`App Store 3.1.1`,
`App Store 3.1.2`), which is what a developer pastes into an appeal, but a bare
guideline number sends them to a wall of policy text; that page covers what an Adapty
app actually has to get right. The link lives here, in the report instruction, rather
than inside the findings' own `fix` strings on purpose: `scripts/lint-links.mjs` walks
`.md` files only, so a URL written into `audit-flow.py` would be unlinted and would rot
silently the next time the docs are reorganised.

The report ends in `BEFORE YOU SHIP` and then, whenever at least one finding fired, a
**`WHAT TO DO NEXT`** section — printed by `audit-flow.py --report` itself, nothing
extra to do here. It routes every already-numbered finding into up to four groups by
check name, never restating a finding's own text, only pointing back at its number:
**Answer these — they change the verdict** (a `question` whose answer can turn it into
a blocker — "do you ship on Android?"), **Change in the flow — I can do these** (the
default group: something `flow-generator` can fix), **Change in the Adapty dashboard —
only you can** (a dashboard-only action, plus the unconditional placement reminder),
and **Optional** (a `risk`). Every numbered finding is guaranteed to land in the groups
its check maps to; a group with no members prints no heading, and the whole section is
silent on a clean flow.

## The verdict rule

`READY FOR PRODUCTION` only when **zero blockers fired and every open question has been
put to the user and answered**. An unanswered question is not a pass. If blockers exist,
print `NOT READY FOR PRODUCTION — n blockers: <short labels>`. If there are no blockers
but unresolved questions remain, print `READY, PENDING n CHECKS I CANNOT MAKE` and list
them. **Never certify what you could not see** — a clean run over five real sandbox
flows never printed a bare `READY FOR PRODUCTION` with no caveats, and that is the
default outcome to expect, not a bug.

## What you cannot check

State these plainly when they apply; never guess an answer for them.

- **Placement attachment.** Measured against `adapty` 0.8.1: `flows get` returns only
  `{id, name, status, updated_at}`, and flows and paywalls are separate id namespaces
  (a flow id given to `paywalls get` 404s). There is no `flows placements` command. The
  audit cannot tell whether this flow is reachable from the app at all — that is a fixed
  reminder in the report (`BEFORE YOU SHIP`), never a numbered finding, because it is
  unverifiable by design at this CLI version, not a question about this flow's data.
- **Whether the host app provides its own dismiss.** A paywall whose only action is
  `purchase` is fine if the app presents the flow modally with a system dismiss — the
  audit cannot see the host app, so this is a `question`, not a blocker, unless no
  `closeFlow`/`navigateBack` is reachable from that screen at all.
- **Why a flow is `publication_failed`.** Both gates can pass clean over the exact bytes
  of a flow sitting in that status (measured, `df730155`) — no local check explains it.
  `check_meta` turns `--status publication_failed` into its own numbered `question`
  finding — the dashboard reports the flow failed to publish, nothing local explains
  why, the Flow Builder will show the real reason — and, because it is a `question`, it
  also blocks a bare `READY FOR PRODUCTION` verdict until the user has seen it. Do not
  invent a cause.

## Handoff

When the user wants fixes made, say plainly that this skill will not write, and invoke
`flow-generator`. It owns the phase-2 backup, `diff-config.py`, `--expected-updated-at`,
the phase-5 approval gate with a before/after render, and the actual `flows config
update` call. Point it at the specific blockers by number — "fix blockers 1 and 2" is
enough context; `flow-generator` re-fetches the flow itself rather than trusting this
run's copy.

## Reference

`references/audit-flow.py` — the six-family completeness checker (stdlib only). Takes
the bare config plus the catalog JSON; `--report` prints the user-facing block, `--json`
prints raw findings, no flag prints a plain list. Exit 0 no blockers, 1 at least one
blocker, 2 usage/unreadable input. Every check is calibrated in both directions against
`tests/fixtures/` and five real flows in `app_finance` — see the script's own docstrings
for the traps each one closes; most were wrong on first contact with real data.

`references/checks.md` — per-check evidence for every completeness check: what it looks
at, its severity and why, its calibration in both directions, and the false-positive trap
it closes. Read it before changing a check.

`references/store-review.md` — the same contract for the six advisory store-review
checks: the two rejection notices verbatim with their dates, the evidence tiers, the
framing rule and why it is a rule, per-check calibration and negative-test outcomes, the
two accepted false-negative classes, the blind spots, and what was ruled out (so nobody
re-adds it from the guideline text).

## Boundaries

- **No writes, ever.** No `flows config update`, no `products create`, no `flows
  create`, no `flows delete` (there is no such command). If a fix requires changing the
  flow, that is `flow-generator`'s job.
- **Not conversion advice.** This skill answers "is it wired up", never "will it
  convert" — that is `paywall-teardown` for a paywall screen, `onboarding-teardown`
  for the sequence around it.
- **Not a render check.** The audit is a config-and-catalog question; it does not
  screenshot. A finding that genuinely needs a render (a selected-state defect, a
  scroll-behind-footer bug) is named as something `flow-generator`'s preview loop should
  catch, not guessed at here.

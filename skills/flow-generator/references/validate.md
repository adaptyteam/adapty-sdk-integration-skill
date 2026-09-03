# `flows config validate` — what it is, what it catches, what it lets through

`flows config validate` is in stable `adapty` from **0.8.0**, and its endpoint is **live in
production**. Everything below was measured against production on 2026-08-24 with `adapty@0.8.0`,
using real flows in a sandbox app.

Read this file when `validate` says no and you need to know what the message means, or when you are
about to claim something is publishable.

## Why it is worth a loop

**`validate` runs the same transform service that gates publishing** — not a local linter, and not
the JSON Schema. Its refusals come back in the transform service's own wording, and they are the
refusals that would otherwise arrive as an HTTP 422 at publish time, or as a 422 the first time
someone opens the flow on a device.

That makes it the only pre-write check the skill has that speaks for the publish gate. It saves
nothing, needs no confirmation, and does not touch the flow. Run it freely.

It is **version-agnostic where the schema check is not**: a `schemaVersion: 9` config validates
clean (measured on two v9 fixtures), so unlike `validate-with-schema.mjs` it needs no baseline.

## The one rule that changes how you use it

**The transform service stops at the first fatal, so `validate` reports exactly one error per
run — never a list.**

Measured: a config with three independent defects (an undeclared product, a dangling `groupId`,
and a `defaultLocale` naming no configured locale) returned **one** issue. Adding the third defect
changed *which* one surfaced. Fixing one and re-running surfaced the next.

Two consequences, and both are easy to get wrong:

- **One issue in the output is not one defect in the config.** Never report "one problem, fixed".
- **The only clean result is `valid: true`.** An issue list that got shorter proves nothing. Loop:
  fix, re-run on the bytes you will actually write, repeat until `valid: true`.

Because each round trip only buys you one defect, walk the [Verify](../SKILL.md#verify) list
yourself *before* the first run rather than using `validate` as a discovery loop — the list is
cheap and local, and it finds the other four defects while `validate` is still telling you about
the first.

## Reading the output

Always use `--json`. Three shapes come back:

```jsonc
{"valid": true,  "issues": []}                                     // exit 0
{"valid": false, "issues": [{"severity": "error", "message": "…",  // exit 1
                             "code": null, "path": null}]}
{"error": {"statusCode": 404, "message": "Flow does not exist."}}  // exit 1 — no `valid` field
```

**Exit 1 means "not publishable" *or* "the call failed", and only the JSON separates them.** A
missing or wrong flow id, an expired token and a genuinely broken config all exit 1. Gate on the
presence of `valid`, then on its value — an agent gating on the exit code alone reports a good
config as broken and a failed call as a defect.

`code` and `path` come back `null` on every message measured. The location, when there is one, is
inside the `message` string.

## The three message families

| Message | What it means | How much it tells you |
|---|---|---|
| `Unsupported flow input: <sentence> (<path>)` | A semantic check failed — a reference points at something that is not there | **Actionable.** The parenthesised path names the exact element, e.g. `screens["scr_x"].elements.map["el_y"].props.groupId` |
| `Generated JSON failed schema validation` | The transform produced output the SDK schema rejects | **Location-free.** You get no field and no index; bisect against your backup |
| `Invalid flow input` | The request body did not parse as a flow at all | **You sent the wrong document** — see the envelope trap below |

## Two traps in the call itself

- **It takes the bare config, not the envelope.** Piping `flows config get --json` straight in
  returns `valid: false` with `Invalid flow input` — which reads exactly like "your config is
  broken". `preview` accepts either form; `validate` does not. Pass `jq '.config'`, the same
  document `update` takes.
- **The flow must already exist.** The flow id is an existence and ownership check only: any
  config validates against any flow in the app, and an id that does not resolve returns
  `Flow does not exist.` So a config authored for a brand-new flow can only be validated after
  `flows create`.

## What it catches

Each row measured by injecting the defect into a real, previously-clean config.

| Defect | Message |
|---|---|
| A product used on a screen with no `_meta.screens[<sid>].products` entry | `… .products is missing flowProductId for product "<uuid>" (screens[…].elements.map[…].props.product)` |
| A `const` **purchase** action's product, undeclared | same message, path ending `.purchase.product` |
| `groupId` naming a group the screen does not declare | `Selectable element references unknown group "<gid>" (…props.groupId)` |
| A `navigate` action targeting a screen that is gone | `Navigate action targets unknown screen "<sid>" (…interactions[0].actions[0].payload.screen)` |
| Deleting a screen something still navigates to | same, reported at the surviving caller |
| An id in `hierarchy` with no `elements.map` entry | `Element "<id>" referenced in hierarchy but missing from element map (…)` |
| `defaultLocale` naming no configured locale | `Default locale "<code>" does not match a configured locale (defaultLocale)` |
| A locale declared in `locales[]` with no translated values | `Generated JSON failed schema validation` |
| A malformed hex colour (e.g. `#FFf`) | `Generated JSON failed schema validation` |
| An `icon` used but not declared in `_meta.icons` — **including a `custom` icon whose name is a builtin** | `Unsupported flow input: Icon "<name>" with weight "<w>" is missing from flow._meta.icons (screens[…].props.icon)` |

That last row surprised a real build and is worth stating on its own: a **`spinner`** whose
`props.icon` is `{"type": "custom", "name": "spinner1"}` — a name lifted straight out of
`component-catalog.json`, i.e. one the builder ships — is still refused until `_meta.icons`
carries an entry for it. Measured 2026-08-25: that was the only issue on an otherwise-clean
343-element config, and adding a `{"name": "spinner1", "weight": "regular", "raw": "<svg …>"}`
entry cleared it. So the Verify rule "every icon used appears in `_meta.icons` with real `raw`
SVG" has no builtin exemption, and `type: "custom"` does not mean "the runtime already has it".
Note also what the render then does with it: `config preview` drew **its own** arc spinner rather
than the authored `raw` path — the same authored-versus-bundled ambiguity
[patterns.md](patterns.md) records for icon names, so the `raw` you ship is what the device gets
and the preview cannot confirm it.

The first four are the ones that matter most in practice, because they are the ones an ordinary
transform produces: removing a screen strands a `navigate`, moving an element strands a `groupId`,
and authoring a purchase strands a product declaration.

**The declaration is checked for presence and consistency, not for correctness.** A fabricated
`flowProductId` validates clean — measured, and consistent with
[products.md](products.md) on `flowkit.predeclare()`. What fails is a product with *no* entry.

### A worked example of both rules at once

The sanitized `tests/fixtures/tabs-paywall.json` fails validate: its `const` purchase actions name
products that no `_meta.screens` block declares. Adding a declaration for the first product —
with a made-up `flowProductId` — cleared that error and surfaced **the next undeclared product**,
on a different element. One fatal per run, the fix confirmed by the error moving on.

The local check beats the round trip here: `references/verify-config.py` names **all three**
undeclared products in one pass, where `validate` would have taken three calls to reach them. That
is the whole argument for walking [Verify](../SKILL.md#verify) first.

This also corrects a narrower claim: a `const` purchase action does bind a product with no
`product` element on screen, but the flow is **not publishable** until that product is declared in
that screen's `_meta.screens[<sid>].products` too.

## What it lets through

A clean `validate` is a floor, not a proof. Every one of these passed with `valid: true`:

| Passes validate | Still caught by |
|---|---|
| `fill: "banana"` and most malformed props | the schema check (`validate-with-schema.mjs`) |
| `schemaVersion: 999` | the schema check |
| A top-level `status` / `id` on a file deliverable | `references/verify-config.py` |
| An element with no `states` key — a config the builder cannot open | `references/verify-config.py` |
| A missing `defaultLocale` | nothing — and the schema is wrong to call it required |
| A hyphen in an element id, which breaks the generated runtime script | `references/verify-config.py` (added after this row; the render still cannot show it — see [flow-schema.md](flow-schema.md#element-and-screen-ids-become-identifiers)) |
| A product id that does not exist in this app | nothing; no price on device and the purchase fails |
| Advisory warnings about silently dropped props (`verticalAlign` and friends) | nothing reachable from the CLI |

These are the reason the phase-5 device-preview callout stays load-bearing. In particular:

- **No warnings surface here.** The transform service emits `severity: warning` issues for
  properties it drops silently — the flow publishes green and the property is simply absent on
  device. A successful `validate` returned `issues: []`, not a warning list, so this channel is
  **not** reachable through the CLI. A clean validate says nothing about what will actually draw.
- **Nothing here resolves products against the app's catalog.** This follows from the trap
  already noted above — the flow id is an existence and ownership check only, so `validate`
  reasons about the document in front of it and never asks the account what exists. Measured
  against production: a paywall binding **three** product ids, every one of which returns
  `adapty_product_does_not_exist`, validated `valid: true, issues: []`. The document was
  perfectly self-consistent — `_meta.screens` declared all three with plausible
  `flowProductId`s — and every price would have been blank on device with the purchase
  failing. The same property is what lets you validate any config against any flow you own,
  so it is one property with two faces, not a bug. **`valid: true` says nothing about whether
  the products exist.** The authoring path is normally safe because products come from
  `products list`; the exposed path is a flow **grafted from another app**, where the UUIDs
  travel and the products do not (see [snippets.md](snippets.md)).

- **Publishable is not the same as it published.** A flow sitting in `publication_failed`
  validated clean. Treat `valid: true` as "the transform service has no blocking objection to this
  document", never as "publishing will succeed" and never as "the screen is right".

- **A publish that never settles is not a document problem.** The flow's status moves through
  `publishing` and the transform through `transforming` on the way to `published`. One that stays
  there indefinitely is an infrastructure failure, not a config the user can edit their way out
  of — a very large accumulated config has hung the transform before. So **do not start rewriting
  the flow**: say the status is stuck, that the document validated clean, and that this one is for
  Adapty support with the flow id. Rewriting a clean config to chase a stuck job destroys work and
  fixes nothing. A `publication_failed` status is the opposite case and *is* yours: it means the
  transform ran and objected, so re-run `validate` over the bytes and read the objection.

Say what you checked, in those terms. The gap between "publishable" and "renders correctly" is
[preview.md](preview.md), and neither closes it — only a device does.

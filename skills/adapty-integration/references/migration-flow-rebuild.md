# Migration Reference: Retiring a Hand-Built Paywall in favor of a Flow

Read this **on demand only**, when all three of these are true:

- `migrationSource` is set,
- `paywallApproach` is `flow_builder`,
- the project contains a paywall screen the app's own code renders — layout, copy, and product list
  written by hand, in the app's UI framework.

That combination is the one case where the migration does not preserve the app's UI. Everywhere else
`references/migration.md` section 4 holds: keep the source's working UI and swap the SDK underneath
it. Here the user already asked for the replacement in Phase 2, so the paywall screen itself is being
retired — but only on the terms below, and never before the flow that replaces it is live.

Platforms: iOS, Android, React Native, Flutter, Kotlin Multiplatform. Capacitor and Unity have no
Flow Builder option in Phase 2, so this file never applies to them.

---

## 1. The hard gate

**The gate is that the flow is live, not that a dashboard was involved.** `flow-generator` can
author the config and save it, and the CLI can publish it (`flows publish`) and point a placement at
it — but neither route is live on every account yet, and on this run the user is rebuilding a screen
they will want to approve for themselves. No amount of code gets you a rendering paywall until the
flow is published and placed, so that is the gate everything else queues behind — not a step you
sequence at your convenience.

Two consequences, and neither is negotiable:

- **Create no placement on a flow_builder run until the flow it points at is published.**
  `references/migration.md` section 3 already reserves the placement ID when the source's paywall
  came out of the source's own visual builder. A hand-built paywall reaches the same outcome by a
  different route: the flow needs that ID, and a **paywall** placement created on it blocks the flow
  placement with that ID permanently. So while the flow is a draft or does not exist,
  `npx adapty@latest placements create` is not a command you run at all — not for the source's
  default offering, not for one the code names, not "to have something to point the code at". Once
  the flow is published, create it as a **flow** placement on that reserved developer ID, per
  SKILL.md Phase 3 Step 5's Flow Builder path and its five preconditions; where that route is
  refused, every placement here is created in the dashboard instead, attached to its flow.
- **The paywall swap is atomic.** Fetch, presentation, purchase, and entitlement gating move to
  Adapty together, in one stage, or none of them move. Section 7 explains the specific way a partial
  swap ships an app that still builds and still locks paying users out.

## 2. Order of operations

Each step needs the one above it to have really happened, so do not start one on the promise of
another:

1. Access levels created (`references/migration.md` section 3 — one per active source entitlement).
2. **Real** products created, with real store product IDs. Deferred products (SKILL.md Phase 3
   Step 4 — IDs not in the code, or Google Play's AAB prerequisite) defer everything below, because
   a flow with no products to attach is not worth building twice.
3. Rebuild spec extracted from the existing paywall code — section 3. Do this **before** any code
   changes, while the screen is still intact and readable.
4. The flow is built, **published**, and attached to its placement — the user in the dashboard, or
   you with `flow-generator` plus `flows publish` and `placements create` where those routes are
   live. Either way the user approves the rebuilt screen first. SKILL.md Phase 3 Step 5.
5. Code swap, atomic per section 1, in the platform reference's Stage 2 Flow Builder section.
6. Checkpoint on a device: flow renders, products appear, a sandbox purchase completes, access level
   is granted.
7. Only then: delete the old paywall screen and remove the source SDK — section 6.

## 3. Extract the rebuild spec before you delete anything

The user rebuilds the screen in a visual editor, from whatever you write down. Copy, product order,
badge text, and locales live in the code you are about to delete, and `git` history is not a rebuild
brief — once the screen is gone, anything you did not record is gone with it.

Read the paywall screen and every file it pulls strings, assets, or products from. Then copy this
template into `ADAPTY_SETUP.md` under the **Rebuild as flows** heading that
`references/migration.md` section 5.3 already defines, one block per paywall screen, and fill in
every field. `not present` is a valid value; a field left out is not — a reader cannot tell an
element the screen never had from one you did not look for.

```
**Screen:** <name> — <file:line>
**Shown from:** <each entry point, file:line> → placement developer ID <id — from the source's own
  offering identifier per `references/migration.md` section 3; if the code never names one, say so
  here and treat the ID as inferred, which section 3 requires you to disclose>
**Unlocks:** <access level ID>
**Products, in display order:**
| # | Store product ID | Label as rendered | Price string as rendered | Badge | Preselected |
|---|---|---|---|---|---|
**Trial / intro offer:** <copy, verbatim, and the condition under which it renders>
**Copy, verbatim and in order:** headline · subhead · feature bullets · CTA label(s) · footnote and
  legal line
**Controls:** close (and any delay before it appears) · restore · Terms URL · Privacy URL · every
  other button or link, with what it does
**Assets:** images, video, icons — by file path · fonts — family and weight · colors — as hex ·
  dark-mode variants
**Locales:** every locale the screen ships in, and where the strings live
**Conditional rendering:** segment checks, remote-config flags, A/B branches, first-launch-only
  rules — each with its file:line
**Computed values:** every string the code calculates rather than reads — per-month price derived
  from an annual product, "save 40%", countdowns
```

**When the screen ships in more than one locale**, put the per-locale string inventory in a sibling
`ADAPTY_FLOW_SPEC.md` and link it from that heading, so the rest of the handoff stays readable. The
rest of the spec stays inline in `ADAPTY_SETUP.md`.

## 4. Check the builder's elements before you promise fidelity

Most of a paywall rebuilds cleanly, and the mapping is not guesswork — the builder's element
inventory is documented. Read `https://adapty.io/docs/builder-elements.md` plus the pages you need
from this table, and record the counterpart next to each element in the spec:

| In the hand-built screen | Builder counterpart |
|---|---|
| Tappable product cards with a selected state | `https://adapty.io/docs/flow-selectable-elements.md`, `https://adapty.io/docs/builder-element-states.md` |
| Product list and purchase button wiring | `https://adapty.io/docs/paywall-product-block.md` |
| Monthly/annual switch | `https://adapty.io/docs/builder-tabs.md`, `https://adapty.io/docs/builder-toggles.md` |
| Carousel, bottom sheet, grouped layout | `https://adapty.io/docs/builder-containers.md` |
| Urgency countdown | `https://adapty.io/docs/flow-timer.md` |
| Reviews, ratings, social proof | `https://adapty.io/docs/builder-reviews-and-testimonials.md` |
| Computed price strings ("$4.99/mo, billed annually") | `https://adapty.io/docs/onboarding-variables.md` |
| Copy or elements that appear conditionally | `https://adapty.io/docs/onboarding-element-visibility.md` |
| Values the screen reads from the app's own backend | `https://adapty.io/docs/customize-flow-with-remote-config.md` |
| Custom fonts | `https://adapty.io/docs/using-custom-fonts-in-flow-builder.md` |
| Images, video, icons; full-screen background | `https://adapty.io/docs/custom-media.md`, `https://adapty.io/docs/paywall-head-picture.md` |
| Localized strings | `https://adapty.io/docs/paywall-localization.md`, `https://adapty.io/docs/add-paywall-locale-in-adapty-paywall-builder.md` |
| Dark-mode variant | `https://adapty.io/docs/paywall-dark-mode.md` |

**An element with no counterpart is the user's decision, not your omission.** List it in the spec
under **No builder counterpart** with what it does today, and give the user the two options: ship the
flow without it, or keep this screen on a custom paywall fed by Adapty products (the `custom` path in
the platform reference's Stage 2) while other placements use flows.

If what makes the screen work is bespoke animation, interaction, or business logic that the list
above cannot reach, you are looking at the evidence `references/migration-architecture.md` row 4
weighs for keeping a custom paywall. Say so to the user and record it. Do not silently change
`paywallApproach` — that choice is theirs.

## 5. What the swap needs that a hand-built paywall never had

A flow is not a drop-in for a screen the app renders. Four things the old screen did implicitly now
need code, and all of them are checkpoint failures if missed:

- **Button actions arrive as events.** Close, restore, Terms, Privacy, and any custom button in the
  flow emit actions your code handles — they are no longer your own tap handlers. Every behavior you
  recorded under **Controls** needs a handler here: `https://adapty.io/docs/handle-paywall-actions.md`
  (iOS), `https://adapty.io/docs/android-handle-paywall-actions.md`,
  `https://adapty.io/docs/flutter-handle-paywall-actions.md`,
  `https://adapty.io/docs/react-native-handle-paywall-actions.md`,
  `https://adapty.io/docs/kmp-handle-paywall-actions.md`.
- **Purchase outcomes arrive as events too**, not as the return value of a button callback. The
  platform reference's Stage 2 Flow Builder section lists the events page for the platform.
- **Offline is no longer free.** The old screen rendered from compiled-in strings; a flow is fetched,
  so without a local fallback the paywall is blank on a cold offline launch — a regression a device
  test on wifi never shows. Set one up: `https://adapty.io/docs/fallback-flows.md`, with the
  platform side in `references/<platform>.md`.
- **Locale is now a parameter.** The old screen picked up the OS locale through the platform's own
  localization. A flow renders the locale you pass when you build its configuration, so pass the
  user's — a hardcoded `"en"` ships English to every user who had translations before. The exact call
  is in the platform reference's Stage 2.

One more thing the spec surfaces, and it is a question rather than a change: the old screen was
probably one file reused from several entry points. Placements are how a flow differs per entry
point, so the rebuild *could* give each entry point its own — but `references/migration.md`
section 3 still governs how many you create, one per offering the app actually uses, and splitting
one offering across three placements is a change to how the app monetizes, not a migration step.
Put the option to the user with the entry points you recorded, and create the extra placements only
if they ask for them.

## 6. Delete the old screen last, and only on evidence

Delete the paywall screen and its purchase code **after** the section 2 step 6 checkpoint passes on a
device: the flow rendered, products appeared, a sandbox purchase completed, the access level was
granted. Not after the code compiles, not after the flow previews correctly in the dashboard.

Then remove the source SDK and grep for its symbols, per `references/migration.md` section 4.

The screen's UI code is the only rollback that exists for a flow that renders blank in production, so
until that checkpoint passes it stays. Note in `ADAPTY_SETUP.md` that users on app versions built
before this release keep seeing the old screen, and read
`https://adapty.io/docs/migrate-to-flows.md` for the roll-out half of that problem — the page is
written for a different starting point, so take only its guidance on not disrupting users on older
versions.

## 7. If the flow cannot be built this session

Headless runs and users who will not open the dashboard now are normal. The rule is section 1's:
**no partial swap.** Concretely, on this run:

- Install and activate the Adapty SDK, wire user identification and logout, and set up the
  integrations. All of it is independent of any placement.
- **Leave the entire purchase and entitlement path on the source system**, with the source SDK still
  installed and the paywall screen untouched. Adapty does not own purchases yet, so it cannot grant
  access levels yet — repointing the app's "is premium" check at Adapty before the swap locks paying
  users out of what they bought. This is the specific way a partial swap breaks an app that still
  builds and still ships.
- Create no placement (section 1). Create access levels and products only where section 2 steps 1–2
  are genuinely satisfied.
- Extract the rebuild spec anyway (section 3) — it is the deliverable that makes the deferred work
  possible, and the code it comes from is still intact right now.

Then write the remainder into `ADAPTY_SETUP.md` as ordered, ready-to-run steps: build the flow, create
the placement in the dashboard, then the exact code edits left (fetch, presentation, purchase,
gating, action handlers), then the deletion. Say plainly that the app is shipping with two purchase
systems installed and Adapty not yet in charge, and that this is a safe pause point rather than a
finished state.

That last point is where `references/migration.md` section 4's rule — remove the source SDK, because
two initialized SDKs double-report purchases — meets this one. The files do not disagree: that rule
describes the state a migration must *finish* in, and it is exactly why the interim state here has to
be written down as unfinished rather than left for someone to discover. The source SDK stays only
until the swap it is standing in for can happen, and the handoff has to name it as the reason the
migration is not done.

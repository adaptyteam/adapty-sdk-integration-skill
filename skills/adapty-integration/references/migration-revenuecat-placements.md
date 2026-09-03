# Migration Reference: RevenueCat — Offering and product access

Read this **on demand only**, when a row in `references/migration-revenuecat.md` section 5's triage
table points here. It assumes the spine's rules (`references/migration.md`) and takes every code
signature from `references/<platform>.md` — nothing below is a snippet, because these divergences are
behavioral and the call you need is per-platform.

---

RevenueCat lets an app reach products by several routes. Adapty has exactly one: a placement, then that
placement's paywall or flow, then its products. Every row here is some version of that funnel being
narrower than the one the app was written against.

**Check which of RC's three access routes the app actually uses — one of them migrates for free.**
RC's `Offerings` exposes exactly `current`, `all` (a dictionary keyed by offering identifier), and
`currentOffering(forPlacement:)`. There is no `default`, despite that term appearing in older internal
notes; do not grep for one.

The three routes migrate very differently:

- **`currentOffering(forPlacement:)` maps straight across.** The call already names a placement, which
  is exactly Adapty's model, so this is a swap and not a restructure. Look for it before assuming work.
- **`offerings.current`** returns a paywall with no identifier anywhere in the code. This is the case
  `references/migration-revenuecat.md` section 1 covers: the RC Identifier may not be recoverable, and
  if you pick a placement ID you must disclose that you picked it.
- **`offerings.all["some_id"]`** at least gives you the identifier, so the placement ID is recoverable
  from the code — but the fetch-everything-then-choose shape has no equivalent and becomes one fetch
  per placement.

Adapty always takes a placement ID, including `Adapty.getPaywallForDefaultAudience`, whose name
suggests otherwise but which still requires one.

**Typed package slots become a flat array.** RC exposes **seven** typed accessors — `monthly`,
`annual`, `weekly`, `lifetime`, `sixMonth`, `threeMonth`, `twoMonth` — plus `package(identifier:)` and a
subscript, so `offering["monthly"]` reads the same slot as `offering.monthly`. On Android the same seven
are derived through a `PackageType` lookup. Grep for the whole set: `monthly` is the most common in real
code and the one most easily missed if you only search for the durations a particular app happens to
sell.

`Adapty.getPaywallProducts` returns a plain array instead, and the order is guaranteed — the SDK
documents it as the same order as the paywall object, and builds it by walking the paywall's product
references. UI that reads `offering.annual` into a specific slot has nothing to read.

Two ways out, and the choice belongs in `ADAPTY_SETUP.md`. Prefer rendering the array in order and
letting the paywall's configuration decide what appears where — that is the shape Adapty is built
around, and it makes the screen independent of which products the paywall carries. Where the layout
genuinely cannot be order-driven, match products by their store identifier rather than by position;
never by array index, which silently re-points at a different product the first time someone reorders
the paywall in the dashboard.

**Products cannot be fetched by store ID.** RC's `Purchases.products([…])` takes raw store identifiers
and needs no paywall. Adapty has no equivalent; the docs are explicit that the placement ID is the only
ID you should hardcode. Two patterns hit this:

- A hardcoded fallback paywall, which is how RC apps cope with a failed offerings fetch. Adapty's
  answer is a fallback file — see below.
- A products screen assembled from a constant list. This needs a real placement, which means dashboard
  work, which means it belongs in `ADAPTY_SETUP.md` rather than being improvised into existence.

**A `nil` from `currentOffering(forPlacement:)` may be a deliberate "show nobody a paywall".** RC
resolves a placement in two steps: if the placement identifier is present in its targeting map it uses
that offering **and never falls back**, even when the mapped value is empty; only a placement that is
absent from the map falls through to a dashboard-configured fallback offering.

So an RC app that treats `nil` as "this audience gets no paywall" is expressing targeting, not handling
an error. Do not port that branch as a failure path. The intent has to move into Adapty's placement and
audience configuration, and because you cannot see the RC targeting map from the code, it belongs in the
verify-against-your-dashboard checklist rather than in a guess.

**The fallback file is new work, not a migration.** RC has no bundled fallback: its offline story is the
cached offerings it already holds (it falls back to cache on server errors and network failure) plus
offline entitlements. There is nothing to port, so an agent mapping call site to call site will produce
an app with no offline paywall at all — which looks fine in development and shows an empty paywall to a
first-launch user on a plane.

Four things about it that the RC codebase cannot teach you:

- **You do not hand-write it.** The payload is downloaded from the Adapty dashboard — the SDK expects
  exactly what the backend returns.
- **`Adapty.setFallback` does not require an activated SDK**, unlike almost everything else, so it can
  be called before or alongside activation.
- **The file is format-versioned**, and an SDK major upgrade can require re-downloading it. Adapty's own
  iOS 4.1 migration notes call this out. Put it in the handoff as a recurring chore, not a one-off.
- **It covers builder paywalls too**, not just product lists — the file carries UI schema alongside the
  placement data, so a flow or builder paywall can render offline.

One behavior worth knowing before you debug it: the fallback file and the on-device cache are compared
by version, and the newer one wins. A stale bundled file does not override fresher cached content.

**Because the file is a dashboard download, you usually cannot produce it — and that is exactly why it
needs its own heading in the handoff, not a mention inside the deferred-dashboard list.** Every other
deferred item is a thing the user has *not yet gained*; this one is a protection the app has silently
*lost*, because RC's own offering cache was covering the offline case and Adapty's cache does not cover a
first launch. Bundling it into "other things to set up in the dashboard" reads as optional housekeeping
and gets postponed past release, at which point the symptom is an empty paywall for users with no network
on first run — a case QA rarely tests. Give it its own subheading, say what breaks without it, and put the
download step and the `setFallback` call in the same place.

**A custom paywall has to log its own views, and RC gave you no call to port.** RevenueCat measured
paywall impressions itself, so an RC codebase contains nothing that looks like view logging. Adapty
cannot know when your own UI put a paywall on screen, so unless you log it, paywall funnels and every
A/B test result stay empty — with no error, no warning, and a dashboard that looks merely unused rather
than broken. It is the purest form of the absence-keyed hazard in this file: there is no line to grep
for and no diff in which the omission appears.

The rule is conditional, and getting it backwards is its own bug:

- **Custom paywall (`paywallApproach == custom`) → you must log the view**, once, when the screen is
  actually shown to the user. Adapty's docs put it plainly: logging views "needs your input because only
  you know when a customer sees a paywall."
- **Paywall Builder or Flow Builder paywall → do not log it.** Those track views automatically, and a
  manual call on top produces double-counted views — which the docs list as a known cause of a paywall
  view count showing twice the expected number.

The call is named per platform and per SDK major (`logShowFlow` on Flutter v4+, `logShowPaywall`
elsewhere), so take the exact spelling from `references/<platform>.md` rather than from here, and put it
in the same commit as the paywall screen so the two cannot drift apart.

**Nothing is prewarmed.** RC refreshes its offerings cache when the SDK is configured *and again every
time the app comes to the foreground*, so by the time a user reaches a paywall the data is almost always
in hand. Adapty fetches a placement only when you ask for one. Migrate the code as-is and the first
paywall gets measurably slower — a regression nobody attributes to the migration, because the paywall
still works. Fetch the paywall ahead of the moment it is shown and hold it; the platform reference's
Stage 2 covers where.

Adapty does give you two controls RC has no equivalent for, and they are the right tools for the preload
you are about to add: the placement fetch takes a `loadTimeout` — five seconds by default — after which
it falls back instead of hanging, and an `AdaptyPlacementFetchPolicy` that serves cached placement data
up to an age you choose rather than going to the network. Neither exists on RC's `offerings()`, so there
is nothing to port. Take the exact parameter names from `references/<platform>.md`; they vary per SDK.

**Products are a second call.** RC's packages arrive inside the offering. Adapty needs
`Adapty.getPaywallProducts` after the paywall, which is one more await and one more thing that can
fail. Handle its failure separately from the paywall fetch: a paywall that loads and products that do
not is a blank paywall, which is worse than an error.

Adapty's own page for this: `https://adapty.io/docs/fetch-paywalls-and-products`

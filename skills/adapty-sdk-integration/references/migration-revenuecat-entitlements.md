# Migration Reference: RevenueCat — Entitlements and caching

Read this **on demand only**, when a row in `references/migration-revenuecat.md` section 5's triage
table points here. It assumes the spine's rules (`references/migration.md`) and takes every code
signature from `references/<platform>.md` — nothing below is a snippet, because these divergences are
behavioral and the call you need is per-platform.

---

**Adapty polls; RC waits to be asked.** The two SDKs reach freshness by opposite routes, and the
difference decides how much of the app's caching code survives.

RevenueCat serves its cached customer info until that cache is *stale*, then refetches on the next
access. Stale means five minutes in the foreground and **twenty-five hours in the background** — the
same thresholds on iOS and Android. That long background window is why RC apps so often force a refresh
at a decisive moment, and why RC's guidance is to call `customerInfo()` whenever you need to check
access: the call is usually free, and occasionally it is the thing that gets you current data.

Adapty inverts this. Its SDK polls the backend on a timer — about every minute, dropping to roughly ten
seconds after a failed attempt, and accelerating to a few seconds for a while after the user opens a
web paywall, so an out-of-app purchase lands quickly — and serves the cache in between. While the app
is running the profile is never much more than a minute old.

Two consequences:

- Porting RC's call-it-every-time habit literally produces a network call on every gate check for data
  that was already fresh. Read the cached profile through `Adapty.getProfile`, or react to the
  profile-update listener at Stage 3 of `references/<platform>.md`.
- A forced refresh before gating — the workaround for RC's 25-hour window — is redundant, and there is
  no API to force one anyway (see the cache-invalidation entry below). Delete it rather than looking
  for the equivalent.

Do not add your own polling on top of Adapty's.

**A product can carry only one access level.** RC allows one product to unlock several entitlements.
Adapty's product form asks you to select *the* access level the product belongs to — singular. A
product that unlocked two RC entitlements cannot be represented, so create it against the access level
the code actually gates on and record the dropped one.

This one goes in `ADAPTY_SETUP.md`'s entitlement → access level mapping (`references/migration.md`
section 5, subsection 2), naming the product, the access level you chose, the entitlement you dropped,
and the file and line that decided it. Do not resolve it silently — a user whose product legitimately
grants two tiers needs to know Adapty models that differently before they ship.

Because this is a product-model limit rather than a missing feature, confirm it by re-reading the page
rather than by searching the docs index:

```bash
curl -s "https://adapty.io/docs/create-product.md" | grep -i -A3 "access level"
```

**There is no cache invalidation API.** RC's `invalidateCustomerInfoCache` and `fetchPolicy` let the
app force a refresh. Adapty owns refresh and exposes no equivalent. This is a design difference, not a
gap awaiting a feature — delete those calls rather than looking for a replacement. If the code called
them at a specific moment because it needed post-purchase state, the purchase result already carries a
fresh profile, and the listener covers the rest.

**Whether RC's `customerInfoStream` has a counterpart depends entirely on the platform — check before
you restructure anything.** Adapty's profile-update mechanism is not one shape:

- **Flutter exposes a real stream.** `didUpdateProfileStream` maps almost directly onto
  `customerInfoStream`, and it is what the platform reference and Adapty's own docs build their
  recommended service around. Restructuring away from a stream here would be moving *away* from the
  right API.
- **Native iOS is a delegate**, Android and KMP a listener interface, React Native and Capacitor an
  event subscription, Unity an event-listener object.

So on the callback platforms, code built around an `await`-loop does need inverting — a callback pushes
instead of a loop pulling — and the bridge into whatever the app uses for state is app-side code, not an
Adapty API. On Flutter it is a swap. `references/<platform>.md` Stage 3 names the exact mechanism; take
it from there rather than assuming a callback.

**There is no one-expression "any access active" check.** RC's `entitlements.active.isEmpty` answers
"does this user have anything" in one go. Adapty's profile exposes access levels keyed by ID; check the
specific one the app gates on, or iterate the collection. An app with a single `premium` level barely
notices; an app with several tiers and a generic is-subscribed check needs that check rewritten as an
explicit list of the levels that count.

**RC's Offline Entitlements → local access levels.** Adapty ships this for exactly the case RC's
feature covered: paid access keeps working through a temporary outage. It was a genuine gap when the
internal comparison behind this file was written and is not one now — do not report it as missing.
`https://adapty.io/docs/local-access-levels`

Adapty's own page for this section: `https://adapty.io/docs/subscription-status`

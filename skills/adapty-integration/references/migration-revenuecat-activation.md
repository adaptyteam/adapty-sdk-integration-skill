# Migration Reference: RevenueCat — Activation, threading, and fetch control

Read this **on demand only**, when a row in `references/migration-revenuecat.md` section 5's triage
table points here. It assumes the spine's rules (`references/migration.md`) and takes every code
signature from `references/<platform>.md` — nothing below is a snippet, because these divergences are
behavioral and the call you need is per-platform.

---

Nothing in this section is about a purchase concept. These are the ways the two SDKs behave differently
as *libraries*, and they are the divergences most likely to be discovered from a crash report rather
than from a diff.

**Initializing twice is safe in RC and is not safe in Adapty — differently per platform.** RevenueCat
logs a warning and carries on when `configure` runs a second time, and when the second call carries an
identical configuration it ignores the call outright. Nothing throws. So defensive double-configuration
— from a scene delegate as well as the app delegate, on a hot reload, in test setup, in a plugin that
re-initializes — is a pattern RC quietly tolerates, and it is common in RC codebases for exactly that
reason.

Adapty does not tolerate it, and does not agree with itself about how:

- **iOS throws.** A second activate raises an "activate once" error. If the app's second call sits
  somewhere that does not expect a throw, that is a crash or a swallowed failure.
- **Android logs an error and returns.** The call is a silent no-op; nothing reaches the caller.

Find every activation site before you migrate — not just the one in the app delegate — and reduce them
to one. On a cross-platform project (Flutter, React Native, KMP, Unity) this matters more, not less: the
same Dart or TypeScript that double-activates will throw on one platform and no-op on the other, so the
bug presents as platform-specific flakiness rather than as a clear error.

**The not-initialized failure mode moves, and on Android it moves out of the call stack.** All four SDKs
refuse to work before initialization, but they refuse in four different ways:

- **RC iOS** — touching the shared instance triggers a `fatalError`. An uncatchable crash.
- **RC Android** — the shared instance throws an uninitialized-property exception.
- **Adapty iOS** — throws a catchable Adapty error.
- **Adapty Android** — does **not** throw. It hands an "Adapty not initialized" error to the callback
  you passed in.

That last one is the migration hazard. A `try`/`catch` wrapped around the RC call has nothing left to
catch, so it becomes dead code while the error quietly arrives somewhere the app is not looking. Move
the handling into the result callback, and do not leave the old catch block behind as reassurance.

The upside of the same change: because RC iOS crashes outright, an RC codebase's call ordering is
correct by survival — it would not have shipped otherwise. Adapty returns an error instead, which is
friendlier and means a newly mis-ordered call degrades silently rather than announcing itself. Adapty
publishes a per-platform "SDK call order" page for this reason; consult it if the app activates late or
conditionally.

**The paywall UI module needs its own activation, and RC's does not.** This one has no RC call site to
map from, which is exactly why it gets missed: RevenueCatUI has no activation step at all. You `import
RevenueCatUI` and use `presentPaywallIfNeeded` or a paywall view, and it works because the core SDK is
already configured.

Adapty splits this in two. `AdaptyUI.activate()` is a second, separate activation that must run **after**
`Adapty.activate()` — it throws if the core SDK is not activated yet, and it throws an activate-once
error if it runs twice, the same double-initialization hazard described above. Every AdaptyUI entry point
then guards on it and fails if activation never happened.

The failure mode is total but narrow: purchases, profiles, and access levels all work, and only paywall
presentation fails. So an app can look successfully migrated in every respect except the screen the
migration existed to serve. On any run where `paywallApproach` is `paywall_builder` or `flow_builder`,
treat this as part of the activation work rather than as a UI detail, and take the exact call and its
configuration from `references/<platform>.md`.

**Adapty delivers callbacks on the main thread; RC does not promise to.** Adapty dispatches profile
updates and completion handlers to the main queue by default on both platforms — configurable on iOS
through the activation configuration's callback dispatch queue. RevenueCat's customer-info delegate is
invoked without any main-thread hop, and RC's own delegate documentation says the delegate is not
thread-safe.

Two small consequences, in opposite directions. Manual main-thread hops inside the RC listener become
redundant and can go. But work the app was doing in that listener now runs on the main thread, so
anything expensive there — a database write, a large decode — becomes a main-thread stall it was not
before. Move it off deliberately rather than inheriting it.

**iOS is actor-isolated, which removes synchronous call sites.** The Adapty iOS SDK is confined to a
global actor, so its API is asynchronous throughout. RevenueCat offers both completion-handler and async
APIs and is not actor-isolated, which means an RC codebase can and often does read state synchronously —
an entitlement check inside a computed property, a SwiftUI `body`, or an `init`. There is no synchronous
Adapty equivalent to put there.

This is the one divergence in this file that surfaces as a compile error rather than a silent failure,
so it will not escape you. It is here because the *fix* is a design decision and not a mechanical one:
the value has to be resolved earlier and held in app state, which usually means the wrapper described in
`references/migration-architecture.md` plus the profile listener from
`migration-revenuecat-entitlements.md` feeding it. Do not reach for a
semaphore or a blocking wait to preserve the old shape.

**Placement fetches take a timeout and a fetch policy.** Covered in `migration-revenuecat-placements.md`
as it affects preloading; noted
here because there is no RC counterpart to migrate and it is therefore easy to miss. Adapty's placement
fetch accepts a `loadTimeout` — five seconds by default — after which it falls back instead of hanging,
and an `AdaptyPlacementFetchPolicy` that can serve cached placement data up to an age you choose. RC's
`offerings()` accepts neither. Take the exact parameter names and spellings from
`references/<platform>.md`; they vary per SDK.

# Migration Reference: RevenueCat — Observer mode

Read this **on demand only**, when a row in `references/migration-revenuecat.md` section 5's triage
table points here. It assumes the spine's rules (`references/migration.md`) and takes every code
signature from `references/<platform>.md` — nothing below is a snippet, because these divergences are
behavioral and the call you need is per-platform.

---

**Report every transaction, on every platform.** This is the highest-consequence divergence in this
file, and the only one that costs money while looking completely correct.

RevenueCat's reporting requirement is conditional, and it takes three different shapes:

- **StoreKit 1** — nothing to call. RC observes the payment queue itself, so the app has no reporting
  code at all.
- **StoreKit 2** — `recordPurchase`, once per purchase, on every Apple platform (it is available on
  iOS, macOS, tvOS, and watchOS; do not assume it is macOS-only).
- **Android**, with purchases completed by the app — `syncPurchases`, which is a **batch** sync of the
  user's purchases rather than a per-transaction report.

Adapty requires `Adapty.reportTransaction` per transaction, unconditionally. So what you are porting
varies: from a StoreKit 1 codebase there is **no call to find** and the reporting is entirely new code,
and from an Android codebase there is one batch call to replace with a report at each purchase site —
not a rename.

**On Apple platforms this can be a StoreKit 2 prerequisite, not a call swap.** Adapty's iOS SDK is
StoreKit 2 based, and the public reporting overloads accept a StoreKit 2 transaction (or its verification
result). An app whose own purchase code is StoreKit 1 holds `SKPaymentTransaction` objects and has
nothing it can pass. So for an RC observer-mode app on StoreKit 1, reporting is blocked until the app's
purchase code moves to StoreKit 2 — which is a scope item to raise with the user before you start
editing, not something to discover halfway through.

The paywall variation ID is an optional argument. Omitting it does not break the purchase; it breaks the
attribution that ties revenue back to the paywall that earned it, silently.

**What observer mode actually switches off:** with it enabled, Adapty does not start its transaction
observer at all. That is the whole mechanism behind the requirement above — nothing is watching, so
anything you do not report does not exist as far as Adapty is concerned.

Miss it and nothing fails. The app compiles, purchases succeed, the user gets what they paid for, and
Adapty records none of it — no revenue, no analytics, and no access level granted from the transaction.
The migration looks finished and the dashboard stays empty. There is no compiler error and no runtime
error to notice.

So on any run where `paywallApproach` is `observer`, treat the reporting call as the deliverable rather
than as a detail: find every place the app completes a purchase — not just the one the RC call was
next to — and report from each.

**Then tell the user how to verify it, and how not to.** "The app builds" proves nothing here, but so
does the obvious test: transactions originating in Xcode's local StoreKit testing environment are
**silently discarded** by the reporting call — it returns without error and nothing reaches Adapty. An
engineer who validates observer mode against a local `.storekit` configuration will conclude the
integration is broken when it is fine, or that it works when they have tested nothing. Point them at a
sandbox purchase instead, and say plainly in `ADAPTY_SETUP.md` that a local StoreKit-file purchase is not
a valid check. `references/testing-setup-ios.md` covers the sandbox setup.

`Adapty.reportTransaction` also takes the paywall variation ID when the purchase came from an Adapty
paywall, which is what ties revenue back to the paywall that earned it. Omitting it does not break the
purchase; it breaks the attribution silently. The platform reference's Observer mode section has the
signature and the per-platform page is
`https://adapty.io/docs/implement-observer-mode`.

# Migration Reference: RevenueCat — Purchases and offers

Read this **on demand only**, when a row in `references/migration-revenuecat.md` section 5's triage
table points here. It assumes the spine's rules (`references/migration.md`) and takes every code
signature from `references/<platform>.md` — nothing below is a snippet, because these divergences are
behavioral and the call you need is per-platform.

---

**Eligibility is computed for you only if a Paywall Builder paywall renders the purchase.** RC asks the
store whether a user is eligible for a trial or introductory offer, then the app decides what to render.
Adapty resolves eligibility itself — but automatic application of the **introductory** offer holds only
for paywalls built in the Paywall Builder.

**On a custom paywall — the usual outcome of "keep my existing paywall UI", and therefore the usual
migration — you must check iOS introductory-offer eligibility yourself.** Adapty's docs are explicit
about the stakes: skipping it "may result in your app being rejected during release" and "could lead to
charging the full price to users who are eligible for an introductory offer". So on a `custom` run the RC
eligibility call is **not** dead code to delete; it is a call to re-point at Adapty's own eligibility
check. Deleting it is a regression with money and App Review attached.

Read the page and find the iOS eligibility section before you touch the eligibility branch:

```bash
curl -s "https://adapty.io/docs/making-purchases.md?ref=skill-<sessionToken>" | grep -in "paywall builder\|eligib\|rejected\|full price"
```

Grep for the caveat, not for the reassurance: a search for the auto-apply sentence returns the
*promotional*-offer rule and never surfaces the introductory-offer limit, because the two are worded
differently. `references/<platform>.md` and
`https://adapty.io/docs/fetch-paywalls-and-products` carry the actual eligibility call.

**You cannot choose an offer at purchase time.** RC fetches eligible promotional offers, or eligible
win-back offers, and the app passes the chosen one into the purchase call. Adapty applies the eligible
offer automatically, based on how the offer is attached to the product in that paywall. There is no
parameter to pass one in.

So the app-side selection code is deleted, and the intent behind it moves to the dashboard: the offer
has to be attached to the right product on the right paywall or it will never apply. That is
configuration you cannot do from the CLI, so it belongs in `ADAPTY_SETUP.md`
(`references/migration.md` section 5, subsection 3), stated next to the paywall it affects and naming
which offers the RC code was selecting. An app that silently stops applying a win-back offer looks
fine and quietly loses the winbacks.

**And when several offers could apply, the precedence is fixed and not yours to change.** Adapty
resolves one offer per product when it builds the product list: an eligible **win-back** offer wins,
otherwise a configured **promotional** offer, otherwise the **introductory** offer if the user is still
eligible for one. RC's model let the app decide — fetch the eligible offers, apply business logic, pass
the chosen one in. If the RC code encoded a different preference than Adapty's order, that preference is
not expressible and the behavior will change. Say so in the handoff rather than assuming nobody will
notice which discount applied.

Confirm this by re-reading the page rather than the docs index — it is a behavioral rule, not a feature
that would appear as an index entry. Search for the Paywall Builder condition, **not** for the
auto-apply sentence: the latter matches only the promotional-offer rule and will leave you believing
introductory offers are handled too.

```bash
curl -s "https://adapty.io/docs/making-purchases.md?ref=skill-<sessionToken>" | grep -in "paywall builder\|applied automatically"
```

**Restore: RC has two methods, Adapty has one, and Adapty's is the quiet one.** RC splits restoring in
two, and the difference is whether the user gets an Apple ID credential prompt:

- **`restorePurchases`** forces a receipt refresh. On StoreKit 1 that issues a refresh request, which
  prompts the user to authenticate — the behavior behind a "Restore Purchases" button.
- **`syncPurchases`** explicitly does not refresh, so it never prompts. Its real use is observer mode
  and migration, not a user-facing button.

`Adapty.restorePurchases` never refreshes a receipt and never asks StoreKit to sync an account, so it
never prompts. It reads the transaction history and returns the profile. Two consequences:

- **`syncPurchases` maps across cleanly** — same no-prompt semantics. If the app calls it at launch, keep
  that call site and swap the method; do not treat it as unmappable.
- **A "Restore Purchases" button loses its prompt.** Usually an improvement, and StoreKit 2 does not need
  the refresh to see past transactions. But a user with no active App Store session gets a silent empty
  result where RC would have asked them to sign in, so keep the button's own "nothing to restore" message
  meaningful rather than relying on the system dialog to explain things.

**`pending` is a result, not an error.** RC surfaces a deferred purchase — a parent-approval flow, an
offline cash payment — through the error path. Adapty returns `pending` as its own case alongside
success and user-cancelled. Ported as-is, a pending purchase gets reported to the user as a failure,
and then completes later anyway. Add the branch; the platform reference's Stage 2 has the shape.

**Purchase-time parameters: a real gap on Apple platforms, no gap on Android.** RC's purchase builder
differs per platform, and so does the migration.

On Apple platforms RC accepts a quantity and arbitrary per-purchase metadata alongside the offer.
Adapty's iOS `makePurchase` takes the product and nothing else — there is no parameters object at all,
so **multi-quantity consumable purchases and purchase-level metadata have no equivalent**. An app
selling "5 credit packs at once" through quantity has to model that differently (separate products, or
repeated purchases), and metadata used to correlate a purchase with app-side state has to move to the
app's own storage keyed by the transaction. Both belong in the handoff.

On Android there is **no gap** and you should not report one: RC's `oldProductId`,
`googleReplacementMode`, and `isPersonalizedPrice` all have counterparts in Adapty's Android purchase
parameters — subscription-update parameters carrying the old product and a replacement mode, and a
personalized-offer flag. Subscription upgrade and downgrade flows migrate intact. Take the exact
spellings from `references/<platform>.md` — on a cross-platform run the Android parameters are exposed
under platform-specific names, so `references/android.md` is the wrong file to read unless the project
*is* native Android.

**StoreKit Messages are not supported.** RC documents the StoreKit Messages API as one redemption path
for win-back offers. Adapty has no support for it. Drop the code and note the capability loss.

```bash
curl -s "https://adapty.io/docs/llms.txt?ref=skill-<sessionToken>" | grep -i "storekit message"
```

A hit means this row is stale and Adapty supports it now — read the page and do not report a gap.

Adapty's own page for this section: `https://adapty.io/docs/making-purchases`

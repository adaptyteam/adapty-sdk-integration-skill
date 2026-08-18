# Migration Reference: RevenueCat — Features with no Adapty equivalent

Read this **on demand only**, when a row in `references/migration-revenuecat.md` section 5's triage
table points here. It assumes the spine's rules (`references/migration.md`) and takes every code
signature from `references/<platform>.md` — nothing below is a snippet, because these divergences are
behavioral and the call you need is per-platform.

---

Everything in this section is deleted code plus an `ADAPTY_SETUP.md` entry
(`references/migration.md` section 5, subsection 3) saying what the app used it for. State the
capability loss plainly — a user who relied on one of these needs it raised before they ship, not
discovered afterward.

**Every entry below carries its own confirmation command, and you run it before telling the user
anything is missing.** A hit means the entry is stale and Adapty supports the feature now: read the
page, and tell the user how to use it instead of reporting a gap. Two entries in this file were gaps
when the comparison behind it
was written and have since closed, so treat the list as dated rather than settled.

**Customer Center** — RC's prebuilt subscription-management UI. No Adapty equivalent, and its
replacement is app-side screens, which is a real scope item rather than a line of code.

```bash
curl -s "https://adapty.io/docs/llms.txt" | grep -i "customer center"
```

**The Manage Subscriptions sheet** — the system sheet RC can present. No Adapty equivalent; the app can
still open the store's own subscription-management URL itself.

```bash
curl -s "https://adapty.io/docs/llms.txt" | grep -i "manage subscription"
```

**Refund requests** — RC can present Apple's refund-request sheet. Adapty has no equivalent.

**Adapty Refund Saver is not this feature.** Refund Saver is a server-side capability for responding to
refund requests; it is not an SDK call that shows a sheet to a user. Do not offer it as the equivalent —
that mistake sends the user looking for an API that does not exist.

```bash
curl -s "https://adapty.io/docs/llms.txt" | grep -iE "refund request|beginRefundRequest"
```

**Redemption Links** — RC's flow for buying on the web without the app installed and redeeming
in-app afterward, via `redeemWebPurchase`. No Adapty equivalent. Adapty does have web paywalls, which
solve a nearby but different problem: paying outside the store, by a user who already has the app.
If the app uses redemption links, say explicitly that web paywalls do not replace them.

```bash
curl -s "https://adapty.io/docs/llms.txt" | grep -iE "redemption|redeem"
```

**App Extensions and widgets** — RC can be used from extension targets. Adapty is not documented for
this, so an extension reading subscription state through the SDK has no supported path. The workable
shape is for the host app to write the state somewhere the extension can read it, which is app-side
work and belongs in the handoff.

```bash
curl -s "https://adapty.io/docs/llms.txt" | grep -iE "app extension|widget"
```

**`presentPaywallIfNeeded` has no equivalent.** RC's SwiftUI modifier checks entitlements and presents
a paywall in one call. Adapty separates the two: check the access level, then present. This is more
code than the RC version, not less, and it is app-side code — the access check from Stage 3 of
`references/<platform>.md` and the presentation from Stage 2. Keep the two concerns separate rather
than rebuilding a combined modifier; the app's own navigation usually wants to decide when a paywall
appears.

**Store targets: Amazon Appstore and RC's web store have no Adapty equivalent, and there is only one
SDK key.** This is the entry the triage table's `AmazonConfiguration` / `Store.amazon` / per-store-key row
sends you to.

- **Amazon Appstore is not supported.** An app that ships to Amazon cannot serve that store through
  Adapty. This is a dropped *distribution channel*, not a call to remap, so it needs stating in the
  handoff in those terms — the user may not be willing to migrate at all on that basis.
- **RC's web store / Web Billing has no counterpart.** Adapty's web paywall is a nearby but different
  thing: it takes an existing app's user out to a web checkout. It is not a storefront for users who
  never installed the app, and it does not redeem an RC web purchase.
- **One Public SDK key replaces the per-store keys.** RC apps commonly branch on the store to pick a key
  (`Platform.isIOS ? applKey : googKey`, or an Amazon variant). Adapty has a single key per app, so that
  branch collapses — and when it collapses it silently takes the store distinction with it. Delete the
  branch deliberately and say in the handoff which stores the app actually ships to.

```bash
curl -s "https://adapty.io/docs/llms.txt" | grep -iE "amazon appstore|web billing|web store"
```

A hit means one of these now has support — read the page and correct this entry rather than reporting a
gap. Note that a bare search for `amazon` matches Adapty's Amazon **S3** export pages, which are
unrelated; that is why this command is narrower.

**Web checkout URLs have a direct equivalent.** RC's `package.webCheckoutUrl` becomes
`Adapty.createWebPaywallUrl`, which takes a paywall or a product. Straight swap.

**RC Virtual Currencies → Adapty virtual currencies.** Link a currency to a product so a purchase
grants credits, and read or adjust balances through the server-side API. This was a gap when the
comparison behind this file was written and is not one now. An app using RC's virtual currencies has a
real migration path — a nontrivial one, since balances have to be carried over, but a path.
`https://adapty.io/docs/virtual-currencies`

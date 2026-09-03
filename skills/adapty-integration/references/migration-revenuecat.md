# Migration Reference: RevenueCat

Read this when `migrationSource == "revenuecat"`, together with `references/migration.md` — the
source-agnostic spine. That file's rules on access levels, products, placements, the never-imitate
list, and the `ADAPTY_SETUP.md` contract all apply here unchanged; this file states only what is
specific to RevenueCat, and points back at the spine section that already covers everything else.

---

## 1. Offering identifiers: what a placement's developer ID has to equal, and when it can't be recovered

A RevenueCat Offering's **Identifier** is set once, at creation, and can never be changed afterward.
That Identifier is what a placement's developer ID must equal — `references/migration.md` section 3's
placement rule, applied to RC's own field.

- **A call site that fetches a specific offering by identifier maps mechanically to a placement of
  that identifier.** The exact call differs per SDK language (Flutter's `getOffering("x")`, for
  instance) but the shape is always "give me the offering named x" — grep for it before concluding
  the identifier isn't in the code.
- **The current offering is different.** The app fetches it by asking for "the current offering" from
  `getOfferings()`, with no identifier ever appearing anywhere in the code. When that is the only call
  site touching the offering you're mapping, RC's real Identifier is genuinely not recoverable from
  the code — not merely unobvious.
- In that case, follow `references/migration.md` section 3's rule for an unrecoverable identifier
  exactly: you may still choose a placement developer ID and write it into the code, but
  `ADAPTY_SETUP.md`'s "Skipped entities and inferred identifiers" subsection (spine section 5.3) must
  say plainly that the ID is an invented convenience name, not a value read from RevenueCat, and that
  the reader has to open the RC dashboard's Offerings list and confirm whether the placement should
  instead match the Identifier shown there. Do not let a different, true observation stand in for
  that disclosure — "there's only one paywall trigger in the UI, so one placement was enough" answers
  how many places the app calls the paywall, not what RevenueCat calls the offering being replaced,
  and settling the ID on that basis alone is exactly the silent substitution this rule exists to catch.

---

## 2. An Offering with a published RevenueCat Paywall reserves its placement ID — it gets nothing created

`references/migration.md` section 3 already states the general rule: a source paywall built in the
source's own visual builder gets no placement created for it, only a reservation, because paywall and
flow placements share one Adapty ID namespace. RevenueCat's version of that visual builder is its
Paywall Editor: an Offering can carry one attached Paywall, and once that Paywall is **Published**, RC
serves it to whichever customers see the Offering.

- **Whether an Offering has a Published Paywall attached is dashboard state — no call site in the app
  code reveals it.** An offering fetched only for its products looks identical in code whether or not
  it has a Paywall behind it in the dashboard. You can rule this in or out only with RC account access
  (the dashboard's Paywalls list) or the `--rc-key` catalog described in section 3 below; from code
  alone you cannot clear this hazard, only flag it.
- This is why every offering you are about to turn into a placement belongs in the "Verify against
  your RevenueCat dashboard" checklist below when you worked without account access: the reader must
  confirm in the dashboard that it carries no Published Paywall before treating that placement ID as
  safe, because creating it first would permanently block the flow placement of the same name later.
<!-- Note for whoever edits this file, not for the runtime agent and not for any handoff document:
this section is a hazard guard, not a rule verified in practice. The skill's baseline run had no
RevenueCat Paywall Builder paywall in its fixture, so the detection path has never been exercised.
Keep it anyway; the harm it guards against (an irreversibly reserved placement ID) is permanent. -->

---

## 3. Verify against your RevenueCat dashboard (code-only path)

`references/migration.md` section 5.1 already requires an `ADAPTY_SETUP.md` "Verify against your
`<source>` dashboard" subsection whenever you worked without account access — the default. For
RevenueCat, populate its checkboxes with:

- **Products you didn't create** because no store identifier for them appeared in code or config —
  list each with the ready-to-run `products create` command (spine section 5.1's first bullet; there
  is nothing RC-specific to add to the command itself).
- **Entitlements beyond the ones an actual call site references.** RC lets a project define
  entitlements nothing in the app checks yet; those exist only in the dashboard.
- **Offerings and Paywalls that exist only in the dashboard.** You created something only for the
  current offering and any offering referenced in code by identifier (`references/migration.md`
  section 3); every other Offering in the RC project — and every Offering carrying a Published Paywall
  (section 2 above) — still needs the recreate-as-placement-or-rebuild-as-flow decision spine section
  5.1 already calls for.
- **Offering metadata destined for paywall remote config** (spine section 3). RC stores this per
  Offering in the dashboard; it does not appear anywhere in a diff of the application code.

Mention that re-running `adapty migrate --rc-key <v2 secret key>` fetches this catalog directly from
RevenueCat and automates the comparison above — every checkbox in this list becomes a diff the CLI
already computed instead of a manual dashboard visit. (This flag belongs to the Adapty CLI's `migrate`
command, which is not yet in a published CLI release — say so if the user asks why it isn't on their
installed version.)

---

## 4. RC SDK version: no assumptions, no matrix, map the old API directly

- **Consult `migrationSourceVersion`, don't redetect it.** `SKILL.md` Phase 1 already reads the
  installed RC major version into it before this file is loaded. If it's empty, fall back to
  `references/migration.md` section 2's version-reading path before mapping a single RC call.
- **RevenueCat's SDK API surface changes across majors**, and RC publishes a dedicated migration guide
  per major jump (iOS 3.x→4.x and 4.x→5.x; Android 4.x→5.x through 8.x→9.x, at the time of writing).
  Do not map a call site from memory of RC's current API. When the installed major's surface is
  unfamiliar, fetch the index and find that specific jump's guide before touching the code:

  ```bash
  curl -s "https://www.revenuecat.com/docs/llms.txt" | grep -i migrat
  ```

  Never assemble the guide's URL from the version number yourself — take it from what the index
  actually lists, the same discipline `references/migration.md` requires for Adapty's own docs.
- **Map straight from the installed RC version to Adapty.** Never go old RC → current RC → Adapty as
  an intermediate step: either hop can silently drop or rename a concept, and a double translation
  leaves no way to tell which hop introduced the error.
- **REST API branch.** `adapty migrate --rc-key` needs a RevenueCat v2 **secret** key — the kind RC's
  dashboard lists under "Secret API keys" (prefixed `sk_`), not the public key used to configure the
  RC SDK itself. A v1-only key cannot drive it. Say this up front rather than letting the user
  discover it mid-run, and fall back to the code-only path (section 3 above) when a secret key isn't
  available.

---

## 5. Behavioral divergences: triage before you map

This section comes after section 4 deliberately: pin `migrationSourceVersion` first, because a row's RC
signal may not exist in the installed major, and a row you match against the wrong version sends you
restructuring code that isn't there.

**Every row is keyed to something you can point at in the code.** If you cannot cite the line that puts
you in a row, you are not in it. The converse matters too: this table is not an inventory of RC's API.
A call site that isn't here is not thereby a problem — it's covered by `references/migration.md`
section 4's generic mapping table and by `references/<platform>.md`, which own the signatures.

Two verdicts appear here: **Restructure** — the surrounding code has to change, and these are the rows
that compile fine and behave differently — and **Drop** — no Adapty equivalent, so delete the code and
hand the capability off in `ADAPTY_SETUP.md`. Divergences that resolve at the call site are in the topic
files only, which is why the table carries no third verdict.

**The word after the verdict names a file to read — `references/migration-revenuecat-<word>.md`.** Each
one carries the reasoning, the options, and the handoff obligation for its own topic, and each is 60–110
lines. Read the ones your matched rows name and no others; there are eight, and a run that loads all of
them has almost certainly stopped triaging and started browsing.

| Word | File covers |
|---|---|
| `activation` | Double-initialization, the not-initialized failure modes, callback threading, actor isolation, `AdaptyUI.activate`, fetch timeouts |
| `identity` | `logIn`/`identify` semantics, account switching, anonymous-profile data, re-requesting paywalls after identify |
| `placements` | `current`/`all` vs placements, package accessors, products-by-ID, preloading, fallback files, `nil`-as-targeting |
| `entitlements` | Freshness and polling vs staleness, one access level per product, cache invalidation, profile listeners |
| `purchases` | Offer selection and precedence, `pending`, restore vs sync, purchase parameters |
| `observer` | `reportTransaction` requirements, the StoreKit 2 prerequisite, how to verify it |
| `attribution` | Integration identifiers, the six unsupported tools, conversion data vs UTM setters, custom-attribute limits |
| `gaps` | RC features with no Adapty equivalent, each with the command that re-checks it |

| RC signal in the code | How Adapty differs | Verdict |
|---|---|---|
| `configure` called more than once — defensively, from a scene delegate, on hot reload, or in test setup | RC warns and carries on (and ignores the call outright when the config is identical). Adapty iOS **throws**; Adapty Android logs an error and returns silently. The same defensive code is harmless, fatal, or a no-op depending on platform | Restructure → activation |
| `try`/`catch` around an RC call to handle the not-configured case | The failure mode moves. RC iOS crashes outright (`fatalError`) and RC Android throws; Adapty iOS throws a catchable error, but **Adapty Android delivers it into the result callback** — so the existing catch block becomes dead code and the error path has to move | Restructure → activation |
| `logIn(` used for its return value — `(customerInfo, created)` | `Adapty.identify` returns nothing; both the profile and the was-created flag are gone | Restructure → identity |
| `logIn(` called again with a different user ID to switch accounts | `Adapty.identify` sends the **profile you are already on** plus the new ID. If Adapty already knows that ID you are switched onto its profile; if it doesn't, your current profile *becomes* that user and the previous identity is lost. Switching accounts needs `Adapty.logout` first — guarded, because both SDKs reject logging out an anonymous user | Restructure → identity |
| `Purchases.appUserID`, or anonymity detected by string-matching the `$RCAnonymousID:` prefix | RC's single ID becomes two, and neither is a drop-in: `customerUserId` is what you set and is **null while anonymous**, `profileId` is Adapty's own and always present. An anonymity check becomes `customerUserId == null`; a method that must return a non-null identifier needs `customerUserId ?? profileId`. Decide which one each call site actually wanted | Restructure → identity |
| The app sets custom attributes or attribution on the anonymous user before logging in | RC copies subscriber attributes forward, but only when the previous user was anonymous. Adapty copies nothing — its docs require resubmitting that data after identifying | Restructure → identity |
| The app identifies mid-session and keeps showing the paywall it already fetched | Adapty requires re-requesting paywalls and products after identifying, since the identified user can land in a different audience. RC refreshed offerings on its own (see the preload row), so no app code did this. Nothing looks broken — the anonymous user's paywall just keeps showing, and targeting silently doesn't apply | Restructure → identity |
| `offerings.current`, or `offerings.all` indexed by offering identifier | No equivalent — every Adapty fetch names a placement. `placements` separates RC's three access routes; one of them already names a placement and maps across directly, so read it before restructuring anything | Restructure → placements |
| `offering.monthly`, `.annual`, `.weekly`, `.lifetime`, `.sixMonth`, `.threeMonth`, `.twoMonth`; `package(identifier:)`; the `offering["key"]` subscript; `PackageType` on Android | `Adapty.getPaywallProducts` returns a flat array, ordered as the paywall lists it. All seven typed slots and the by-identifier lookups are gone — grep for the whole set, not just the obvious ones | Restructure → placements |
| `Purchases.products([…])`, or a purchase driven by a raw store product ID | Unsupported — the placement ID is the only ID ever hardcoded. A hardcoded RC fallback paywall becomes an Adapty fallback file | Restructure → placements |
| `currentOffering(forPlacement:)` whose `nil` return is handled as "no paywall for this user" | That `nil` is RC targeting, not an error: a placement present in RC's targeting map never falls back to the dashboard fallback offering, even when it maps to nothing. Porting the branch as a failure path loses the intent, and the RC targeting map is not visible from the code | Restructure → placements |
| **No fallback file shipped, because RC had none to port** | RC's offline story is its own offering cache plus offline entitlements — there is no bundled file, so nothing looks missing. Without an Adapty fallback file a first-launch offline user gets an empty paywall. The file is downloaded from the dashboard, not hand-written, is format-versioned so an SDK major upgrade can require re-downloading it, and also covers builder paywalls | Restructure → placements |
| **No paywall-view logging call anywhere**, because RC never needed one from the app | On a **custom** paywall Adapty cannot know when a user saw it, so you must log the view yourself or funnels and A/B results stay silently empty — no error, no warning, just no data. RC tracked its own impressions, so there is no call to port and nothing in the diff will reveal the omission. Conversely, do **not** add it on a builder paywall or flow: those log automatically and a manual call double-counts views | Restructure → placements |
| No preload before the first paywall is shown | RC refreshed offerings at configure **and on every foreground**; Adapty fetches only when asked, so the first paywall gets slower and nobody blames the migration | Restructure → placements |
| `customerInfo()` called on every entitlement check | Adapty refreshes the profile about once a minute and serves cache; a per-check network call is the wrong shape here | Restructure → entitlements |
| A forced refresh before gating, or at launch, to defeat a stale cache | The two SDKs get fresh differently: RC serves cache until it is stale — 5 minutes in foreground, **25 hours in background** — and refetches on access, so RC apps often force a refresh at a critical moment. Adapty polls on its own (60 s, faster after a failure or a web paywall), so the cache is never more than about a minute old while the app runs and the forced refresh is redundant. There is also no API to force one — see the `invalidateCustomerInfoCache` row | Restructure → entitlements |
| A product that unlocks more than one RC entitlement | One access level per product. The additional entitlement cannot be represented | Drop → entitlements |
| `invalidateCustomerInfoCache`, `fetchPolicy` | No equivalent; Adapty owns refresh | Drop → entitlements |
| **Any RC profile-update subscription**, whatever its shape on your platform: `customerInfoStream` or an async-sequence loop on iOS, `addCustomerInfoUpdateListener` on Flutter/Android/RN, a delegate on native iOS | Depends on the platform: Flutter has a real stream that maps almost directly, while iOS is a delegate and Android/RN/Capacitor/Unity are callbacks that need the loop inverted. Check the platform before restructuring — on Flutter this is a swap, and restructuring would move away from the right API | Restructure → entitlements |
| A cached boolean mirrored from `customerInfo` by a callback | Structure change — `references/migration-architecture.md` owns this row, including the shape to recognize | Restructure → entitlements |
| `eligiblePromotionalOffers()`, or a promo offer passed into the purchase call | Adapty applies the eligible offer automatically from the paywall's configuration. The selection code is deleted and the wiring becomes dashboard work | Drop → purchases |
| `eligibleWinBackOffers`, or a win-back offer passed into the purchase call | Same as promotional offers | Drop → purchases |
| Pending purchases handled in the error branch | `pending` is its own result case, not an error, and the purchase completes later | Restructure → purchases |
| StoreKit Messages API | Absent | Drop → purchases |
| `PurchaseParams.Builder` on Apple platforms carrying `with(quantity:)` or `with(metadata:)` | Adapty's iOS `makePurchase` takes the product and nothing else — no quantity, no per-purchase metadata. Multi-quantity consumables and purchase-tagging have no equivalent. **Android is not affected**: `AdaptyPurchaseParameters` covers the upgrade/proration and personalized-price params RC has there | Drop → purchases |
| `recordPurchase` or `syncPurchases`, in Observer mode — **or neither**, if the app is on StoreKit 1 | `Adapty.reportTransaction` is required per transaction, unconditionally — not only in the cases RC needed a call. RC needed nothing under StoreKit 1, `recordPurchase` per purchase under StoreKit 2, and a **batch** `syncPurchases` on Android, so there may be no call to port or one batch call to replace with per-transaction ones. Nothing fails to compile if you miss it, and Adapty records no revenue at all. On Apple platforms read the next row first | Restructure → observer |
| Observer mode on Apple platforms while the app's own purchase code is **StoreKit 1** | Adapty's iOS SDK is StoreKit 2 based and the reporting call accepts a StoreKit 2 transaction, so an SK1 app has nothing it can pass. Reporting is blocked until the purchase code moves to SK2 — a scope item to raise before editing, not mid-run | Restructure → observer |
| `restorePurchases` behind a user-facing button, or `syncPurchases` called at launch | Adapty has one restore and it never prompts for Apple ID credentials: RC's `restorePurchases` forces a receipt refresh (which prompts on SK1), RC's `syncPurchases` doesn't. So `syncPurchases` maps across cleanly — don't treat it as unmappable — while a Restore button loses its prompt and needs its own "nothing to restore" message | Restructure → purchases |
| `setMediaSource`, `setCampaign`, `setAdGroup`, `setAd`, `setKeyword`, `setCreative` | No equivalent — Adapty matches attribution itself and exposes the result on the profile. **But don't delete `setAppsFlyerConversionData` along with them**: a whole conversion payload from a known network ports to `Adapty.updateAttribution` with a source | Restructure → attribution |
| `setMparticleID`, `setAirshipChannelID`, `setCleverTapID`, `setKochavaDeviceID`, the three `setSolarEngine*` setters, `setAppstackAttributionParams` | No Adapty integration for any of these six tools — none appears anywhere in the SDK source | Drop → attribution |
| `setAttributes(…)`, or an attribute cleared by assigning `""` / `nil` | RC validated nothing and never threw. Adapty enforces limits and **rejects**: keys ≤30 chars from `[A-Za-z0-9._-]` only, string values non-empty and ≤50 chars, at most 30 attributes. An empty value is refused rather than deleting — removal is a separate explicit call, so RC's delete idiom becomes a runtime error | Restructure → attribution |
| `setPushToken`, `setPushTokenString` | No Adapty equivalent | Drop → attribution |
| `AmazonConfiguration`, `Store.amazon`, a per-store API-key switch, or any RC Web Billing / web-store target | Adapty has no Amazon Appstore support and no counterpart to RC's web store, and it uses **one** Public SDK key rather than a key per store. A store target the app actually ships to is a dropped capability, not a call to remap — say so explicitly rather than letting the per-store branch quietly collapse into the default store | Drop → gaps |
| `presentPaywallIfNeeded` | No high-level equivalent; the app implements the access check and the presentation itself | Restructure → gaps |
| **`import RevenueCatUI` with no activation call anywhere** — RevenueCatUI needs none | `AdaptyUI.activate()` is a required second activation, after `Adapty.activate()`. There is no RC call to map from, so it gets skipped. Purchases and access levels keep working and only paywall presentation fails — the app looks migrated except for the screen the migration was for | Restructure → activation |
| Customer Center, the Manage Subscriptions sheet, `beginRefundRequest`, `redeemWebPurchase` / Redemption Links, App Extension or widget usage | No Adapty equivalent for any of these. Confirm each is still missing before reporting it — `gaps` carries the check per feature | Drop → gaps |

**A Drop verdict is dated, not permanent** — each describes what Adapty lacked when this table was
written. Before telling the user Adapty cannot do something, run that feature's confirmation command in
`gaps`, or re-read the named page for the rows that are behavioral limits rather than missing features.
Two specifically: **Offline Entitlements** (→ local access levels) and **virtual currencies** were gaps
in the comparison behind this table and both closed — never report either as missing; `entitlements` and `gaps` map them.

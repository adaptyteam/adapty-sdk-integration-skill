# Migration Reference: Moving an Existing Purchase System to Adapty

Read this whenever `migrationSource` is set. It is the shared spine for every migration, on every platform, from every source system.

---

## 1. When this file applies

`migrationSource` is set means: the app already sells subscriptions or in-app purchases through another system, and Adapty **fully replaces** it. You are not installing a second purchase SDK alongside the first — the only exception is Observer mode, and only when the user explicitly chose it in Phase 2.

Your mission changes from "integrate from scratch" to: **map every call site of the source system to its Adapty equivalent, create only the dashboard entities that map cleanly, then remove the source SDK and delete the code that used it.**

Read this file together with:

| File | What it gives you |
|---|---|
| `references/<platform>.md` | Every Adapty API, code snippet, build command, and checkpoint. **All code comes from there** — this file contains no platform code and never substitutes for it. |
| `references/migration-<migrationSource>.md` | Source-specific concept mapping, when the file exists in this skill directory. It overrides this file on specifics. |
| Section 4 below | Your path when no `migration-<migrationSource>.md` exists. Today that is every source except RevenueCat. |

Adapty's own migration docs — fetch the overview once before you start mapping, plus the per-source page when one exists:

```bash
curl -s "https://adapty.io/docs/migrate-to-adapty-from-another-solutions.md?ref=skill-<sessionToken>"
# revenuecat →
curl -s "https://adapty.io/docs/migration-from-revenuecat.md?ref=skill-<sessionToken>"
# superwall →
curl -s "https://adapty.io/docs/migration-from-superwall.md?ref=skill-<sessionToken>"
```

There is no Adapty docs page for Qonversion, store plugins, or hand-rolled native store code — for those the overview plus section 4 is the whole of your guidance.

---

## 2. Source detection and version

`migrationSource` normally arrives already set. Confirm it against the code anyway: if the manifests contradict it, the code wins — say so to the user and proceed on what you found. If it is empty because nothing set it for you, detect it here: the table below is the only detector you get.

Grep these dependency manifests (whichever exist): `package.json`, `pubspec.yaml`, `Podfile`, `ios/Podfile`, `Package.swift`, `build.gradle`, `build.gradle.kts`, `app/build.gradle{,.kts}`, `android/app/build.gradle{,.kts}`, `Packages/manifest.json`. For hand-rolled StoreKit the only manifest-level trace is the Xcode project file — `ios/Runner.xcodeproj/project.pbxproj`, `ios/App/App.xcodeproj/project.pbxproj`, or the app's own `.xcodeproj`.

| Signal in a dependency manifest | `migrationSource` | Note |
|---|---|---|
| `revenuecat`, `purchases_flutter`, `react-native-purchases`, `purchases-capacitor`, `purchases-hybrid` | `revenuecat` | |
| `superwall` (any package whose name contains it) | `superwall` | |
| `qonversion` | `qonversion` | |
| `in_app_purchase:` as a **direct** dep in `pubspec.yaml` | `store-plugin` | Flutter |
| `flutter_inapp_purchase` | `store-plugin` | Flutter |
| `react-native-iap` | `store-plugin` | React Native |
| `expo-in-app-purchases` | `store-plugin` | Expo |
| `cordova-plugin-purchase` | `store-plugin` | Capacitor / Cordova |
| `com.unity.purchasing` in `Packages/manifest.json` | `store-plugin` | Unity IAP |
| `com.android.billingclient` | `native-store` | Google Play Billing |
| `StoreKit.framework` in a `.pbxproj`, or `import StoreKit` in source | `native-store` | |

Two rules about reading that table:

- **Check in order: dedicated purchase platforms → store plugins → native store code. First match wins.** Projects match several rows at once (an app using RevenueCat also links StoreKit); the first match is the system that actually owns the purchase logic.
- **Never detect from a lockfile.** Lockfiles list transitive dependencies indistinguishably from direct ones, so `in_app_purchase` pulled in by some other plugin reads as a store-plugin migration that isn't there. Direct dependencies live in the manifest.

**Record the source's major version in `migrationSourceVersion` before you map a single API.** Take the resolved version from the lockfile — `pubspec.lock`, `package-lock.json` / `yarn.lock` / `pnpm-lock.yaml`, `Podfile.lock`, `Packages/packages-lock.json`, or the pinned version in the gradle/manifest declaration when there is no lockfile. The API surface of every one of these sources differs across majors: a call you map from memory may not exist in the installed version, and a concept the installed version has may have no Adapty equivalent at all and must simply be dropped rather than mistranslated. If you had to fall back to a manifest constraint (`^10.4.2`) rather than a resolved version, state the version you assumed in `ADAPTY_SETUP.md`.

---

## 3. Mapping rules (source-agnostic)

Vocabulary differs per source: what Adapty calls an **access level** the source may call an entitlement, a permission, or nothing at all; what Adapty calls a **placement** the source may call an offering, a campaign, or a paywall group. Map by role, not by name.

**The prime rule: an entity that does not map cleanly must NOT be created.** Junk in the user's Adapty account is worse than a skipped entity, and a wrong product or placement cannot be undone. When in doubt, create nothing, and write into `ADAPTY_SETUP.md` exactly what to create, why you skipped it, and the ready-to-run command to finish it.

- **Access levels** — one per *active* entitlement in the source, ID = the source's own entitlement identifier, so existing code that gates on that string keeps working. Skip archived or unused entitlements. Sources with no entitlement concept at all (store plugins, hand-rolled native code — they gate on a product ID or a stored boolean) → use the default `premium` access level and record that choice, and the line of code it replaced, in `ADAPTY_SETUP.md`.

- **Products — store product IDs are IMMUTABLE once an Adapty product exists.** They can never be edited; the only fix is deleting the product and recreating it, which loses its paywall attachments. So **never create a product with a guessed, normalized, or placeholder store ID.** Use the exact identifier as written in the code or config, byte for byte. No real ID available → create no product; put the ready-to-run `products create` command in `ADAPTY_SETUP.md` with a `<REAL_PRODUCT_ID>` slot instead. A product's access level = the entitlement it unlocked in the source; attached to several → assign the one the code actually gates on and flag the choice; attached to none → the default access level, flagged.

- **One store identifier present in both stores → ONE Adapty product carrying both store IDs**, never two products. Equally, do not assume a product exists in every store the app ships to — create it with only the store IDs it demonstrably has.

- **Store product IDs the user types in complement the code, they do not replace it.** When the user supplies IDs (SKILL.md Phase 3 Step 4 asks for them), identifiers you found in the code stay as-is — never second-guess or overwrite them. Create every product from the user's list that the code does not already cover; where the same product appears in both under different identifiers, keep the code's identifier and flag the mismatch in `ADAPTY_SETUP.md` for the user to check.

- **Placements** — ID = the source's own offering/campaign identifier, so a source call site that fetches by name maps mechanically to a placement of that name. Create a placement (plus paywall, products in the source's display order) only for the offerings the app actually uses: the source's default/current one, plus any referenced in code by name. Offerings that are neither referenced nor current → list them in `ADAPTY_SETUP.md`, do not create them.

- **A placement developer ID you could not recover is an unknown, not a decision.** When the source's offering identifier is genuinely not in the code — the app only ever asks for "the current offering" — you may pick a working ID to write into the code, but you must never present it as recovered. In `ADAPTY_SETUP.md`, under **Skipped entities and inferred identifiers**, write that this ID is a convenience name you chose **because** the source's real offering identifier could not be read from the code, and that the user must confirm in the source's dashboard whether it should instead match that identifier. The same holds for any identifier, access level, or product you settled by inference: state the value, state that you inferred it, and state what would confirm it (section 5).

- **A source paywall built in the source's own visual builder → create NOTHING for it.** Paywall placements and flow placements share one ID namespace in Adapty, so a placement created now permanently blocks the flow placement with that ID, and builder paywalls are meant to be rebuilt as Adapty flows. List each such reserved placement ID, with its product list, under a **"Rebuild as flows"** heading in `ADAPTY_SETUP.md`.

- **Offering/campaign metadata maps to paywall remote config**, which the CLI cannot set. Put the metadata JSON in `ADAPTY_SETUP.md` next to the paywall it belongs to.

- **Never create or imitate:**
  - **Webhooks** — Adapty's payload format differs from the source's; the user's backend needs work. Checklist item, not a thing you recreate.
  - **Audiences, targeting rules, experiments, A/B tests** — not exportable from any source. Checklist item.
  - **Store credentials** — write-only at the source and impossible to export. The user re-enters them in Adapty (section 5).

---

## 4. No `migration-<source>.md`: the unknown-source path

This is the normal case, not the exception. Work from the source's call sites — every purchase system has the same handful, whatever it names them.

Enumerate them all before writing code (grep for the source's package/class name across the whole project, not just the obvious service file), then map each one through `references/<platform>.md`, which owns the exact signature, async style, and error handling:

Every platform reference uses the same stage numbering, so the last column points at the same place on all of them:

| Source call site | Adapty equivalent | Platform reference |
|---|---|---|
| SDK init / configure / setup | `Adapty.activate` | Stage 1 |
| User identification, login, "app user ID" | `Adapty.identify`; logout → `Adapty.logout` | Stage 4 |
| Product / offering / paywall fetch | `Adapty.getFlow`, then `Adapty.getPaywallProducts` when a custom UI renders the products itself; on Capacitor and Unity `Adapty.getPaywall` takes `getFlow`'s place | Stage 2 |
| Purchase | `Adapty.makePurchase` | Stage 2 |
| Restore purchases | `Adapty.restorePurchases` | Stage 2 |
| Entitlement / subscription / "is premium" check | `Adapty.getProfile`, then the profile's access-level check | Stage 3 |
| Listeners: customer-info stream, delegate, purchase events | The platform's profile-update listener (delegate, stream, or event subscription) | Stage 3 |
| Attribution and analytics data the source forwarded | The matching Adapty integration | Stage 3.5 |
| Log level / debug logging | The `activate` configuration | Stage 1, and the Stage 5 checklist (never `verbose` in production) |
| Custom user attributes | Their Adapty counterparts | "Want to go further?" |

Then:

- **Code establishes what the app *uses*, never what exists in the source's account.** A missing call site is not evidence that an entity is missing: entitlements the app never names, offerings it never fetches, and a published visual-builder paywall attached to an offering it never requests all exist regardless — and that paywall still reserves its placement ID (section 3). Anything only the dashboard can settle goes to the verification checklist as an open question; never resolve it by reasoning from code.
- **Carry the never-create list into the handoff even when the code shows no trace of them.** Webhooks, audiences, targeting, and experiments (section 3) live only in the source's dashboard, so code silence says nothing about them. Write the checklist line either way — "nothing found in code, confirm in the dashboard" when that is the answer.
- **Take store product IDs only from code and config**, never from your own inference: constants files, `.storekit` configuration files, `Info.plist` / gradle / XML resources, and repo-checked-in remote config JSON. Nothing there → create no product, and defer with commands as in section 3.
- **Derive access levels from whatever the source calls entitlements.** No such concept → default `premium`, noted in `ADAPTY_SETUP.md`.
- **Record every entity you could not map instead of approximating it.** A source concept with no Adapty equivalent (a source-only wrapper type, a "purchases are completed by <source>" mode, a source-only store or web-billing target) is dropped and listed — never emulated, and never silently ported on a guess.
- **Remove the source SDK and every line that used it**, then grep the project for the source's symbols to confirm nothing executable remains. Leaving both SDKs initialized double-reports purchases.
- Keep the source's working UI. Swapping the SDK underneath a functioning custom paywall is the migration's job; replacing that UI is a separate decision the user has to ask for — and `paywallApproach == flow_builder` on a project whose paywall screen the app renders itself *is* them asking it. That combination is the one migration that retires the app's own UI, and it has its own sequence and its own hazards: read `references/migration-flow-rebuild.md` before you touch that screen or create a placement (section 7).

---

## 5. The `ADAPTY_SETUP.md` migration contract

`ADAPTY_SETUP.md` — the handoff document you leave in the project root — is the migration's real deliverable: the code is only the part a follow-up engineer can see. What you skipped, what you inferred, and what only they can do in a dashboard you had no access to exists only if it is written here. Alongside whatever else you record there, it must contain a **Migration** section with **all** of the subsections below. Each is mandatory even when its answer is "nothing to do" — write that sentence explicitly rather than dropping the subsection, so the reader can tell a considered no-op from an oversight.

**Write it for a reader who has no copy of this skill.** Two consequences, and they apply to every subsection:

- Never cite a `references/…` path in the document — those paths exist only inside your installed skill and a teammate cannot open them. Where a subsection below tells you to read one, read it yourself and write out what the reader needs.
- Docs links written into the document are for a human in a browser: plain `https://adapty.io/docs/<page>`, with no `.md` and **no `?ref=` tag**. The session marker belongs only on pages you fetch yourself.

**Disclose every inferred value.** Subsection 3 is its home, whatever your account access — it is the one subsection that is always present, and it covers entities you created on an inferred value as well as ones you skipped. An access level may instead go in subsection 2, where its mapping already lives. When subsection 1 applies, the values the user must compare against the source's dashboard also appear there as checkboxes. An inferred value is never allowed to reach the reader looking settled.

**In every ready-to-run command, an inferred value is a placeholder, not a literal** — `--developer-id "<PLACEMENT_ID>"`, never `--developer-id "main"` — with the confirm-it-first note beside the command. A command the reader can paste unchanged is exactly where a caveat in the surrounding prose stops protecting them.

1. **Verify against your `<source>` dashboard** — open the Migration section with this when you worked without access to the source's account, which is the default. The code was your only source and the account almost certainly holds entities you could not see. Concrete checkboxes:
   - Products you did NOT create because their store IDs were not in the code — include the ready-to-run `products create` commands with `<REAL_PRODUCT_ID>` slots.
   - Entitlements beyond the ones referenced in code.
   - Offerings and paywalls that exist only in the dashboard. Each needs a decision: recreate as placement + paywall, or rebuild as a flow if it used a visual paywall builder.
   - Offering metadata that should become paywall remote config.
   - Every identifier you inferred rather than recovered — above all any placement developer ID that stands in for an offering identifier not present in the code (section 3).

2. **Entitlement → access level mapping** — a row per source entitlement: source identifier, Adapty access level ID, and the file and line the name came from. Include the ones you skipped and why.

3. **Skipped entities and inferred identifiers, with exact manual steps** — two kinds of item, and this subsection always carries both:
   - **What you did not create**: the reserved "Rebuild as flows" placement IDs and their products; offering metadata destined for remote config; webhooks to re-point at Adapty; audiences, targeting, and experiments to recreate by hand. Ready-to-run commands wherever a command exists.
   - **What you did create on a value you inferred rather than recovered** — above all a placement whose developer ID stands in for an offering identifier that was not in the code (section 3). Give the value, why it was inferred, and what would confirm it. Being created is not a reason to leave it out; an unverified identifier in a working entity is exactly the one a reader would otherwise trust.

4. **Re-enter store credentials in Adapty** — they cannot be exported from the source system, so the user must supply them again: App Store In-App Purchase Key, and the Google Play service account key.

5. **Reconnect the stores and re-point server notifications at Adapty.** Non-negotiable, in every migration handoff, on every platform the app ships to. The source system holds this wiring for itself and **none of it transfers**: until it is redone, the app looks fully migrated and Adapty never receives a single renewal, cancellation, billing-retry, or refund. Two things, and say plainly that both are still outstanding:
   - Connect App Store Connect and/or Google Play to the **new Adapty app**.
   - Repoint **App Store Server Notifications** and **Google Play Real-Time Developer Notifications** at Adapty.

   Do not re-teach the steps in the document — link them, so they cannot drift. Write in these four public pages, for whichever stores the app ships to:

   - `https://adapty.io/docs/app-store-connection-configuration`
   - `https://adapty.io/docs/enable-app-store-server-notifications`
   - `https://adapty.io/docs/google-play-store-connection-configuration`
   - `https://adapty.io/docs/enable-real-time-developer-notifications-rtdn`

   To get the sequence right before you write it, read `references/testing-setup-ios.md` Part 2, `references/testing-setup-android.md` Part 2, and the platform reference's Stage 5 checklist — for you, not for the document.

   Write this subsection even when you had no store or dashboard access at all — especially then.

6. **Historical data import** — a decision the user has to make, so raise it even when you cannot act on it. State: import is not required for continuity of *access* — Adapty grants access levels and restores purchases for historical users as soon as they open a build with the Adapty SDK — **but that holds only for access that came from a store purchase**, because it is established from the store transaction history. Users whose access was granted outside the stores are not covered by it and need the separate backfill in subsection 8; do not reassure the reader about continuity without checking that first. Import is what gives the dashboard accurate historical analytics for an app with a meaningful transaction history. Two operational points that decide the timing:
   - **Wait about a week after the Adapty release before importing**, so the SDK has collected price data for the products involved.
   - The import is a CSV per store, handed to Adapty support. **Google purchase tokens are not in the app's code** — they come from an export requested from the source system's support or its data-export feature; Apple imports need the In-App Purchase Key already uploaded (subsection 4).

   Link the reader to `https://adapty.io/docs/importing-historical-data-to-adapty` for the file format and the request procedure.

7. **Re-point analytics and attribution integrations** — the source feeds the user's analytics and attribution tools today, and moving those integrations carelessly duplicates events. List the ones you found evidence of in the project, and link `https://adapty.io/docs/migrate-integrations-to-adapty`.

8. **Access granted outside the stores, by the user's own backend** — raise this even when you find no trace of it, because it is invisible in the app's code and it is the one omission that locks paying customers out on release day.

   Not all access comes from a store purchase. A web checkout, an invoice, a promo campaign, a support tool, or a B2B contract normally ends with the app's **own backend calling the source system's server API** to grant the entitlement. The mobile code shows nothing of this — the app simply reads an entitlement that something else set — so a call-site sweep of the app cannot find it and a diff will never reveal it.

   Two consequences, both severe:

   - **The grant path still points at the source, and it does not move itself.** Until that backend code is changed to grant an Adapty access level through Adapty's server-side API, every future out-of-band grant lands in a system the app no longer reads.
   - **Those users are not covered by automatic transfer.** Adapty establishes a historical user's access from their store transaction history. Access that never came from a store receipt has nothing to establish it from, so those users arrive with no access at all.

   So go looking rather than waiting: grep the project for calls to the source's REST API or server SDK, check whether any backend code is in the repo, and **ask the user outright whether any access is granted outside the stores** — the answer is often yes for apps that sell on the web. If it is yes, or unknown, put it at the top of the handoff, name `https://adapty.io/docs/grant-access-level` as the replacement mechanism, and state plainly that existing out-of-band users need a backfill before release.

---

## 6. When a call site does not map one-to-one

Read `references/migration-architecture.md` **on demand only** — when a source call site has no one-to-one Adapty equivalent and you need to decide how to restructure it. Do not load it by default; the rules above cover the mapping itself.

---

## 7. When the app's own paywall screen is being retired for a flow

Read `references/migration-flow-rebuild.md` **on demand only** — when `paywallApproach` is `flow_builder` and the project renders its paywall itself (layout, copy, and product list written by hand). It owns the sequence for that case, and two rules that override what you would otherwise do from this file: **no placement is created with the CLI until the flow it points at is published** (the flow needs that developer ID, and a paywall placement created on it blocks the flow placement with that ID — the same reservation as section 3's builder-paywall rule, reached by a different route), and the paywall screen's copy, assets, and locales are extracted into the handoff *before* any code changes, since the user rebuilds the screen in a visual editor from what you wrote down.

Do not load it on any other run. A migration that keeps the app's paywall UI — every `custom` and `observer` run, and every `flow_builder` run where the source's paywall came out of a visual builder rather than the app's own code — is fully covered by the sections above.

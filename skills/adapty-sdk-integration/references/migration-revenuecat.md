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

# Migration Reference: Architecture Decisions

Read this **on demand only** — when a source call site does not map one-to-one onto an Adapty
equivalent and you need to decide whether to swap it in place or restructure the surrounding code.
`references/migration.md` sends you here from its section 6; do not load this file by default and
do not read it before you hit such a call site. A headless run has no one to consult mid-decision,
so carrying judgment material you have not yet needed buys nothing — the spine's mapping rules cover
every call site that maps cleanly, which is most of them.

---

## Decision table: replace in place, or change structure

Every row is keyed to something you can point at in the code — a call site, a field, a listener.
None of them are keyed to how the code "feels." If you cannot cite the line that puts you in a row,
you are not in it yet.

| Observable condition in the code | Decision |
|---|---|
| The source call returns the same shape the app already consumes (a boolean, a single object, a list the app already iterates the same way) | **Replace in place.** Swap the SDK call for its Adapty equivalent (`references/migration.md` section 4) and leave the surrounding function, its signature, and its callers untouched. |
| Entitlement checks are scattered across many files, each hitting the source SDK directly | **Introduce one app-side wrapper and route every check through it** — do not edit each call site individually. Use `AdaptyService`, the same wrapper name every `references/<platform>.md` already recommends for a fresh integration (it's in `scripts/app-side-allowlist.txt` already); a migration is exactly the case that wrapper exists for. |
| The app caches or persists the source's customer-info object — or a field derived from it, refreshed by a listener — instead of reading it live | **Structure change.** Adapty's profile is the source of truth; the cache must go, and every read must go through `Adapty.getProfile` or the platform's profile-update listener (Stage 3 in `references/<platform>.md`). The recognizable shape: a singleton holding something like `bool entitlementIsActive` that a source-SDK callback writes into on every update — RevenueCat's MagicWeather sample does exactly this in `lib/src/model/singletons_data.dart`. The field name and the storage mechanism (singleton, global, `ChangeNotifier`, static) vary; the tell is a mirrored value plus a callback that refreshes it, not any specific name. |
| Paywall UI is coupled to the source's offering/package shape (renders by iterating the source's own offering or package objects, not a generic product list) | **Decide between a custom paywall fed by Adapty products and a Flow Builder rebuild** — this is not a coin flip, so read the evidence: bespoke layout, animation, or business logic the app's design cannot lose → keep the UI, feed it from `Adapty.getPaywallProducts` (Stage 2). A generic tier list with no logic that couldn't be reproduced in a visual builder → rebuild as a Flow (`Adapty.getFlow`, same stage), which is usually less code to migrate and lets `paywallApproach` land on `flow_builder`/`paywall_builder` per SKILL.md Phase 2 instead of `custom` by default. State which evidence you saw in `ADAPTY_SETUP.md` either way. Once the decision lands on a Flow rebuild, stop here and read `references/migration-flow-rebuild.md` — retiring the app's own paywall screen has a sequence and a set of hazards this table does not carry. |
| The app drives purchases through its own store code, with the source SDK only observing/reporting | This shape **is** Observer mode — SKILL.md Phase 2 already offers it as one of the three paywall approaches, limitations and all; do not re-derive that decision here. If `paywallApproach` is already `observer`, this is expected: keep the structure, and route only the tracking calls through Adapty per the platform reference's Observer mode section — no restructuring. If `paywallApproach` is something else, do not silently switch it; that choice belongs to the user, not to a call-site-level decision. Record the conflict in `ADAPTY_SETUP.md` instead — this is precisely the signal SKILL.md Phase 1 flags as "existing purchase code" without wiring it into the Phase 2 answer, so surfacing it here is the only place it currently gets surfaced. |

---

## What NOT to restructure

The migration's job is a working, verifiable swap — not a rewrite. Once a row above tells you a
call site needs restructuring, restructure *that* call site and stop. Do not refactor code the
migration does not touch, reformat files you're already editing beyond what the change requires, or
"improve" architecture that has nothing to do with the source SDK. This mirrors the CLI's
smallest-set-of-edits rule and keeps `git diff` reviewable by someone who wasn't in the room: every
line changed should be traceable to a source call site or its direct consequence, not to taste.

---

## How to record a structure change

Any decision made from the table above — which row, what you changed, and why — goes in
`ADAPTY_SETUP.md`'s Migration section (`references/migration.md` section 5), next to the entity or
mapping it affects: a rebuilt-as-flow paywall beside that placement's entry, a wrapper introduced for
entitlement checks beside the access-level mapping it now serves. State the evidence you saw, not
just the conclusion, so a reviewer who wasn't there can disagree with the call without re-reading the
whole diff.

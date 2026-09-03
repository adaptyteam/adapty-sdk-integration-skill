# Migration Reference: RevenueCat — Identity and profile lifecycle

Read this **on demand only**, when a row in `references/migration-revenuecat.md` section 5's triage
table points here. It assumes the spine's rules (`references/migration.md`) and takes every code
signature from `references/<platform>.md` — nothing below is a snippet, because these divergences are
behavioral and the call you need is per-platform.

---

RevenueCat has one identifier for a user. Adapty has two, and they are not interchangeable: a
`profileId` Adapty issues and owns, and a `customerUserId` your app supplies. Every divergence in this
section follows from that split.

**`logIn` returned values are gone.** RC's `logIn` hands back the customer info and a flag saying
whether the user was newly created. `Adapty.identify` returns neither. Code shaped as "log in, then
immediately branch on the returned entitlements" has to become "identify, then read the profile" —
`Adapty.getProfile`, or the profile-update listener at Stage 3 of `references/<platform>.md`. The
was-created flag has no equivalent at all: if the app used it to trigger onboarding or a first-run
grant, that signal must come from the app's own storage instead. Say so in `ADAPTY_SETUP.md` when you
replace it, because you are substituting a different source of truth, not translating a call.

**Re-identifying depends on whether Adapty already knows the ID, and one branch loses an identity.**
RC's `logIn` sends both the old and the new user ID to its backend and lets the server resolve them.
Adapty's `identify` sends the **profile ID you are already on** together with the new customer user ID
— the client deliberately reuses the current profile ID rather than starting a new profile — and the
server then decides one of two things:

- **The customer user ID is already known.** You are switched onto that existing profile. The server
  returns a different profile ID and the SDK follows it. Adapty's docs put it plainly: the SDK "will
  automatically switch to work with the new user."
- **The customer user ID is new.** The profile you are already on becomes that user. If you were
  anonymous, that is exactly what you wanted. If you were already identified as somebody else, the
  previous customer user ID is gone from that profile.

That second branch is the one that costs you. An app that switches between accounts — a
client-management tool, a "log in as" affordance, a shared tablet — must not identify straight from one
user to another. Call `Adapty.logout` first, then `Adapty.identify`.

**But do not call logout unconditionally.** Both SDKs refuse it for an anonymous user: RC returns a
log-out-anonymous-user error and Adapty throws its own equivalent. So the guard is part of the change —
log out only when a customer user ID is currently set. An RC codebase that never switched accounts has
no such guard to copy, which makes this new code rather than moved code.

Grep every `logIn` call site before deciding this does not apply. A single login screen that runs once
per install is safe; a login that can run again with a different user is not. Record which case you
found in `ADAPTY_SETUP.md` — a reviewer cannot tell from the diff which one you concluded.

**Data on the anonymous profile does not carry over, and RC quietly carried some of it.** RC copies the
old user's subscriber attributes to the new user, but **only when the old user was anonymous** — that
narrow case is the whole of RC's automatic transfer, not a general merge, and switching between two
identified users copies nothing in either SDK.

Adapty copies nothing at all. Its docs are explicit: if you passed data to the anonymous user, "such as
custom attributes or attributions from third-party networks, you should resubmit that data for the
identified user." So the app has to re-send, after `Adapty.identify` succeeds, whatever it set on the
anonymous profile. Its existing code almost certainly does not, because under RC that case was handled
for it.

**Re-request paywalls and products after identifying.** Adapty's docs require it — "you should
re-request all paywalls and products after identifying the user, as the new user's data may be
different" — because the identified user can fall into different audiences and see different paywalls.
RC needed no such step: it refreshes its own offerings cache at configure and on every foreground
(see `migration-revenuecat-placements.md`), so a mid-session `logIn` was followed by a refresh the
app never wrote.

This is easy to miss precisely because nothing looks broken: the app keeps showing the paywall it
already had, which is the *anonymous* user's paywall. Any A/B test or audience targeting keyed to the
identified user silently does not apply. Re-fetch the placement after identify and rebuild whatever
the app cached from the previous fetch.

**`logout` returns nothing.** RC's `logOut` returns the fresh customer info for the new anonymous user;
`Adapty.logout` returns nothing. Same fix as `logIn`: read the profile afterward if the app needs it.
Both SDKs do create a new anonymous user on logout, so that behavior needs no change.

**An empty user ID is rejected by RC and is not rejected by Adapty.** RC fails the call with a
missing-app-user-ID error when the trimmed ID is empty. Adapty trims and proceeds. So a code path that
was safe because RC refused it — identifying from a not-yet-populated field, a nullable backend value
coerced to `""` — now goes through. If the app relied on that rejection as validation, the check moves
into the app.

Adapty's own page for this: `https://adapty.io/docs/identifying-users`

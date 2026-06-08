# App ID Collection for Feedback — Design

**Date:** 2026-06-08
**Status:** Approved (pending spec review)

## Problem

The `adapty-sdk-integration` skill collects optional, anonymous feedback at the
end of an integration session. Today the feedback is deliberately
non-identifying — the Phase 0 consent promises *"no code, no project details,
nothing identifying."*

We want to additionally collect the user's **Adapty app ID** and send it with
the feedback, so the Adapty team can tie a session to a specific app and help
faster if the user runs into issues. Constraints:

- **No additional permission requests** — reuse the single existing consent gate
  in Phase 0; no second prompt.
- **Smart, honest positioning** — the app ID should read as a support perk for
  the user, not as tracking. Framed as a *reactive support* benefit ("the team
  can help you faster if you ever need a hand").

## Key insight

The app ID is **already captured** — `appId` is an existing state variable set
in Phase 3 from the `adapty apps list` / `apps create` CLI output. Nothing new
needs to be collected from the user or the CLI. This work is:

1. Rewording the Phase 0 consent so it covers the app ID honestly and positions
   it well.
2. Including the already-captured `appId` in the Phase 5 delivery payload.

Because consent is asked in Phase 0 (before the app ID exists in Phase 3), the
consent references "your app ID" generically, and the actual value is attached
at delivery time in Phase 5.

## Approach

**Reframe the existing Phase 0 consent; attach `appId` at Phase 5 delivery.**

Rejected alternative: a second touch in Phase 3 (when the app ID is first
known). It is the natural moment the ID appears, but it adds a second prompt,
which the constraint explicitly forbids. The single Phase 0 gate is kept.

## Changes

### 1. Phase 0 consent copy (`SKILL.md`)

Replace the current consent text. It drops "nothing identifying" (no longer
true), keeps the honest "no code, no project details," and positions the app ID
as a reactive-support perk. Remains a **single yes/no `AskUserQuestion`** — app
ID is bundled into the same consent, with no separate opt-out.

**New copy:**

> "Mind if I share quick feedback with the Adapty team when we finish? Just a
> rating, a few signals (platform, steps completed), and your Adapty app ID —
> no code or project details. The app ID just lets the team help you faster if
> you ever need a hand. Sound good?"

- **Yes** → `feedbackEnabled = true` (unchanged downstream: the same permission
  pre-approval script runs; no new permissions are needed because `app_id`
  rides along in the existing POST).
- **No** → `feedbackEnabled = false`; nothing is sent, including the app ID.

### 2. Phase 5 delivery (`SKILL.md`)

- Add `"app_id": "APP_ID"` to the curl JSON body (value from the `appId` state
  variable).
- Append ` · App: APP_ID` to `slack_text`, **only when `appId` is set**.
- If `appId` is empty (user abandoned before Phase 3), send `"app_id": null`
  and omit the `· App:` suffix from `slack_text`.

### 3. Endpoint (`feedback-endpoint/api/sdk-integration-feedback.js`)

- Destructure `app_id` from the request body.
- Add `app_id: app_id ?? null` to the Airtable `fields` object.
- Slack needs no change — the app ID already arrives inside `slack_text`.

### 4. Airtable schema (manual, dashboard side)

- Add an `app_id` column (single-line text) to the feedback table. Done in the
  Airtable UI, outside this repo.

### 5. Endpoint README (`feedback-endpoint/README.md`)

- Update the example payload to include `"app_id"`.

## Data flow

```
Phase 0:  consent (single yes/no)  ── feedbackEnabled
Phase 3:  adapty apps list/create  ── appId  (already captured today)
Phase 5:  POST { ...signals, app_id } ──► endpoint
                                            ├─► Slack  (app_id shown via slack_text)
                                            └─► Airtable (app_id column)
```

## Edge cases

| Case | Behavior |
|---|---|
| Consent declined | Nothing sent; app ID not collected for delivery. |
| Abandoned before Phase 3 (no app ID) | `app_id: null`; `· App:` suffix omitted from Slack text. |
| New app created in Phase 3 | `appId` is set from `apps create` output; sent normally. |

## Out of scope (YAGNI)

- App title / any second field — app ID only.
- A separate opt-out for the app ID — it is bundled into the single consent.
- Any change to permission pre-approval — the app ID rides the existing POST.
- Backfilling or de-anonymizing past feedback records.

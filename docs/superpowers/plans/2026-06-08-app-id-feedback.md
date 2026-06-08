# App ID Collection for Feedback — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Attach the user's already-captured Adapty app ID to end-of-session feedback, framed as a reactive-support perk, without adding any new permission prompt.

**Architecture:** The `appId` is already captured in Phase 3 of `SKILL.md`. This plan (1) reworks the Phase 0 consent copy to honestly cover the app ID and position it as a support perk, (2) adds `app_id` to the Phase 5 delivery payload and the Slack text, (3) forwards `app_id` into the Airtable record in the serverless endpoint, and (4) adds the matching Airtable column + redeploys.

**Tech Stack:** Markdown skill file (`SKILL.md`), a single Vercel ESM serverless function (`sdk-integration-feedback.js`), Node's built-in test runner (`node --test`, no new dependencies), Airtable, Slack webhook.

**Spec:** `docs/superpowers/specs/2026-06-08-app-id-feedback-design.md`

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `feedback-endpoint/api/sdk-integration-feedback.js` | Receives feedback POST, forwards to Slack + Airtable | Destructure `app_id`, write it to Airtable `fields` |
| `feedback-endpoint/test/endpoint.test.js` | Verifies the endpoint forwards `app_id` correctly | **Create** (node:test, no deps) |
| `plugins/adapty-sdk-integration/skills/adapty-sdk-integration/SKILL.md` | The skill instructions | Phase 0 consent copy + Phase 5 payload/slack_text |
| `feedback-endpoint/README.md` | Endpoint docs | Update example payload |
| Airtable table (external) | Stores structured feedback | Add `app_id` column (manual) |

---

## Task 1: Endpoint — forward `app_id` to Airtable (TDD)

**Files:**
- Create: `feedback-endpoint/test/endpoint.test.js`
- Modify: `feedback-endpoint/api/sdk-integration-feedback.js` (the destructure block ~lines 15-25 and the Airtable `fields` object ~lines 44-55)

The endpoint reads env vars *inside* the `POST` handler (not at import time), so the test sets env + stubs `globalThis.fetch` and asserts on the recorded Airtable request body. Node's `Response` and `fetch` globals are used (Node 18+).

- [ ] **Step 1: Write the failing test**

Create `feedback-endpoint/test/endpoint.test.js`:

```js
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { POST } from '../api/sdk-integration-feedback.js';

// The handler reads these inside POST(), so setting them at module scope
// (before any test runs) is sufficient.
process.env.SLACK_WEBHOOK_URL = 'https://hooks.slack.com/services/TEST';
process.env.AIRTABLE_PAT = 'pat_test';
process.env.AIRTABLE_BASE_ID = 'appTEST';
process.env.AIRTABLE_TABLE = 'Table 1';

// Build a minimal Request-like object: the handler only calls req.json().
function makeReq(body) {
  return { json: async () => body };
}

// Replace global fetch with a recorder that always succeeds.
function stubFetch() {
  const calls = [];
  globalThis.fetch = async (url, opts) => {
    calls.push({ url, opts });
    return { ok: true };
  };
  return calls;
}

// Find the Airtable call among recorded fetches and return its parsed body.
function airtableBody(calls) {
  const call = calls.find((c) => String(c.url).includes('airtable.com'));
  assert.ok(call, 'expected an Airtable fetch call');
  return JSON.parse(call.opts.body);
}

test('app_id is forwarded into the Airtable fields when present', async () => {
  const calls = stubFetch();
  const res = await POST(
    makeReq({
      platform: 'ios',
      paywall_approach: 'paywall_builder',
      integrations: 'amplitude',
      phases_completed: 4,
      checkpoints_passed: 5,
      friction_rounds: 0,
      sentiment: 'positive',
      rating: 4,
      app_id: 'a1b2c3d4',
      slack_text: 'x',
    })
  );
  assert.equal(res.status, 200);
  assert.equal(airtableBody(calls).fields.app_id, 'a1b2c3d4');
});

test('app_id defaults to null when omitted', async () => {
  const calls = stubFetch();
  const res = await POST(
    makeReq({
      platform: 'ios',
      slack_text: 'x',
    })
  );
  assert.equal(res.status, 200);
  assert.equal(airtableBody(calls).fields.app_id, null);
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run:
```bash
cd feedback-endpoint && node --test
```
Expected: the `app_id is forwarded...` test FAILS — `airtableBody(calls).fields.app_id` is `undefined`, not `'a1b2c3d4'` (the handler does not yet read `app_id`). The null test may pass coincidentally (`undefined !== null` → it also fails). At least one assertion failure is expected.

- [ ] **Step 3: Add `app_id` to the destructure block**

In `feedback-endpoint/api/sdk-integration-feedback.js`, change the destructure block from:

```js
  const {
    platform,
    paywall_approach,
    integrations,
    phases_completed,
    checkpoints_passed,
    friction_rounds,
    sentiment,
    rating,
    slack_text,
  } = await req.json();
```

to (add `app_id,`):

```js
  const {
    platform,
    paywall_approach,
    integrations,
    phases_completed,
    checkpoints_passed,
    friction_rounds,
    sentiment,
    rating,
    app_id,
    slack_text,
  } = await req.json();
```

- [ ] **Step 4: Add `app_id` to the Airtable `fields` object**

In the same file, change the Airtable `fields` object from:

```js
        fields: {
          platform,
          paywall_approach,
          integrations,
          phases_completed,
          checkpoints_passed,
          friction_rounds,
          sentiment,
          rating: rating ?? null,
        },
```

to (add the `app_id` line):

```js
        fields: {
          platform,
          paywall_approach,
          integrations,
          phases_completed,
          checkpoints_passed,
          friction_rounds,
          sentiment,
          rating: rating ?? null,
          app_id: app_id ?? null,
        },
```

- [ ] **Step 5: Run the test to verify it passes**

Run:
```bash
cd feedback-endpoint && node --test
```
Expected: both tests PASS (`# pass 2`, `# fail 0`).

- [ ] **Step 6: Commit**

```bash
git add feedback-endpoint/api/sdk-integration-feedback.js feedback-endpoint/test/endpoint.test.js
git commit -m "feat: forward app_id from feedback endpoint to Airtable"
```

---

## Task 2: SKILL.md — reword the Phase 0 consent

**Files:**
- Modify: `plugins/adapty-sdk-integration/skills/adapty-sdk-integration/SKILL.md` (the "Feedback consent" block under Phase 0, ~lines 57-61)

- [ ] **Step 1: Replace the consent copy**

Find this blockquote under `### Feedback consent`:

```
> "Would you like to share anonymous feedback when we're done? It's just a quick rating + a few signals (platform, steps completed) — no code, no project details, nothing identifying. Helps the Adapty team improve this guide."
```

Replace it with:

```
> "Mind if I share quick feedback with the Adapty team when we finish? Just a rating, a few signals (platform, steps completed), and your Adapty app ID — no code or project details. The app ID just lets the team help you faster if you ever need a hand. Sound good?"
```

Leave the surrounding `AskUserQuestion`, the yes/no branches, and the permission pre-approval script unchanged — it remains a single yes/no gate, and no new permissions are needed (the app ID rides the existing POST).

- [ ] **Step 2: Verify the change**

Run:
```bash
grep -c "lets the team help you faster" plugins/adapty-sdk-integration/skills/adapty-sdk-integration/SKILL.md
grep -c "nothing identifying" plugins/adapty-sdk-integration/skills/adapty-sdk-integration/SKILL.md
```
Expected: first prints `1`, second prints `0` (the old "nothing identifying" wording is gone).

- [ ] **Step 3: Commit**

```bash
git add plugins/adapty-sdk-integration/skills/adapty-sdk-integration/SKILL.md
git commit -m "feat: reword Phase 0 consent to cover app ID as a support perk"
```

---

## Task 3: SKILL.md — add `app_id` to Phase 5 delivery

**Files:**
- Modify: `plugins/adapty-sdk-integration/skills/adapty-sdk-integration/SKILL.md` (Phase 5 "Steps 3 & 4: Send feedback", the curl template ~lines 423-427, the explanatory lines ~lines 429-431, and the real-values example ~lines 434-437)

- [ ] **Step 1: Update the curl template**

Find the template curl command:

```bash
curl -s -X POST "https://feedback-endpoint-eandreeva-twrs-projects.vercel.app/api/sdk-integration-feedback" \
  -H "Content-Type: application/json" \
  -d "{\"platform\": \"PLATFORM\", \"paywall_approach\": \"PAYWALL_APPROACH\", \"integrations\": \"INTEGRATIONS_STRING\", \"phases_completed\": PHASES_COMPLETED, \"checkpoints_passed\": CHECKPOINTS_PASSED, \"friction_rounds\": FRICTION_ROUNDS, \"sentiment\": \"SENTIMENT\", \"rating\": RATING_OR_NULL, \"slack_text\": \"[PLATFORM · PAYWALL_APPROACH] Phase PHASES_COMPLETED ✓ · Rating: RATING/5 · Sentiment: SENTIMENT · FRICTION_ROUNDS friction rounds\"}"
```

Replace it with (adds `app_id` before `slack_text`, and ` · App: APP_ID` inside `slack_text`):

```bash
curl -s -X POST "https://feedback-endpoint-eandreeva-twrs-projects.vercel.app/api/sdk-integration-feedback" \
  -H "Content-Type: application/json" \
  -d "{\"platform\": \"PLATFORM\", \"paywall_approach\": \"PAYWALL_APPROACH\", \"integrations\": \"INTEGRATIONS_STRING\", \"phases_completed\": PHASES_COMPLETED, \"checkpoints_passed\": CHECKPOINTS_PASSED, \"friction_rounds\": FRICTION_ROUNDS, \"sentiment\": \"SENTIMENT\", \"rating\": RATING_OR_NULL, \"app_id\": APP_ID_OR_NULL, \"slack_text\": \"[PLATFORM · PAYWALL_APPROACH] Phase PHASES_COMPLETED ✓ · Rating: RATING/5 · Sentiment: SENTIMENT · FRICTION_ROUNDS friction rounds · App: APP_ID\"}"
```

- [ ] **Step 2: Update the explanatory lines**

Find these lines immediately after the template:

```
`INTEGRATIONS_STRING` is a comma-separated string of integration keys, e.g. `amplitude, appsflyer` or left empty.
`RATING_OR_NULL` is the numeric rating (e.g. `4`) or `null` if not collected.
If `rating` is null, omit `· Rating: RATING/5` from `slack_text`.
```

Replace with (adds the two app_id lines):

```
`INTEGRATIONS_STRING` is a comma-separated string of integration keys, e.g. `amplitude, appsflyer` or left empty.
`RATING_OR_NULL` is the numeric rating (e.g. `4`) or `null` if not collected.
If `rating` is null, omit `· Rating: RATING/5` from `slack_text`.
`APP_ID_OR_NULL` is the `appId` state value as a quoted string (e.g. `"a1b2c3d4"`), or `null` if it was never captured (user abandoned before Phase 3).
If `appId` is empty/null, send `"app_id": null` and omit ` · App: APP_ID` from `slack_text`.
```

- [ ] **Step 3: Update the real-values example**

Find the example block with real values:

```bash
curl -s -X POST "https://feedback-endpoint-eandreeva-twrs-projects.vercel.app/api/sdk-integration-feedback" \
  -H "Content-Type: application/json" \
  -d '{"platform": "ios", "paywall_approach": "paywall_builder", "integrations": "amplitude, appsflyer", "phases_completed": 4, "checkpoints_passed": 5, "friction_rounds": 0, "sentiment": "positive", "rating": 4, "slack_text": "[ios · paywall_builder] Phase 4 ✓ · Rating: 4/5 · Sentiment: positive · 0 friction rounds"}'
```

Replace it with (adds `app_id` and the `· App:` suffix):

```bash
curl -s -X POST "https://feedback-endpoint-eandreeva-twrs-projects.vercel.app/api/sdk-integration-feedback" \
  -H "Content-Type: application/json" \
  -d '{"platform": "ios", "paywall_approach": "paywall_builder", "integrations": "amplitude, appsflyer", "phases_completed": 4, "checkpoints_passed": 5, "friction_rounds": 0, "sentiment": "positive", "rating": 4, "app_id": "a1b2c3d4", "slack_text": "[ios · paywall_builder] Phase 4 ✓ · Rating: 4/5 · Sentiment: positive · 0 friction rounds · App: a1b2c3d4"}'
```

- [ ] **Step 4: Verify the change**

Run:
```bash
grep -c "app_id" plugins/adapty-sdk-integration/skills/adapty-sdk-integration/SKILL.md
grep -c "APP_ID_OR_NULL" plugins/adapty-sdk-integration/skills/adapty-sdk-integration/SKILL.md
```
Expected: first prints `3` (template + example + one explanatory mention via `"app_id": null`), second prints `2` (template + explanatory line). If counts differ, re-check the three edits above were all applied.

- [ ] **Step 5: Commit**

```bash
git add plugins/adapty-sdk-integration/skills/adapty-sdk-integration/SKILL.md
git commit -m "feat: include app_id in Phase 5 feedback payload and Slack text"
```

---

## Task 4: README — update the example payload

**Files:**
- Modify: `feedback-endpoint/README.md` (the JSON example under `## Endpoint`, ~lines 31-43)

- [ ] **Step 1: Update the example JSON**

Find:

```json
{
  "platform": "ios",
  "paywall_approach": "paywall_builder",
  "integrations": "amplitude, appsflyer",
  "phases_completed": 4,
  "checkpoints_passed": 5,
  "friction_rounds": 0,
  "sentiment": "positive",
  "rating": 4,
  "slack_text": "[ios · paywall_builder] Phase 4 ✓ · Rating: 4/5 · Sentiment: positive · 0 friction rounds"
}
```

Replace with (adds `app_id` and the `· App:` suffix in `slack_text`):

```json
{
  "platform": "ios",
  "paywall_approach": "paywall_builder",
  "integrations": "amplitude, appsflyer",
  "phases_completed": 4,
  "checkpoints_passed": 5,
  "friction_rounds": 0,
  "sentiment": "positive",
  "rating": 4,
  "app_id": "a1b2c3d4",
  "slack_text": "[ios · paywall_builder] Phase 4 ✓ · Rating: 4/5 · Sentiment: positive · 0 friction rounds · App: a1b2c3d4"
}
```

- [ ] **Step 2: Verify the change**

Run:
```bash
grep -c '"app_id"' feedback-endpoint/README.md
```
Expected: prints `1`.

- [ ] **Step 3: Commit**

```bash
git add feedback-endpoint/README.md
git commit -m "docs: add app_id to feedback endpoint example payload"
```

---

## Task 5: Add Airtable column, deploy, end-to-end verify (manual)

**This task is manual — no code, but required for the field to actually persist.** The Airtable column MUST exist *before* sending, or Airtable silently drops the unknown field.

- [ ] **Step 1: Add the Airtable column**

In the Airtable base/table referenced by `AIRTABLE_BASE_ID` / `AIRTABLE_TABLE`:
- Click the **+** at the right end of the column headers.
- Field name: `app_id` (exactly — lowercase, underscore; must match the JSON key).
- Field type: **Single line text**.
- Create.

- [ ] **Step 2: Deploy the endpoint**

```bash
cd feedback-endpoint && npx vercel deploy --prod
```
Expected: deploy succeeds and reports the production URL (the stable alias `https://feedback-endpoint-eandreeva-twrs-projects.vercel.app` remains valid).

- [ ] **Step 3: Send a live test request**

```bash
curl -s -X POST "https://feedback-endpoint-eandreeva-twrs-projects.vercel.app/api/sdk-integration-feedback" \
  -H "Content-Type: application/json" \
  -d '{"platform": "ios", "paywall_approach": "paywall_builder", "integrations": "", "phases_completed": 4, "checkpoints_passed": 5, "friction_rounds": 0, "sentiment": "positive", "rating": 5, "app_id": "e2e-test-app-id", "slack_text": "[e2e test] app_id verification · App: e2e-test-app-id"}'
```
Expected: response is `{"ok":true}`.

- [ ] **Step 4: Confirm delivery**

- Airtable: a new row appears with `app_id` = `e2e-test-app-id`.
- Slack: a message appears containing `App: e2e-test-app-id`.

If the Airtable `app_id` cell is empty but the row was created, the column name does not match exactly — re-check Step 1.

- [ ] **Step 5: (Optional) clean up the test row** in Airtable so it doesn't pollute real feedback data.

---

## Self-Review

**Spec coverage:**
- Phase 0 consent reword → Task 2 ✓
- `app_id` in Phase 5 payload + Slack text → Task 3 ✓
- Endpoint forwards `app_id` to Airtable → Task 1 ✓
- Airtable `app_id` column → Task 5, Step 1 ✓
- README example update → Task 4 ✓
- Edge case `app_id: null` when abandoned → covered by Task 1 (null test) + Task 3 (Step 2 instruction) ✓
- "No additional permission requests" → Task 2 keeps the single gate and existing pre-approval script ✓

**Placeholder scan:** No TBD/TODO. `PLATFORM`, `APP_ID_OR_NULL`, etc. are the SKILL.md template tokens (intentional, defined in the explanatory lines).

**Type/name consistency:** Field key is `app_id` everywhere (endpoint destructure, Airtable `fields`, SKILL.md payload, README, Airtable column, test assertions). Slack suffix is ` · App: ` everywhere.

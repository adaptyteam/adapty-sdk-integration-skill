# Adapty SDK Integration — Feedback Endpoint

A single Vercel serverless function that receives session feedback from the
`adapty-sdk-integration` Claude skill and forwards it to Slack and Airtable.

## Deploy

**Add the `migration_source` column to the Airtable table first.** The handler sends
`migration_source` on every request — a source name on a migration run, `null` on a greenfield one —
and Airtable rejects a write naming a field the table does not have with HTTP 422, rejecting the
*whole* record rather than the unknown field. Deploying before the column exists therefore drops
every feedback submission, greenfield ones included, not just migration ones. Create the column
(single line text), then deploy.

1. `cd` into this directory and run:
   ```bash
   npx vercel deploy --prod
   ```

2. Set the following environment variables in the Vercel dashboard
   (Project → Settings → Environment Variables):

   | Variable | Value |
   |---|---|
   | `SLACK_WEBHOOK_URL` | Your Slack Incoming Webhook URL |
   | `AIRTABLE_PAT` | Airtable Personal Access Token (scope: `data.records:write`) |
   | `AIRTABLE_BASE_ID` | Airtable Base ID (starts with `app`) |
   | `AIRTABLE_TABLE` | Table name inside the base (e.g. `Table 1`) |

3. The stable production URL is:
   `https://feedback-endpoint-eandreeva-twrs-projects.vercel.app/api/sdk-integration-feedback`
   This is already set in SKILL.md. Update it if the project is redeployed under a different team.

## Endpoint

`POST /api/sdk-integration-feedback`

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
  "migration_source": null,
  "slack_text": "[ios · paywall_builder] Phase 4 ✓ · Rating: 4/5 · Sentiment: positive · 0 friction rounds · App: a1b2c3d4"
}
```

`migration_source` is the source system a migration run replaced (e.g. `"revenuecat"`), or `null` for
a greenfield integration.

Returns `{"ok": true}` when both deliveries returned a 2xx, and
`{"error": "Failed: <destinations>"}` with HTTP 500 otherwise — including when a delivery completed
but answered non-2xx.

Refused before anything is delivered: HTTP 415 for a content type other than `application/json`,
413 for a body over 16 KB, 400 for a body that is not parseable JSON or is not an object.

## Validation

The endpoint is public and cannot be authenticated — the skill runs on the user's machine, so any
embedded token would be public by definition. Validation is therefore part of the defense, and the
sharpest edge is `slack_text`: it reaches an Adapty Slack channel verbatim, so without sanitising it
anyone who learns the URL can post arbitrary text there, mention syntax included.

`src/validate.js` clamps rather than rejects, because a telemetry endpoint that answers 400 for an
unexpected value just loses real events:

| Field | Rule |
|---|---|
| `platform`, `paywall_approach`, `migration_source` | `[A-Za-z0-9_.-]` only, 32 chars; empty result → `null` |
| `sentiment` | same, 16 chars |
| `app_id` | same, 64 chars |
| `integrations` | free text, control characters and `<>` removed, 200 chars |
| `slack_text` | free text, same treatment, 500 chars |
| `rating` | integer 1–5, else `null` |
| `phases_completed`, `checkpoints_passed`, `friction_rounds` | integer 0–1000, else `null` |

Non-ASCII survives — real messages are full of `·` and `✓`. Angle brackets do not, which is what
neuters `<!channel>`. Unknown keys never reach Airtable: the delivered object is built field by
field, never spread. Deliberately **not** an allowlist of known platforms or approaches: a new value
would then start failing until the endpoint was redeployed, the same deploy-order trap as an Airtable
column that does not exist yet.

Rate limiting belongs in front of the endpoint (Cloudflare WAF), not here — it should reject before
our compute runs. What only we can know is the schema, which is why the shape checks live in code.

## Tests

```bash
node --test test/endpoint.test.js
```

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

## Tests

```bash
node --test test/endpoint.test.js
```

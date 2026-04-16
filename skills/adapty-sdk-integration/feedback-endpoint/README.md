# Adapty SDK Integration — Feedback Endpoint

A single Vercel serverless function that receives anonymous feedback from the
`adapty-sdk-integration` Claude skill and forwards it to Slack and Airtable.

## Deploy

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
  "slack_text": "[ios · paywall_builder] Phase 4 ✓ · Rating: 4/5 · Sentiment: positive · 0 friction rounds"
}
```

Returns `{"ok": true}` on success.

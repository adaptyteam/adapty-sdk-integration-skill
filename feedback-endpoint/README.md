# Adapty SDK Integration — Feedback Endpoint

Receives session feedback from the `adapty-sdk-integration` skill and from the
Adapty CLI (`adapty integrate` / `adapty migrate`), and forwards it to Slack and Airtable.

One implementation, two deployments:

| File | Runs on | Role |
|---|---|---|
| `src/validate.js` | both | Reads and clamps the body; owns what is refused outright |
| `src/deliver.js` | both | Fans the payload out to Slack and Airtable; owns what counts as a failure |
| `src/handler.js` | both | Request in, response out: validate, then deliver |
| `src/index.js` | Cloudflare Workers | The deployment we run |
| `api/sdk-integration-feedback.js` | Vercel | Legacy address, kept alive for published skill versions |

## Why both

The Vercel URL is baked into skill versions that are already installed and into
published CLI builds. They keep sending there for as long as they exist, so that
address cannot be retired — but it also should not be a second implementation.
Setting `FORWARD_URL` on the Vercel deployment turns it into a relay: it passes
the request to the Worker verbatim and returns the Worker's verdict unchanged.
Credentials, validation and delivery logic then live in one place.

## Deploy (Cloudflare Workers)

**Add any new Airtable column before deploying code that sends it.** Airtable
answers HTTP 422 for a field the table does not have and rejects the *whole*
record, so a deploy that runs ahead of the column drops every submission, not
just the ones carrying the new field. Order is always: column → Worker → senders.

```bash
cd feedback-endpoint
npx wrangler secret put SLACK_WEBHOOK_URL   # Slack Incoming Webhook URL
npx wrangler secret put AIRTABLE_PAT        # Airtable PAT, scope data.records:write
npx wrangler secret put AIRTABLE_BASE_ID    # starts with "app"
npx wrangler secret put AIRTABLE_TABLE      # table name inside the base
npx wrangler deploy
```

Routine changes do not need any of that: merging to `main` deploys the Worker
through `.github/workflows/feedback-endpoint-deploy.yml`, which needs two repo
secrets — `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID`. Without them the
workflow runs the tests and skips the deploy, so it is safe before provisioning.

The route lives in `wrangler.toml`, commented out until the hostname exists. Both
`/sdk-integration-feedback` and `/api/sdk-integration-feedback` are served, so the
relay can forward the legacy path unchanged.

## Cutover

1. Deploy the Worker and confirm a POST reaches Slack and Airtable.
2. Point new senders at the Worker URL: `SKILL.md` in this repo, and
   `DEFAULT_ENDPOINT` in the Adapty CLI's `src/lib/agent/telemetry.ts`.
3. Set `FORWARD_URL` on the Vercel deployment to the Worker URL. Old clients
   keep working; nothing else about that project needs to change.
4. Leave the Vercel deployment running. It costs nothing and it is the only
   thing serving already-installed versions.

## Endpoint

`POST /sdk-integration-feedback` (also `/api/sdk-integration-feedback`)

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
a greenfield integration. The CLI sends a subset of these fields; missing ones land as `null`.

Returns `{"ok": true}` when both deliveries returned a 2xx,
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

No network: `fetch` is stubbed and the credentials are passed in as an argument,
the same way the Worker receives its bindings.

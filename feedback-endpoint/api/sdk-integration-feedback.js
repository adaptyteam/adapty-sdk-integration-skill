/**
 * Adapty SDK Integration Skill — Feedback Endpoint
 *
 * Accepts session feedback from the adapty-integration Claude skill
 * and forwards it to Slack and Airtable.
 *
 * The body is validated before anything leaves here (see src/validate.js):
 * the endpoint is public and unauthenticatable, and `slack_text` reaches an
 * Adapty Slack channel verbatim.
 *
 * Environment variables (set in Vercel dashboard):
 *   SLACK_WEBHOOK_URL   — Slack Incoming Webhook URL
 *   AIRTABLE_PAT        — Airtable Personal Access Token (data.records:write)
 *   AIRTABLE_BASE_ID    — Airtable Base ID (e.g. appXXXXXXXXXXXXXX)
 *   AIRTABLE_TABLE      — Airtable table name (e.g. Table 1)
 */
import { readFeedback } from '../src/validate.js';

export async function POST(req) {
  const result = await readFeedback(req);
  if (!result.ok) {
    return Response.json({ error: result.error }, { status: result.status });
  }

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
    migration_source,
    slack_text,
  } = result.payload;

  const { SLACK_WEBHOOK_URL, AIRTABLE_PAT, AIRTABLE_BASE_ID, AIRTABLE_TABLE } = process.env;

  const results = await Promise.allSettled([
    // Slack
    fetch(SLACK_WEBHOOK_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: slack_text }),
    }),

    // Airtable
    fetch(`https://api.airtable.com/v0/${AIRTABLE_BASE_ID}/${encodeURIComponent(AIRTABLE_TABLE)}`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${AIRTABLE_PAT}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        fields: {
          platform,
          paywall_approach,
          integrations,
          phases_completed,
          checkpoints_passed,
          friction_rounds,
          sentiment,
          rating,
          app_id,
          migration_source,
        },
      }),
    }),
  ]);

  const destinations = ['slack', 'airtable'];
  const failed = results
    .map((r, i) => {
      // A rejected promise means the request never completed. A fulfilled one
      // can still carry a non-2xx response — Airtable answers 422 for an unknown
      // field name, for instance — so the status has to be checked too, or a
      // silently dropped write is reported to the caller as a success.
      if (r.status === 'rejected') {
        console.error(`[sdk-integration-feedback] ${destinations[i]} delivery failed:`, r.reason);
        return destinations[i];
      }
      if (!r.value?.ok) {
        console.error(
          `[sdk-integration-feedback] ${destinations[i]} delivery failed with HTTP ${r.value?.status}`
        );
        return destinations[i];
      }
      return null;
    })
    .filter(Boolean);

  if (failed.length > 0) {
    return Response.json({ error: `Failed: ${failed.join(', ')}` }, { status: 500 });
  }

  return Response.json({ ok: true });
}

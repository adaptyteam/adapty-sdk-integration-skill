/**
 * Adapty SDK Integration Skill — Feedback Endpoint
 *
 * Accepts anonymous feedback from the adapty-sdk-integration Claude skill
 * and forwards it to Slack and Airtable.
 *
 * Environment variables (set in Vercel dashboard):
 *   SLACK_WEBHOOK_URL   — Slack Incoming Webhook URL
 *   AIRTABLE_PAT        — Airtable Personal Access Token (data.records:write)
 *   AIRTABLE_BASE_ID    — Airtable Base ID (e.g. appXXXXXXXXXXXXXX)
 *   AIRTABLE_TABLE      — Airtable table name (e.g. Table 1)
 */

export async function POST(req) {
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
          rating: rating ?? null,
        },
      }),
    }),
  ]);

  const destinations = ['slack', 'airtable'];
  const failed = results
    .map((r, i) => {
      if (r.status === 'rejected') {
        console.error(`[sdk-integration-feedback] ${destinations[i]} delivery failed:`, r.reason);
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

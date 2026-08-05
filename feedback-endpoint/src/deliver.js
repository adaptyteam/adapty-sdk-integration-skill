/**
 * Fan one feedback payload out to Slack and Airtable.
 *
 * Platform-agnostic on purpose: the Worker hands in its `env` binding, the
 * Vercel function hands in `process.env`, and the delivery rules - including
 * which non-2xx counts as a failure - live in exactly one place.
 *
 * Returns the list of destinations that did not accept the payload; empty
 * means everything landed.
 */
export async function deliver(payload, env) {
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
  } = payload;

  const { SLACK_WEBHOOK_URL, AIRTABLE_PAT, AIRTABLE_BASE_ID, AIRTABLE_TABLE } = env;

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
          app_id: app_id ?? null,
          migration_source: migration_source ?? null,
        },
      }),
    }),
  ]);

  const destinations = ['slack', 'airtable'];
  return results
    .map((r, i) => {
      // A rejected promise means the request never completed. A fulfilled one
      // can still carry a non-2xx response - Airtable answers 422 for an unknown
      // field name, for instance - so the status has to be checked too, or a
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
}

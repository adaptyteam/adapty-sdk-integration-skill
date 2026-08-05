/**
 * Validation for the feedback payload.
 *
 * This endpoint cannot be authenticated: the skill runs on the user's machine,
 * so any token we embedded would be public by definition. Validation plus a
 * rate limit in front of it is therefore the whole defense, and the sharpest
 * edge is `slack_text` - it lands in an Adapty Slack channel verbatim, so
 * without sanitising it anyone who learns the URL can post arbitrary text
 * there, mention syntax included.
 *
 * Values are CLAMPED, not rejected. A telemetry endpoint that answers 400
 * because a sender added a field or a new platform appeared just loses real
 * events - the same deploy-order trap as an Airtable column that does not
 * exist yet, in reverse. So strings get trimmed to a length and a character
 * set, numbers that make no sense become null, and only a body we cannot read
 * at all is refused.
 */

/** Bodies are a few hundred bytes; this is two orders of magnitude of headroom. */
export const MAX_BODY_BYTES = 16 * 1024;

const MAX_TOKEN = 32;
const MAX_SENTIMENT = 16;
const MAX_APP_ID = 64;
const MAX_INTEGRATIONS = 200;
const MAX_SLACK_TEXT = 500;
/** Counters are step tallies; anything past this is noise, not a longer session. */
const MAX_COUNTER = 1000;

/**
 * Free text: control characters and angle brackets out, then truncated.
 * Angle brackets are what neuters Slack's mention syntax - `<!channel>` stops
 * being a broadcast once it is plain text. Non-ASCII stays: our own messages
 * are full of `·` and `✓`.
 */
function text(value, max) {
  if (typeof value !== 'string') return null;
  // eslint-disable-next-line no-control-regex
  return value.replaceAll(/[\p{Cc}<>]/gu, '').slice(0, max).trim();
}

/** An identifier-shaped value: platform, approach, source, app id. */
function token(value, max) {
  if (typeof value !== 'string') return null;
  const cleaned = value.replaceAll(/[^\w.-]/g, '').slice(0, max);
  return cleaned || null;
}

function intOr(value, min, max) {
  return Number.isInteger(value) && value >= min && value <= max ? value : null;
}

/**
 * Shape the raw body into exactly the fields we deliver. Unknown keys are
 * dropped by construction - the result is built, never spread.
 */
export function validatePayload(raw) {
  if (raw === null || typeof raw !== 'object' || Array.isArray(raw)) {
    return { error: 'Body must be a JSON object', ok: false, status: 400 };
  }

  return {
    ok: true,
    payload: {
      app_id: token(raw.app_id, MAX_APP_ID),
      checkpoints_passed: intOr(raw.checkpoints_passed, 0, MAX_COUNTER),
      friction_rounds: intOr(raw.friction_rounds, 0, MAX_COUNTER),
      integrations: text(raw.integrations, MAX_INTEGRATIONS),
      migration_source: token(raw.migration_source, MAX_TOKEN),
      paywall_approach: token(raw.paywall_approach, MAX_TOKEN),
      phases_completed: intOr(raw.phases_completed, 0, MAX_COUNTER),
      platform: token(raw.platform, MAX_TOKEN),
      rating: intOr(raw.rating, 1, 5),
      sentiment: token(raw.sentiment, MAX_SENTIMENT),
      slack_text: text(raw.slack_text, MAX_SLACK_TEXT),
    },
  };
}

/** Read and validate a request body. Same contract as validatePayload. */
export async function readFeedback(request) {
  const contentType = request.headers?.get?.('content-type') ?? '';
  if (contentType && !contentType.includes('application/json')) {
    return { error: 'Expected application/json', ok: false, status: 415 };
  }

  // Refuse an oversized body before buffering it, when the sender declares one.
  const declared = Number(request.headers?.get?.('content-length'));
  if (Number.isFinite(declared) && declared > MAX_BODY_BYTES) {
    return { error: 'Body too large', ok: false, status: 413 };
  }

  const body = await request.text();
  if (new TextEncoder().encode(body).byteLength > MAX_BODY_BYTES) {
    return { error: 'Body too large', ok: false, status: 413 };
  }

  let raw;
  try {
    raw = JSON.parse(body);
  } catch {
    // The caller's mistake, not a delivery failure - a 500 here would send
    // them into a pointless retry.
    return { error: 'Invalid JSON body', ok: false, status: 400 };
  }

  return validatePayload(raw);
}

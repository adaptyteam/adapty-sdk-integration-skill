/**
 * Adapty SDK Integration Skill — Feedback Endpoint, Vercel entry point.
 *
 * Kept after the move to Cloudflare Workers because this URL is baked into
 * published skill versions and keeps receiving traffic for as long as they are
 * installed — retiring it would drop their feedback silently.
 *
 * Two modes:
 *   - no `FORWARD_URL`: validates and delivers to Slack and Airtable itself
 *     (what it always did);
 *   - `FORWARD_URL` set: relays the request to the Worker, which validates and
 *     delivers, so after the cutover the credentials and the rules live in one
 *     place.
 *
 * Environment variables (set in the Vercel dashboard):
 *   FORWARD_URL         — Worker URL to relay to; unset means deliver here
 *   SLACK_WEBHOOK_URL   — Slack Incoming Webhook URL
 *   AIRTABLE_PAT        — Airtable Personal Access Token (data.records:write)
 *   AIRTABLE_BASE_ID    — Airtable Base ID (e.g. appXXXXXXXXXXXXXX)
 *   AIRTABLE_TABLE      — Airtable table name (e.g. Table 1)
 */
import { handleFeedback } from '../src/handler.js';
import { MAX_BODY_BYTES } from '../src/validate.js';

export async function POST(req) {
  const forwardUrl = process.env.FORWARD_URL;
  if (!forwardUrl) return handleFeedback(req, process.env);

  // The Worker validates, but a relay that buffers first would still eat an
  // oversized body here - refuse it on the declared length before reading.
  const declared = Number(req.headers?.get?.('content-length'));
  if (Number.isFinite(declared) && declared > MAX_BODY_BYTES) {
    return Response.json({ error: 'Body too large' }, { status: 413 });
  }

  const body = await req.text();
  const upstream = await fetch(forwardUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body,
  });

  // Pass the Worker's verdict through unchanged: the caller decides what a
  // failure means, and a relay that swallows it would hide a broken cutover.
  return new Response(await upstream.text(), {
    status: upstream.status,
    headers: { 'Content-Type': 'application/json' },
  });
}

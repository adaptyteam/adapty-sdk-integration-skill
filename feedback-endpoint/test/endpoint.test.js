import { test } from 'node:test';
import assert from 'node:assert/strict';

import { POST } from '../api/sdk-integration-feedback.js';
import { MAX_BODY_BYTES, validatePayload } from '../src/validate.js';

// The handler reads these inside POST(), so setting them at module scope
// (before any test runs) is sufficient.
process.env.SLACK_WEBHOOK_URL = 'https://hooks.slack.com/services/TEST';
process.env.AIRTABLE_PAT = 'pat_test';
process.env.AIRTABLE_BASE_ID = 'appTEST';
process.env.AIRTABLE_TABLE = 'Table 1';

// A real Request: the handler now reads headers and the raw body, not just json().
function makeReq(body, { contentType = 'application/json', raw } = {}) {
  return new Request('https://feedback.example.com/api/sdk-integration-feedback', {
    method: 'POST',
    headers: { 'Content-Type': contentType },
    body: raw ?? JSON.stringify(body),
  });
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

// Replace global fetch with a recorder whose Airtable call resolves to a
// non-2xx response — the shape Airtable returns for an unknown field name.
function stubFetchAirtable422() {
  const calls = [];
  globalThis.fetch = async (url, opts) => {
    calls.push({ url, opts });
    return String(url).includes('airtable.com')
      ? { ok: false, status: 422 }
      : { ok: true, status: 200 };
  };
  return calls;
}

// Find the Airtable call among recorded fetches and return its parsed body.
function airtableBody(calls) {
  const call = calls.find((c) => String(c.url).includes('airtable.com'));
  assert.ok(call, 'expected an Airtable fetch call');
  return JSON.parse(call.opts.body);
}

function slackText(calls) {
  const call = calls.find((c) => String(c.url).includes('hooks.slack.com'));
  assert.ok(call, 'expected a Slack fetch call');
  return JSON.parse(call.opts.body).text;
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
  const res = await POST(makeReq({ platform: 'ios', slack_text: 'x' }));
  assert.equal(res.status, 200);
  assert.equal(airtableBody(calls).fields.app_id, null);
});

test('migration_source is forwarded into the Airtable fields when present', async () => {
  const calls = stubFetch();
  const res = await POST(
    makeReq({
      platform: 'flutter',
      paywall_approach: 'flow_builder',
      integrations: '',
      phases_completed: 4,
      checkpoints_passed: 5,
      friction_rounds: 1,
      sentiment: 'positive',
      rating: 4,
      app_id: 'a1b2c3d4',
      migration_source: 'revenuecat',
      slack_text: 'x',
    })
  );
  assert.equal(res.status, 200);
  assert.equal(airtableBody(calls).fields.migration_source, 'revenuecat');
});

test('migration_source defaults to null when omitted', async () => {
  const calls = stubFetch();
  const res = await POST(
    makeReq({
      platform: 'ios',
      paywall_approach: 'paywall_builder',
      integrations: '',
      phases_completed: 4,
      checkpoints_passed: 5,
      friction_rounds: 0,
      sentiment: 'positive',
      rating: 5,
      slack_text: 'x',
    })
  );
  assert.equal(res.status, 200);
  assert.equal(airtableBody(calls).fields.migration_source, null);
});

test('a resolved-but-not-ok response is reported as a failure, not a success', async () => {
  stubFetchAirtable422();
  const res = await POST(
    makeReq({
      platform: 'ios',
      paywall_approach: 'paywall_builder',
      integrations: '',
      phases_completed: 4,
      checkpoints_passed: 5,
      friction_rounds: 0,
      sentiment: 'positive',
      rating: 5,
      migration_source: 'revenuecat',
      slack_text: 'x',
    })
  );
  assert.equal(res.status, 500);
  const body = await res.json();
  assert.match(body.error, /airtable/);
  assert.doesNotMatch(body.error, /slack/);
});

test('a real message survives validation unchanged', async () => {
  const calls = stubFetch();
  const text =
    '[ios · flow_builder · from revenuecat] Phase 4 ✓ · Rating: 4/5 · Sentiment: positive · 0 friction rounds · App: a1b2c3d4';
  const res = await POST(
    makeReq({
      platform: 'ios',
      paywall_approach: 'flow_builder',
      integrations: 'source:cli-integrate v0.3.0 · driver:claude',
      phases_completed: 4,
      checkpoints_passed: 5,
      friction_rounds: 0,
      sentiment: 'positive',
      rating: 4,
      app_id: 'a1b2c3d4',
      migration_source: 'revenuecat',
      slack_text: text,
    })
  );
  assert.equal(res.status, 200);
  assert.equal(slackText(calls), text, 'non-ASCII and punctuation must not be mangled');
  assert.equal(airtableBody(calls).fields.integrations, 'source:cli-integrate v0.3.0 · driver:claude');
});

test('Slack mention syntax is neutered before it reaches the channel', async () => {
  const calls = stubFetch();
  const res = await POST(
    makeReq({ platform: 'ios', slack_text: 'ping <!channel> <!here> <@U123> now' })
  );
  assert.equal(res.status, 200);
  assert.equal(slackText(calls), 'ping !channel !here @U123 now');
});

test('junk in identifier fields is stripped, not delivered', () => {
  const { payload } = validatePayload({
    platform: 'ios"; DROP TABLE',
    paywall_approach: 'flow builder!',
    migration_source: '<script>',
    app_id: 'a1b2-c3d4 ',
  });
  assert.equal(payload.platform, 'iosDROPTABLE');
  assert.equal(payload.paywall_approach, 'flowbuilder');
  assert.equal(payload.migration_source, 'script');
  assert.equal(payload.app_id, 'a1b2-c3d4');
});

test('an unknown platform still gets through - clamping, not an allowlist', () => {
  // A new platform must not start failing while the endpoint waits to be redeployed.
  const { payload } = validatePayload({ platform: 'web' });
  assert.equal(payload.platform, 'web');
});

test('numbers outside their range become null instead of reaching Airtable', () => {
  const { payload } = validatePayload({
    rating: 9,
    phases_completed: -1,
    checkpoints_passed: 1.5,
    friction_rounds: 10_000,
  });
  assert.equal(payload.rating, null);
  assert.equal(payload.phases_completed, null);
  assert.equal(payload.checkpoints_passed, null);
  assert.equal(payload.friction_rounds, null);
});

test('overlong strings are truncated, and unknown keys never arrive', () => {
  const { payload } = validatePayload({
    slack_text: 'x'.repeat(5000),
    integrations: 'y'.repeat(5000),
    surprise: 'value',
  });
  assert.equal(payload.slack_text.length, 500);
  assert.equal(payload.integrations.length, 200);
  assert.ok(!('surprise' in payload));
});

test('a body that is not an object is refused', async () => {
  const calls = stubFetch();
  const res = await POST(makeReq(null, { raw: '[1,2,3]' }));
  assert.equal(res.status, 400);
  assert.equal(calls.length, 0);
});

test('an unparseable body is the caller\'s error, not a delivery failure', async () => {
  const calls = stubFetch();
  const res = await POST(makeReq(null, { raw: '{not json' }));
  assert.equal(res.status, 400);
  assert.equal(calls.length, 0, 'nothing should be delivered for a body we could not read');
});

test('a non-JSON content type is refused', async () => {
  const calls = stubFetch();
  const res = await POST(makeReq({ platform: 'ios' }, { contentType: 'text/plain' }));
  assert.equal(res.status, 415);
  assert.equal(calls.length, 0);
});

test('an oversized body is refused before delivery', async () => {
  const calls = stubFetch();
  const res = await POST(
    makeReq(null, { raw: JSON.stringify({ slack_text: 'x'.repeat(MAX_BODY_BYTES) }) })
  );
  assert.equal(res.status, 413);
  assert.equal(calls.length, 0);
});

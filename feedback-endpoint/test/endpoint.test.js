import { test } from 'node:test';
import assert from 'node:assert/strict';

import { POST } from '../api/sdk-integration-feedback.js';
import { handleFeedback } from '../src/handler.js';
import worker from '../src/index.js';
import { MAX_BODY_BYTES, validatePayload } from '../src/validate.js';

// Credentials reach the shared handler as an argument - the Worker gets them
// from its binding, so the tests do the same. The Vercel entry point still
// reads process.env, so the same values live there too for its own tests.
const ENV = {
  SLACK_WEBHOOK_URL: 'https://hooks.slack.com/services/TEST',
  AIRTABLE_PAT: 'pat_test',
  AIRTABLE_BASE_ID: 'appTEST',
  AIRTABLE_TABLE: 'Table 1',
};
Object.assign(process.env, ENV);

// A real Request: the handler reads headers and the raw body, not just json().
function makeReq(body, { contentType = 'application/json', raw, path = '/sdk-integration-feedback' } = {}) {
  return new Request(`https://hooks.example.com${path}`, {
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
  const res = await handleFeedback(
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
    }),
    ENV
  );
  assert.equal(res.status, 200);
  assert.equal(airtableBody(calls).fields.app_id, 'a1b2c3d4');
});

test('app_id defaults to null when omitted', async () => {
  const calls = stubFetch();
  const res = await handleFeedback(makeReq({ platform: 'ios', slack_text: 'x' }), ENV);
  assert.equal(res.status, 200);
  assert.equal(airtableBody(calls).fields.app_id, null);
});

test('migration_source is forwarded into the Airtable fields when present', async () => {
  const calls = stubFetch();
  const res = await handleFeedback(
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
    }),
    ENV
  );
  assert.equal(res.status, 200);
  assert.equal(airtableBody(calls).fields.migration_source, 'revenuecat');
});

test('migration_source defaults to null when omitted', async () => {
  const calls = stubFetch();
  const res = await handleFeedback(
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
    }),
    ENV
  );
  assert.equal(res.status, 200);
  assert.equal(airtableBody(calls).fields.migration_source, null);
});

test('a resolved-but-not-ok response is reported as a failure, not a success', async () => {
  stubFetchAirtable422();
  const res = await handleFeedback(
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
    }),
    ENV
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
  const res = await handleFeedback(
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
    }),
    ENV
  );
  assert.equal(res.status, 200);
  assert.equal(slackText(calls), text, 'non-ASCII and punctuation must not be mangled');
  assert.equal(airtableBody(calls).fields.integrations, 'source:cli-integrate v0.3.0 · driver:claude');
});

test('Slack mention syntax is neutered before it reaches the channel', async () => {
  const calls = stubFetch();
  const res = await handleFeedback(
    makeReq({ platform: 'ios', slack_text: 'ping <!channel> <!here> <@U123> now' }),
    ENV
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
  const res = await handleFeedback(makeReq(null, { raw: '[1,2,3]' }), ENV);
  assert.equal(res.status, 400);
  assert.equal(calls.length, 0);
});

test('an unparseable body is the caller\'s error, not a delivery failure', async () => {
  const calls = stubFetch();
  const res = await handleFeedback(makeReq(null, { raw: '{not json' }), ENV);
  assert.equal(res.status, 400);
  assert.equal(calls.length, 0, 'nothing should be delivered for a body we could not read');
});

test('a non-JSON content type is refused', async () => {
  const calls = stubFetch();
  const res = await handleFeedback(makeReq({ platform: 'ios' }, { contentType: 'text/plain' }), ENV);
  assert.equal(res.status, 415);
  assert.equal(calls.length, 0);
});

test('an oversized body is refused before delivery', async () => {
  const calls = stubFetch();
  const res = await handleFeedback(
    makeReq(null, { raw: JSON.stringify({ slack_text: 'x'.repeat(MAX_BODY_BYTES) }) }),
    ENV
  );
  assert.equal(res.status, 413);
  assert.equal(calls.length, 0);
});

test('the Worker delivers a POST on either path', async () => {
  // Both, because published skill versions send to the /api/ one and the
  // Vercel relay forwards their path verbatim.
  for (const path of ['/sdk-integration-feedback', '/api/sdk-integration-feedback']) {
    const calls = stubFetch();
    const res = await worker.fetch(makeReq({ platform: 'ios', slack_text: 'x' }, { path }), ENV);
    assert.equal(res.status, 200, path);
    assert.equal(airtableBody(calls).fields.platform, 'ios');
  }
});

test('the Worker refuses anything but a POST to a known path', async () => {
  const calls = stubFetch();

  const wrongPath = await worker.fetch(makeReq({ platform: 'ios' }, { path: '/' }), ENV);
  assert.equal(wrongPath.status, 404);

  const wrongMethod = await worker.fetch(
    new Request('https://hooks.example.com/sdk-integration-feedback'),
    ENV
  );
  assert.equal(wrongMethod.status, 405);
  assert.equal(wrongMethod.headers.get('Allow'), 'POST');

  assert.equal(calls.length, 0, 'neither case should reach Slack or Airtable');
});

test('the Vercel entry delivers on its own when FORWARD_URL is unset', async () => {
  delete process.env.FORWARD_URL;
  const calls = stubFetch();
  const res = await POST(makeReq({ platform: 'ios', slack_text: 'x' }));
  assert.equal(res.status, 200);
  assert.equal(airtableBody(calls).fields.platform, 'ios');
});

test('the Vercel entry relays to the Worker and passes its verdict through', async () => {
  process.env.FORWARD_URL = 'https://hooks.adapty.io/sdk-integration-feedback';
  const calls = [];
  globalThis.fetch = async (url, opts) => {
    calls.push({ url, opts });
    return new Response(JSON.stringify({ error: 'Failed: airtable' }), { status: 500 });
  };

  const res = await POST(makeReq({ platform: 'ios', slack_text: 'x' }));
  assert.equal(calls.length, 1, 'the relay must not deliver anything itself');
  assert.equal(calls[0].url, process.env.FORWARD_URL);
  assert.deepEqual(JSON.parse(calls[0].opts.body), { platform: 'ios', slack_text: 'x' });
  assert.equal(res.status, 500, "the Worker's status must not be rewritten");
  delete process.env.FORWARD_URL;
});

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { POST } from '../api/sdk-integration-feedback.js';

// The handler reads these inside POST(), so setting them at module scope
// (before any test runs) is sufficient.
process.env.SLACK_WEBHOOK_URL = 'https://hooks.slack.com/services/TEST';
process.env.AIRTABLE_PAT = 'pat_test';
process.env.AIRTABLE_BASE_ID = 'appTEST';
process.env.AIRTABLE_TABLE = 'Table 1';

// Build a minimal Request-like object: the handler only calls req.json().
function makeReq(body) {
  return { json: async () => body };
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
  const res = await POST(
    makeReq({
      platform: 'ios',
      slack_text: 'x',
    })
  );
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

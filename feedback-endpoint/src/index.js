import { handleFeedback } from './handler.js';

/**
 * Cloudflare Worker entry point.
 *
 * Two paths answer, not one: the Vercel deployment served
 * `/api/sdk-integration-feedback`, that URL is baked into published skill
 * versions, and it stays reachable through a relay - so the Worker must not
 * 404 the old path when the relay forwards it verbatim.
 */
const PATHS = new Set(['/sdk-integration-feedback', '/api/sdk-integration-feedback']);

export default {
  async fetch(request, env) {
    const { pathname } = new URL(request.url);
    if (!PATHS.has(pathname)) return new Response('Not found', { status: 404 });
    if (request.method !== 'POST') {
      return new Response('Method not allowed', { status: 405, headers: { Allow: 'POST' } });
    }

    return handleFeedback(request, env);
  },
};

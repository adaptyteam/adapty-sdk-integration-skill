import { deliver } from './deliver.js';
import { readFeedback } from './validate.js';

/**
 * The request/response shell both deployments share: validate, then deliver.
 * Takes a Web `Request` and the environment holding the credentials - the
 * Worker's binding, or `process.env` on Vercel.
 */
export async function handleFeedback(request, env) {
  const result = await readFeedback(request);
  if (!result.ok) {
    return Response.json({ error: result.error }, { status: result.status });
  }

  const failed = await deliver(result.payload, env);
  if (failed.length > 0) {
    return Response.json({ error: `Failed: ${failed.join(', ')}` }, { status: 500 });
  }

  return Response.json({ ok: true });
}

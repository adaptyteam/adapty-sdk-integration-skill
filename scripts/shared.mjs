/** Shared plumbing for the skill lints: cached, retrying docs fetching. */

export const DOCS_BASE = 'https://adapty.io/docs/'

const pageCache = new Map()

const RETRYABLE = (status) => status === 429 || status >= 500

/**
 * Fetch with cache and backoff. Retries rate limits (429), server errors
 * (5xx), and network blips - a transient hiccup must not turn into a false
 * lint finding or a false skill-drift issue from the daily cron. Thrown
 * errors carry `status` (absent for network errors) so callers can tell a
 * real 404 from infrastructure trouble.
 */
export async function fetchText(url) {
  if (pageCache.has(url)) return pageCache.get(url)
  for (let attempt = 0; ; attempt++) {
    let res
    try {
      res = await fetch(url, {redirect: 'follow', signal: AbortSignal.timeout(20_000)})
    } catch (networkError) {
      if (attempt < 4) {
        await sleep(2 ** attempt * 1000)
        continue
      }

      throw new Error(`network error (${networkError.message})`)
    }

    if (RETRYABLE(res.status) && attempt < 4) {
      const retryAfter = Number.parseFloat(res.headers.get('retry-after') ?? '') || 2 ** attempt
      await sleep(Math.min(retryAfter * 1000, 15_000))
      continue
    }

    if (!res.ok) {
      const error = new Error(`HTTP ${res.status}`)
      error.status = res.status
      throw error
    }

    const bodyText = await res.text()
    pageCache.set(url, bodyText)
    return bodyText
  }
}

/** The global docs index; both lints need it, and without it neither can run at all. */
export async function fetchLlmsTxt() {
  try {
    return await fetchText(`${DOCS_BASE}llms.txt`)
  } catch (error) {
    console.error(`fatal: could not fetch llms.txt: ${error.message}`)
    process.exit(2)
  }
}

async function sleep(ms) {
  await new Promise((resolve) => {
    setTimeout(resolve, ms)
  })
}

export async function mapLimit(items, limit, fn) {
  const results = Array.from({length: items.length})
  let next = 0
  await Promise.all(
    Array.from({length: Math.min(limit, items.length)}, async () => {
      for (;;) {
        const i = next++
        if (i >= items.length) return
        results[i] = await fn(items[i])
      }
    }),
  )
  return results
}

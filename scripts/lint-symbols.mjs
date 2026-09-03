#!/usr/bin/env node
/**
 * Symbol lint: every Adapty-branded SDK symbol used in a reference file must
 * exist in the official docs for that platform.
 *
 * Scope, honestly stated: symbols are extracted from code contexts (fenced
 * blocks and inline backticks) whose receiver is Adapty-branded (`Adapty.x`,
 * `adapty.x`, `AdaptyUI().x`) plus Adapty* type names. Member access on
 * variables holding SDK objects (`paywall.products`) is NOT covered - that
 * class of drift is the eval harness's job, not a text lint's.
 *
 * Ground truth chain: the docs are verified against SDK sources by the docs
 * team's own release process, so "symbol appears in the docs" transitively
 * means "symbol exists in the SDK". This lint closes the remaining gap:
 * skill <-> docs drift (renamed APIs, invented methods, stale snippets).
 *
 * App-side wrapper names the references deliberately invent live in
 * scripts/app-side-allowlist.txt (plain text, editable without touching code).
 *
 * Usage:  node scripts/lint-symbols.mjs [platform ...]
 *         (default: every references/<platform>.md + the testing-setup files)
 * Exit codes: 0 = clean, 1 = missing symbols, 2 = infrastructure error
 * (docs unreachable - fix the network/docs, not the skill).
 */

import {readdir, readFile} from 'node:fs/promises'
import {dirname, join} from 'node:path'
import {fileURLToPath} from 'node:url'

import {DOCS_BASE, fetchLlmsTxt, fetchText, mapLimit} from './shared.mjs'

const SCRIPTS_DIR = dirname(fileURLToPath(import.meta.url))
const REFERENCES_DIR = join(SCRIPTS_DIR, '..', 'skills', 'adapty-integration', 'references')
const FETCH_CONCURRENCY = 3

/** Non-platform references are linted against the platform they belong to. */
const REFERENCE_PLATFORM_OVERRIDES = {
  'testing-setup-android': 'android',
  'testing-setup-ios': 'ios',
}

/**
 * Migration references are cross-platform: they map another SDK's concepts
 * onto Adapty's and delegate platform code to references/<platform>.md, so no
 * single aggregate can verify them. They are linted against the UNION of
 * every platform aggregate instead of being skipped - a skipped file is how
 * drift hides. The union still catches a symbol that exists on NO platform
 * (a hallucination, or a rename that landed everywhere); it cannot catch
 * "iOS-only symbol used in a Flutter context", which is the accepted cost.
 *
 * Prefix-matched, and the platform list is DERIVED, so adding
 * migration-superwall.md or a whole new platform needs no edit here.
 */
const isMigrationReference = (reference) => reference.startsWith('migration')

function platformsFor(reference, available) {
  if (!isMigrationReference(reference)) return [REFERENCE_PLATFORM_OVERRIDES[reference] ?? reference]
  return available.filter((r) => !isMigrationReference(r) && !(r in REFERENCE_PLATFORM_OVERRIDES))
}

// ---------- symbol extraction ----------

// Negative lookbehind: `'adapty.customerUserId'` as a storage-key string is not an API claim.
const MEMBER_CALL = /(?<!['"`])\b([Aa]dapty(?:UI|Ui)?)(?:\(\))?\.([a-zA-Z_]\w*)/g
// \w+ (not {2,}): short-suffix types like AdaptyUI must be extracted too.
const TYPE_NAME = /\bAdapty[A-Z]\w+/g

async function loadAllowlist() {
  const raw = await readFile(join(SCRIPTS_DIR, 'app-side-allowlist.txt'), 'utf8')
  return new Set(
    raw
      .split('\n')
      .map((line) => line.split('#')[0].trim())
      .filter(Boolean),
  )
}

/** "reference: symbol url" entries -> Map<"reference:symbol", sourceUrl>. */
async function loadUndocumented() {
  const raw = await readFile(join(SCRIPTS_DIR, 'undocumented-sdk-symbols.txt'), 'utf8')
  const map = new Map()
  for (const line of raw.split('\n')) {
    const entry = line.split('#')[0].trim()
    if (!entry) continue
    const m = entry.match(/^([a-z-]+):\s*(\S+)\s+(https:\/\/\S+)$/)
    if (m) map.set(`${m[1]}:${m[2]}`, m[3])
  }

  return map
}

function extractCodeContexts(markdown) {
  const contexts = [] // {text, line}
  const lines = markdown.split('\n')
  let inFence = false
  for (const [i, line] of lines.entries()) {
    if (/^\s*(```|~~~)/.test(line)) {
      inFence = !inFence
      continue
    }

    if (inFence) {
      contexts.push({line: i + 1, text: line})
    } else {
      for (const span of line.matchAll(/`([^`]+)`/g)) {
        contexts.push({line: i + 1, text: span[1]})
      }
    }
  }

  return contexts
}

function extractSymbols(markdown) {
  const symbols = new Map() // symbol -> first line
  const add = (symbol, line) => {
    if (!symbols.has(symbol)) symbols.set(symbol, line)
  }

  for (const {line, text} of extractCodeContexts(markdown)) {
    for (const m of text.matchAll(MEMBER_CALL)) {
      if (`${m[1]}.${m[2]}`.toLowerCase().startsWith('adapty.io')) continue // URLs
      add(`${m[1]}.${m[2]}`, line)
    }

    for (const m of text.matchAll(TYPE_NAME)) {
      add(m[0], line)
    }
  }

  return symbols
}

// ---------- docs corpus ----------

/**
 * Corpus for a platform: the <platform>-llms-full.txt aggregate (it carries
 * every page of the platform docs - fetching individual platform pages on
 * top of it would be pure duplication) plus pages the reference itself
 * links that live OUTSIDE the platform section (shared guides etc.).
 */
function collectDocUrls(platforms, markdown) {
  const urls = new Set(platforms.map((platform) => `${DOCS_BASE}${platform}-llms-full.txt`))
  for (const m of markdown.matchAll(/https:\/\/adapty\.io\/docs\/([a-z0-9_-]+(?:\.(?:md|txt))?)/g)) {
    const slug = m[1]
    if (slug === 'llms.txt' || slug === 'llms') continue // the global index carries no code
    urls.add(/\.(md|txt)$/.test(slug) ? `${DOCS_BASE}${slug}` : `${DOCS_BASE}${slug}.md`)
  }

  return [...urls]
}

// ---------- membership ----------

function symbolFoundInCorpus(symbol, corpus) {
  if (!symbol.includes('.')) {
    return new RegExp(`\\b${symbol}\\b`).test(corpus)
  }

  const [root, method] = symbol.split('.')
  // Preferred: the docs show the same receiver the reference claims
  // (first letter case-insensitive: docs mix `Adapty.x` and `adapty.x`).
  const rootPattern = `[${root[0].toUpperCase()}${root[0].toLowerCase()}]${root.slice(1)}`
  if (new RegExp(`\\b${rootPattern}(?:\\(\\))?\\s*\\.\\s*${method}\\b`).test(corpus)) return true
  // Accepted: API-shaped mentions - dotted on another receiver (docs often
  // call via variables) or call form (docs tables list `method(...)`).
  // A bare prose word is deliberately NOT accepted: a removed method
  // lingering in a migration guide must not mask real drift.
  return new RegExp(`[.]\\s*${method}\\b`).test(corpus) || new RegExp(`\\b${method}\\s*\\(`).test(corpus)
}

// ---------- main ----------

async function lintReference(reference, allowlist, undocumented, available) {
  const markdown = await readFile(join(REFERENCES_DIR, `${reference}.md`), 'utf8')
  const symbols = extractSymbols(markdown)

  const urls = collectDocUrls(platformsFor(reference, available), markdown)
  const fetchFailures = []
  const pages = await mapLimit(urls, FETCH_CONCURRENCY, async (url) => {
    try {
      return await fetchText(url)
    } catch (error) {
      fetchFailures.push(`${url}: ${error.message}`)
      return ''
    }
  })
  // An unfetchable corpus page means we CANNOT verify - that is an
  // infrastructure/link problem (exit 2), never a false MISSING symbol.
  if (fetchFailures.length > 0) {
    throw new Error(`corpus incomplete, cannot verify symbols:\n    ${fetchFailures.join('\n    ')}`)
  }

  const corpus = pages.join('\n')
  const missing = []
  for (const [symbol, line] of symbols) {
    if (allowlist.has(symbol)) continue

    // Deliberately-undocumented symbols are verified against SDK SOURCE
    // instead of the docs (see undocumented-sdk-symbols.txt).
    const sourceUrl = undocumented.get(`${reference}:${symbol}`)
    if (sourceUrl) {
      const source = await fetchText(sourceUrl) // throws -> INFRA ERROR, like corpus pages
      const name = symbol.includes('.') ? symbol.split('.')[1] : symbol
      if (!new RegExp(`\\b${name}\\b`).test(source)) {
        missing.push({line, symbol: `${symbol} (vanished from SDK source ${sourceUrl})`})
      }

      continue
    }

    if (!symbolFoundInCorpus(symbol, corpus)) missing.push({line, symbol})
  }

  return {docPages: urls.length, missing, symbolCount: symbols.size}
}

const requested = process.argv.slice(2)
const available = (await readdir(REFERENCES_DIR)).filter((f) => f.endsWith('.md')).map((f) => f.replace(/\.md$/, ''))
const references = requested.length > 0 ? requested : available

const allowlist = await loadAllowlist()
const undocumented = await loadUndocumented()
await fetchLlmsTxt() // fail fast (exit 2) when the docs are unreachable at all

let missingFound = false
let infraFailed = false
for (const reference of references) {
  let result
  try {
    result = await lintReference(reference, allowlist, undocumented, available)
  } catch (error) {
    console.error(`${reference}: INFRA ERROR - ${error.message}`)
    infraFailed = true
    continue
  }

  const status = result.missing.length === 0 ? 'OK' : `${result.missing.length} MISSING`
  console.log(`${reference}: ${result.symbolCount} symbols vs ${result.docPages} doc pages -> ${status}`)
  for (const {line, symbol} of result.missing) {
    console.log(
      `  MISSING  ${symbol}  (references/${reference}.md:${line}) - not in the docs. SDK drift? Or an app-side wrapper name -> add it to scripts/app-side-allowlist.txt`,
    )
    missingFound = true
  }
}

// ---------- scope guard ----------
// This lint verifies `adapty-integration` only, and that is CORRECT rather than an oversight:
// it resolves a file's platform from its name (`references/<platform>.md`) and checks symbols
// against that platform's docs aggregate, and the other four skills have no platform and name
// no SDK symbols -- measured 2026-08-28, zero matches across all four.
//
// But "they name no SDK symbols" is an assumption that rots the moment someone adds one, and a
// silently-unchecked symbol is exactly what this lint exists to prevent. So check the claim
// instead of believing it. Requires a capital A, which is what separates an SDK symbol
// (`AdaptyPaywall`, `Adapty.getPaywall`) from the domain (`adapty.io`) and the CLI (`adapty asa`).
const OTHER_SKILLS = ['ads-manager', 'flow-audit', 'flow-generator', 'migrate-placements', 'onboarding-teardown', 'paywall-teardown']
const SDK_SYMBOL = /\bAdapty[A-Z][A-Za-z0-9_]+|\bAdapty\.[a-z][A-Za-z0-9_]*/g
const SKILLS_ROOT = join(SCRIPTS_DIR, '..', 'skills')

async function mdFiles(dir) {
  const out = []
  for (const entry of await readdir(dir, {withFileTypes: true})) {
    const path = join(dir, entry.name)
    if (entry.isDirectory()) out.push(...(await mdFiles(path)))
    else if (entry.name.endsWith('.md')) out.push(path)
  }
  return out
}

let scopeBreach = false
for (const skill of OTHER_SKILLS) {
  let files
  try {
    files = await mdFiles(join(SKILLS_ROOT, skill))
  } catch {
    continue // skill not present in this checkout
  }
  for (const file of files) {
    const text = await readFile(file, 'utf8')
    for (const [i, lineText] of text.split('\n').entries()) {
      for (const m of lineText.matchAll(SDK_SYMBOL)) {
        console.log(
          `  OUT OF SCOPE  ${m[0]}  (${skill}/${file.split(`/${skill}/`)[1]}:${i + 1}) - an SDK ` +
            `symbol outside adapty-integration, which this lint does not verify. Either drop it ` +
            `(these skills delegate SDK code to adapty-integration) or widen the lint to cover it.`,
        )
        scopeBreach = true
      }
    }
  }
}
if (!scopeBreach) console.log(`scope guard: no SDK symbols in ${OTHER_SKILLS.join(', ')} -> OK`)

process.exit(infraFailed ? 2 : missingFound || scopeBreach ? 1 : 0)

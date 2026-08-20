#!/usr/bin/env node
/**
 * Link lint: every URL the skill tells an agent (or a human) to open must
 * work, the way an AGENT would fetch it.
 *
 * - adapty.io/docs pages are verified via their agent-fetchable variant
 *   (<slug>.md, or as-is for *-llms*.txt aggregates). A dead docs link is a
 *   hard failure - the skill's runtime literally instructs fetching it.
 * - docs pages missing from llms.txt are warnings: they work, but agents
 *   can't DISCOVER them, which degrades on-demand routing.
 * - external links (github, stores, consoles) are checked as-is; failures
 *   are warnings, not errors - many of these sites answer 403/999 to bots.
 * - revenuecat.com/docs pages are checked as-is; a dead one is a hard
 *   failure, since the migration references instruct fetching it.
 *
 * Usage:  node scripts/lint-links.mjs
 * Exit codes: 0 = clean (warnings allowed), 1 = dead docs links, 2 = infra error.
 */

import {readdir, readFile} from 'node:fs/promises'
import {dirname, join, relative} from 'node:path'
import {fileURLToPath} from 'node:url'

import {DOCS_BASE, fetchLlmsTxt, fetchText, mapLimit} from './shared.mjs'

/**
 * Foreign docs the skill instructs agents to fetch (RevenueCat migration
 * guides). A 404 here costs a migrating agent a turn exactly as an Adapty
 * one does, so these are errors, not warnings. Checked AS-IS: RevenueCat's
 * own llms.txt already carries .md where applicable, so no suffixing.
 */
const FOREIGN_DOCS_BASES = ['https://www.revenuecat.com/docs/']
const isForeignDocs = (url) => FOREIGN_DOCS_BASES.some((base) => url.startsWith(base))

const SKILL_DIR = join(dirname(fileURLToPath(import.meta.url)), '..', 'skills', 'adapty-integration')
const REPO_ROOT = join(SKILL_DIR, '..', '..')
const FETCH_CONCURRENCY = 3

// ---------- collect URLs ----------

async function markdownFiles(dir) {
  const out = []
  for (const entry of await readdir(dir, {withFileTypes: true})) {
    const path = join(dir, entry.name)
    if (entry.isDirectory()) out.push(...(await markdownFiles(path)))
    else if (entry.name.endsWith('.md')) out.push(path)
  }

  return out
}

function extractUrls(markdown) {
  const found = [] // {url, line}
  for (const [i, lineText] of markdown.split('\n').entries()) {
    for (const m of lineText.matchAll(/https:\/\/[^\s)"'`<>\]]+/g)) {
      const url = m[0].replace(/[).,:;!?]+$/, '')
      // Templates/globs like https://adapty.io/docs/{slug} or /docs/* are instructions, not links.
      if (/[{}<>*]/.test(url)) continue
      found.push({line: i + 1, url})
    }
  }

  return found
}

// ---------- checks ----------

/** The URL an agent would actually fetch for an adapty docs page. */
function agentFetchVariant(url) {
  // Query/hash (e.g. the ?ref=skill- analytics tag) is not part of the page identity.
  const slug = url.slice(DOCS_BASE.length).split(/[?#]/)[0].replace(/\/+$/, '')
  if (!slug || slug === 'llms.txt') return `${DOCS_BASE}llms.txt`
  return /\.(md|txt)$/.test(slug) ? `${DOCS_BASE}${slug}` : `${DOCS_BASE}${slug}.md`
}

/** null = alive; {dead} = the page does not exist; {infra} = could not verify. */
async function checkUrl(url) {
  try {
    await fetchText(url)
    return null
  } catch (error) {
    // Only "the server said it's not there" makes a link DEAD. Anything
    // else (5xx after retries, timeouts, network) means we could not
    // verify - an infrastructure problem, never a lint finding.
    return error.status === 404 || error.status === 410 ? {dead: error.message} : {infra: error.message}
  }
}

// ---------- main ----------

const files = [...(await markdownFiles(SKILL_DIR))]
const mentions = [] // {file, line, url}
for (const file of files) {
  const markdown = await readFile(file, 'utf8')
  for (const {line, url} of extractUrls(markdown)) {
    mentions.push({file: relative(REPO_ROOT, file), line, url})
  }
}

const llmsTxt = await fetchLlmsTxt()

// Check each unique URL once, then report per mention.
const uniqueUrls = [...new Set(mentions.map((m) => m.url))]
const verdicts = new Map(
  await mapLimit(uniqueUrls, FETCH_CONCURRENCY, async (url) => {
    const isDocs = url.startsWith(DOCS_BASE)
    const variant = isDocs ? agentFetchVariant(url) : url
    const error = await checkUrl(variant)
    return [url, {error, isDocs, isForeign: isForeignDocs(url), variant}]
  }),
)

let errors = 0
let warnings = 0
let infraProblems = 0
for (const {file, line, url} of mentions) {
  const {error, isDocs, isForeign, variant} = verdicts.get(url)
  if (isDocs) {
    if (error?.dead) {
      console.log(`DEAD DOCS LINK  ${url}  (${file}:${line}) - ${error.dead} for the agent-fetchable variant`)
      errors++
    } else if (error?.infra) {
      console.log(`INFRA           ${url}  (${file}:${line}) - could not verify (${error.infra})`)
      infraProblems++
    } else if (url !== DOCS_BASE) {
      const slug = variant.slice(DOCS_BASE.length).replace(/\.md$/, '')
      if (!slug.endsWith('.txt') && !llmsTxt.includes(`/docs/${slug}.md`)) {
        console.log(`NOT IN LLMS.TXT  ${url}  (${file}:${line}) - works, but agents can't discover it`)
        warnings++
      }
    }
  } else if (isForeign) {
    if (error?.dead) {
      console.log(`DEAD DOCS LINK  ${url}  (${file}:${line}) - ${error.dead}`)
      errors++
    } else if (error?.infra && !/HTTP (403|405|999)/.test(error.infra)) {
      console.log(`INFRA           ${url}  (${file}:${line}) - could not verify (${error.infra})`)
      infraProblems++
    }
  } else if (error?.dead || (error?.infra && !/HTTP (403|405|999)/.test(error.infra))) {
    // 403/405/999 = alive but bot-hostile (API endpoints, package registries) - not a finding.
    console.log(`WARN external   ${url}  (${file}:${line}) - ${error.dead ?? error.infra}`)
    warnings++
  }
}

console.log(
  `\n${files.length} files, ${mentions.length} link mentions (${uniqueUrls.length} unique) -> ${errors} dead docs links, ${warnings} warnings, ${infraProblems} unverifiable`,
)
process.exit(infraProblems > 0 ? 2 : errors > 0 ? 1 : 0)

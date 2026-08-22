#!/usr/bin/env node
/**
 * Schema-validate a flow config against the published JSON Schema.
 *
 *   npx --yes --package=ajv@8 node <this-file> --config flow.working.json
 *
 * `adapty flows config validate` checks publishability, not shape: it passes `fill: "banana"`
 * and `schemaVersion: 999` without complaint. This fills that gap — it reports the wrong-shaped
 * props the server-side validator currently ignores, with a JSON path for each.
 *
 * The schema is fetched from SCHEMA_URL and cached at $TMPDIR/adapty-flow.schema.json for a day —
 * the same file the skill tells you to grep. Pass --schema <path-or-url> to point elsewhere, or
 * --refresh to re-download.
 *
 * Exits 0 when the config matches the schema, 1 when it does not, 2 on bad usage.
 *
 * NOTE the schema tracks the newest schemaVersion. On an older flow, expect real mismatches that
 * are version drift rather than mistakes — check `config.schemaVersion` before acting on them.
 */

import {readFileSync, statSync, writeFileSync} from 'node:fs'
import {createRequire} from 'node:module'
import {tmpdir} from 'node:os'
import {delimiter, join, resolve} from 'node:path'
import {parseArgs} from 'node:util'

const SCHEMA_URL = 'https://schemastore.adaptybuilder.com/latest.json'
const CACHE_PATH = join(tmpdir(), 'adapty-flow.schema.json')
const CACHE_MAX_AGE_MS = 24 * 60 * 60 * 1000
const MAX_REPORTED = 40

const USAGE =
  'Usage: node validate-with-schema.mjs --config <flow.json> [--baseline <flow.backup.json>]\n' +
  '         [--schema <path|url>] [--refresh]'

function fail(message) {
  console.error(`${message}\n${USAGE}`)
  process.exit(2)
}

/** ajv is a run-time dependency of the caller: this script, npx, or the current project. */
function loadAjv() {
  const roots = [
    process.cwd(),
    ...(process.env.PATH ?? '')
      .split(delimiter)
      .filter((dir) => dir.endsWith(join('node_modules', '.bin')))
      .map((dir) => join(dir, '..')),
  ]

  for (const root of roots) {
    try {
      return createRequire(join(root, 'noop.js'))('ajv/dist/2020.js')
    } catch {
      continue
    }
  }

  console.error(
    'Could not resolve ajv. Run this through `npx --yes --package=ajv@8 node ...`, or `npm i -D ajv@8` first.',
  )
  process.exit(1)
}

async function loadSchema(source, refresh) {
  if (source && !/^https?:\/\//.test(source)) return JSON.parse(readFileSync(resolve(source), 'utf8'))

  const url = source ?? SCHEMA_URL
  // Only the default URL is cached — an explicit --schema must always be fetched, or it would
  // silently serve whatever the default left behind.
  const cacheable = source === undefined
  const fresh =
    cacheable &&
    !refresh &&
    (() => {
      try {
        return Date.now() - statSync(CACHE_PATH).mtimeMs < CACHE_MAX_AGE_MS
      } catch {
        return false
      }
    })()

  if (fresh) return JSON.parse(readFileSync(CACHE_PATH, 'utf8'))

  let response
  try {
    response = await fetch(url)
  } catch (error) {
    // The schema is not bundled, so this is the first thing to break without a network.
    fail(
      `Could not reach ${url}: ${error.cause?.message ?? error.message}\n` +
        'Offline? Pass --schema <path> to a local copy of the schema instead.',
    )
  }

  if (!response.ok) fail(`Could not fetch ${url}: HTTP ${response.status}`)
  const text = await response.text()
  try {
    if (cacheable) writeFileSync(CACHE_PATH, text)
  } catch {
    // a read-only temp dir is not worth failing over
  }

  return JSON.parse(text)
}

/**
 * ajv reports every branch of every failed union, so one bad prop can produce dozens of errors.
 * Keep the most specific error per location and drop the union wrappers that merely say
 * "nothing matched" — those repeat what the child errors already state, with less detail.
 */
function summarize(errors) {
  const byPath = new Map()

  for (const error of errors) {
    if (error.keyword === 'oneOf' || error.keyword === 'anyOf' || error.keyword === 'if') continue
    const path = error.instancePath || '/'
    let detail
    if (error.keyword === 'additionalProperties') {
      detail = `unknown property "${error.params.additionalProperty}"`
    } else if (error.keyword === 'required') {
      detail = `missing required property "${error.params.missingProperty}"`
    } else if (error.keyword === 'const') {
      // "must be equal to constant" on its own says nothing — name the expected value.
      detail = `must be "${error.params.allowedValue}"`
    } else if (error.params?.allowedValues) {
      detail = `${error.message} (${error.params.allowedValues.join(', ')})`
    } else {
      detail = error.message
    }
    if (!byPath.has(path)) byPath.set(path, new Set())
    byPath.get(path).add(detail)
  }

  return [...byPath].map(([path, details]) => ({details: [...details], path}))
}

let args
try {
  ;({values: args} = parseArgs({
    options: {
      baseline: {type: 'string'},
      config: {type: 'string'},
      refresh: {type: 'boolean'},
      schema: {type: 'string'},
    },
  }))
} catch (error) {
  fail(error.message)
}

if (!args.config) fail('No config: pass --config <path to the flow JSON>.')

let doc
try {
  doc = JSON.parse(readFileSync(resolve(args.config), 'utf8'))
} catch (error) {
  fail(`Could not read ${args.config}: ${error.message}`)
}

// Accept the envelope `flows config get` returns, or a bare config.
const config = doc && typeof doc === 'object' && 'config' in doc ? doc.config : doc

const schema = await loadSchema(args.schema, args.refresh)
const Ajv = loadAjv()
const ajv = new (Ajv.default ?? Ajv)({allErrors: true, strict: false})
const validate = ajv.compile({...schema, $ref: '#/$defs/IFlow'})

const key = ({details, path}) => details.map((d) => `${path} :: ${d}`)
const found = validate(config) ? [] : summarize(validate.errors)

// A flow older than the schema fails in hundreds of places that have nothing to do with the edit
// being made. Validating the backup too, and reporting only what is new, cuts that to signal.
let preexisting = new Set()
if (args.baseline) {
  let baseDoc
  try {
    baseDoc = JSON.parse(readFileSync(resolve(args.baseline), 'utf8'))
  } catch (error) {
    fail(`Could not read ${args.baseline}: ${error.message}`)
  }

  const base = baseDoc && typeof baseDoc === 'object' && 'config' in baseDoc ? baseDoc.config : baseDoc
  if (!validate(base)) preexisting = new Set(summarize(validate.errors).flatMap(key))
}

const fresh = found
  .map(({details, path}) => ({details: details.filter((d) => !preexisting.has(`${path} :: ${d}`)), path}))
  .filter(({details}) => details.length > 0)

const scope = args.baseline ? ' new since the baseline' : ''

if (fresh.length === 0) {
  const note = args.baseline && found.length ? ` ${preexisting.size} pre-existing issue(s) ignored.` : ''
  const what = args.baseline ? 'no new problems since the baseline' : 'no problems'
  console.log(`Schema OK — ${what} in ${args.config} (schemaVersion ${config.schemaVersion}).${note}`)
  process.exit(0)
}

console.error(`Schema FAILED — ${fresh.length} location(s)${scope} in ${args.config} (schemaVersion ${config.schemaVersion}):\n`)
for (const {details, path} of fresh.slice(0, MAX_REPORTED)) {
  console.error(`  ${path || '/'}`)
  for (const detail of details) console.error(`      ${detail}`)
}
if (fresh.length > MAX_REPORTED) console.error(`\n  … and ${fresh.length - MAX_REPORTED} more locations.`)
if (!args.baseline) {
  console.error(
    '\nIf this flow predates the schema, most of these are version drift, not mistakes. ' +
      'Re-run with --baseline flow.backup.json to see only what your edit introduced.',
  )
}

process.exit(1)

#!/usr/bin/env node
/**
 * Build the "Test on Device" link for a saved flow, and render it as a QR code to scan.
 *
 *   npm i --prefix ~/.cache/adapty-flow-qr qrcode        # ONCE, and only if you want the PNG
 *   (cd ~/.cache/adapty-flow-qr && node <this-file> --app <APP_UUID> --flow <FLOW_ID> \
 *     --config /abs/path/flow.working.json --qr)
 *
 * Prints the link, then the flow's locales, then — with --qr — a file:// URL for the QR image and
 * its plain path. Without --qr it prints the link alone and never loads `qrcode`.
 *
 * --qr writes `flow-preview-qr-<flowid8>.png` NEXT TO THE CONFIG, which is the working directory
 * the reader can actually open a file from. It is a throwaway; regenerate rather than keep it.
 * --out <path> overrides the location.
 *
 * This is the same link the Flow Builder shows behind its "Test on Device" button. It is pure
 * string construction — no network, no auth, nothing from Adapty's servers — which is why it lives
 * here rather than in the CLI. What it needs is the app id, the flow id, and the flow's locales.
 *
 * IT PREVIEWS WHAT IS SAVED, NOT YOUR LOCAL FILE. The app opens the link and fetches the flow's
 * current draft from Adapty, so `config update` has to have run first. That makes this a phase-5
 * tool, the opposite of `flows config preview`, which renders a local file and never saves.
 * Because the app re-fetches, one link stays good across later writes — hand it over once.
 *
 * Print THIS url freely: it is ~170 characters and every part of it is meaningful. That is the
 * opposite of the `flows config preview` render URL, which is thousands of characters of gzipped
 * base64 and must never be printed (preview.md explains why).
 *
 * PATHS: `--config` and `--out` are resolved against the CURRENT directory, and the install line
 * above runs this from the cache dir. Pass both as ABSOLUTE paths, or the read fails and the PNG
 * lands somewhere you are not looking — the same trap gates.sh documents for its schema step.
 *
 * Exits 0 on success, 1 when the flow has no locales to build a link from, 2 on bad usage.
 */

import {readFileSync} from 'node:fs'
import {createRequire} from 'node:module'
import {delimiter, dirname, join, resolve} from 'node:path'
import {parseArgs} from 'node:util'

/** Where the Adapty app picks the link up. Override for a staging build of the app. */
const DEFAULT_HOST = 'https://mobile-app.adapty.io'
const PREVIEW_PATH = '/flow-preview'

/**
 * The Flow Builder hardcodes `us` and carries a TODO to derive it from app config. Nothing on the
 * developer API exposes an app's cluster, so this matches the dashboard rather than guessing:
 * an EU or CN app gets a US link in both places. Pass --cluster to override.
 */
const DEFAULT_CLUSTER = 'us'

const USAGE =
  'Usage: node mobile-preview.mjs --app <APP_UUID> --flow <FLOW_ID>\n' +
  '         (--config <flow.json> | --locales <en,uk>) [--locale <id|code>]\n' +
  '         [--qr | --out <qr.png>] [--cluster <us>] [--host <url>]'

function fail(message) {
  console.error(`${message}\n${USAGE}`)
  process.exit(2)
}

/** qrcode is a run-time dependency of the caller: this script, npx, or the current project. */
function loadQrcode() {
  const roots = [
    process.cwd(),
    ...(process.env.PATH ?? '')
      .split(delimiter)
      .filter((dir) => dir.endsWith(join('node_modules', '.bin')))
      .map((dir) => join(dir, '..')),
  ]

  for (const root of roots) {
    try {
      return createRequire(join(root, 'noop.js'))('qrcode')
    } catch {
      continue
    }
  }

  console.error(
    'Could not resolve qrcode. Install it ONCE (`npm i --prefix ~/.cache/adapty-flow-qr qrcode`) '
    + 'and run from that directory. Drop --qr to skip the image and just print the link.',
  )
  process.exit(1)
}

/**
 * Locales live in the flow config as `locales: [{id, code, name}]` with `defaultLocale` naming one
 * by **id**. The link wants codes, so the id is resolved rather than passed through — they are
 * equal in every config seen so far, which is exactly why getting it wrong would go unnoticed.
 *
 * The backend stores locales as opaque dicts, so nothing upstream guarantees the shape.
 */
function readLocales(config) {
  if (typeof config !== 'object' || config === null || !Array.isArray(config.locales)) return []

  return config.locales
    .filter((entry) => typeof entry === 'object' && entry !== null && typeof entry.code === 'string')
    .map((entry) => ({code: entry.code, id: typeof entry.id === 'string' ? entry.id : entry.code}))
}

function resolveLocales(locales, defaultLocaleId, requested) {
  if (locales.length === 0) {
    console.error(
      'This flow has no locales in its config, so there is no link to build. Add a localization in '
      + 'the builder, or pass --locales explicitly if you know the codes.',
    )
    process.exit(1)
  }

  let current
  if (requested) {
    current = locales.find((locale) => locale.id === requested || locale.code === requested)
    if (!current) fail(`Flow has no locale "${requested}". Available: ${locales.map((l) => l.code).join(', ')}.`)
  } else {
    current = locales.find((locale) => locale.id === defaultLocaleId) ?? locales[0]
  }

  return {codes: locales.map((locale) => locale.code), current: current.code}
}

/**
 * Assembled by hand rather than through URLSearchParams, which percent-encodes the `locales`
 * separator as %2C. The app is only known to accept the dashboard's spelling — a literal comma —
 * so this emits the same bytes rather than betting that it decodes. Every value is a UUID or a
 * locale code, so nothing here needs escaping anyway.
 */
function buildUrl({appId, cluster, flowId, host, locales}) {
  let origin
  try {
    origin = new URL(host).origin
  } catch {
    fail(`Invalid --host: ${host}`)
  }

  const query = [
    `app_id=${appId}`,
    `flow_id=${flowId}`,
    `current_locale=${locales.current}`,
    `locales=${locales.codes.join(',')}`,
    `cluster=${cluster}`,
  ].join('&')

  return `${origin}${PREVIEW_PATH}?${query}`
}

const UUID_RE = /^[\da-f]{8}-[\da-f]{4}-[\da-f]{4}-[\da-f]{4}-[\da-f]{12}$/i

let parsed
try {
  parsed = parseArgs({
    options: {
      app: {type: 'string'},
      cluster: {type: 'string'},
      config: {type: 'string'},
      flow: {type: 'string'},
      host: {type: 'string'},
      locale: {type: 'string'},
      locales: {type: 'string'},
      out: {type: 'string'},
      qr: {type: 'boolean'},
    },
  })
} catch (error) {
  fail(error.message)
}

const {values} = parsed
if (!values.app) fail('--app is required.')
if (!values.flow) fail('--flow is required.')
if (!UUID_RE.test(values.app)) fail(`--app is not a UUID: ${values.app}`)
if (!UUID_RE.test(values.flow)) fail(`--flow is not a UUID: ${values.flow}`)
if (!values.config && !values.locales) fail('Pass --config <flow.json>, or --locales <en,uk>.')

let locales
let defaultLocaleId = null
let configDir = null
if (values.locales) {
  const codes = values.locales.split(',').map((code) => code.trim()).filter(Boolean)
  if (codes.length === 0) fail('--locales is empty.')
  locales = codes.map((code) => ({code, id: code}))
} else {
  let config
  try {
    config = JSON.parse(readFileSync(resolve(values.config), 'utf8'))
  } catch (error) {
    fail(`Could not read --config ${values.config}: ${error.message}`)
  }

  // Accepts either a `config get` envelope or a bare config, like the other scripts here.
  const flow = typeof config?.config === 'object' && config.config !== null ? config.config : config
  locales = readLocales(flow)
  defaultLocaleId = typeof flow?.defaultLocale === 'string' ? flow.defaultLocale : null
  configDir = dirname(resolve(values.config))
}

const resolved = resolveLocales(locales, defaultLocaleId, values.locale)
const url = buildUrl({
  appId: values.app,
  cluster: values.cluster ?? DEFAULT_CLUSTER,
  flowId: values.flow,
  host: values.host ?? DEFAULT_HOST,
  locales: resolved,
})

console.log(url)
console.log(`locale ${resolved.current} of ${resolved.codes.join(', ')}`)

// The QR is only ever a PNG. Character-art QRs were tried and dropped: a half-block grid is 29-31
// rows of noise in an answer, and whether it scans at all depends on the reader's terminal theme,
// because the glyphs take its foreground colour. A file scans at whatever size it is opened at.
if (values.qr || values.out) {
  const QRCode = loadQrcode()

  // Default the image NEXT TO THE CONFIG, not into the current directory: the documented invocation
  // runs this from the `qrcode` cache dir, so a relative path would land there — and an image
  // outside the working directory is one the reader's viewer refuses to open, which is the whole
  // point of emitting a file. The config is already in the working tree, so it is the right anchor.
  //
  // Named per flow so two flows in one session do not overwrite each other's code. It is a
  // throwaway: regenerate it rather than keeping it, and it does not belong in a commit.
  let target
  if (values.out) {
    target = resolve(values.out)
  } else if (configDir) {
    target = join(configDir, `flow-preview-qr-${values.flow.slice(0, 8)}.png`)
  } else {
    fail('--qr needs --config to know where to write. Pass --out <path> instead.')
  }

  await QRCode.toFile(target, url, {margin: 2, scale: 8, type: 'png'})
  // A file:// URL so the reader can open the image from wherever they are reading — most terminals
  // linkify it. The plain path follows for the ones that do not.
  console.log(`file://${target}`)
  console.log(target)
}

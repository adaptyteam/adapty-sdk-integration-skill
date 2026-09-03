#!/usr/bin/env node
/**
 * Build the "Test on Device" link for a saved flow, and render it as a QR code to scan.
 *
 *   npm i --prefix ~/.cache/adapty-flow-qr qrcode        # ONCE, and only if you want the PNG
 *   (cd ~/.cache/adapty-flow-qr && node <this-file> --app <APP_UUID> --flow <FLOW_ID> \
 *     --config /abs/path/flow.working.json --qr)
 *
 * Prints the link, then the flow's locales, then — with --qr — a ready-to-paste markdown image line
 * and either `opened <path>` or the opener command. Without --qr it prints the link alone and never
 * loads `qrcode`.
 *
 * THE QR IS ALWAYS A PNG. --qr writes it, OPENS it in the OS viewer, and prints a ready-to-paste
 * `![...](...)` line for a client that renders images. Opening is the point: a terminal reader gets
 * a window with a code in it rather than a path to act on. --no-open (and CI) skip that and print
 * the opener command instead. There is deliberately no character-art rendering — see preview.md,
 * which records the two attempts and why the arithmetic rules it out.
 *
 * --qr writes `flow-preview-qr-<flowid8>.png` NEXT TO THE CONFIG, i.e. inside the working tree,
 * because a client refuses to render an image outside the directory it resolves from. Pass
 * --md-base <dir> (normally your working directory) to get the markdown path relative to it;
 * without it the path is absolute, which clients reject. --out <path> overrides the location.
 * The image is a throwaway: regenerate rather than keep it, and do not commit it.
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

import {spawnSync} from 'node:child_process'
import {readFileSync} from 'node:fs'
import {createRequire} from 'node:module'
import {delimiter, dirname, isAbsolute, join, relative, resolve} from 'node:path'
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
  '         [--qr | --out <qr.png>] [--md-base <dir>] [--no-open] [--cluster <us>] [--host <url>]'

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
      'md-base': {type: 'string'},
      'no-open': {type: 'boolean'},
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

  // scale 4 puts a 53-module code at 228px / ~4KB: about 0.9mm per module on a 110dpi screen, which
  // scans, and small enough inline that it reads as an affordance rather than a wall. Do not go
  // below this without re-checking on a real phone — module size is what a camera needs, and the
  // matrix does not shrink just because the image does.
  await QRCode.toFile(target, url, {margin: 2, scale: 4, type: 'png'})

  // Emit BOTH lines and let the surface sort it out — you cannot detect which one applies, and the
  // costs are asymmetric (see SKILL.md). Line 1 renders the code inline where images work and
  // degrades to its alt text plus the filename where they do not. Line 2 is how a terminal reader
  // actually gets to the image.
  //
  // The path is relative to --md-base (give it the directory the reader's client resolves from,
  // normally your working directory). An ABSOLUTE path is what clients reject: the report was
  // "This file is outside the working directory. It can't be opened here." So a relative path
  // inside that base is the whole trick.
  const base = values['md-base'] ? resolve(values['md-base']) : null
  const shown = base ? relative(base, target) : target
  if (base && (shown.startsWith('..') || isAbsolute(shown))) {
    console.error(
      `warning: ${target} is outside --md-base ${base}, so a client will refuse to render it inline. `
      + 'Write the QR inside the directory your client resolves from.',
    )
  }

  console.log(`![Scan to preview on your phone](${shown})`)

  // Then OPEN it, rather than printing something for the reader to act on.
  //
  // A file:// URL was the first attempt and is not clickable in a terminal (reported from a real
  // one) — a path with seven useless characters in front of it. Printing `open <path>` instead was
  // the second, and it still makes the reader copy-paste before they can scan anything. So do the
  // step for them: `flows config preview` already opens a browser on a TTY rather than handing over
  // a URL, and this is the same move.
  //
  // Best-effort by design. Headless hosts, CI and containers have nothing to open with, and that is
  // not a failure of the run — the image and its path are still the deliverable, so fall back to
  // printing the command and carry on. --no-open skips the attempt entirely.
  const opener = process.platform === 'darwin' ? 'open' : process.platform === 'win32' ? 'start' : 'xdg-open'
  const skipOpen = values['no-open'] || process.env.CI
  let opened = false
  if (!skipOpen) {
    try {
      const {status} = spawnSync(opener, [target], {stdio: 'ignore', timeout: 5000})
      opened = status === 0
    } catch {
      opened = false
    }
  }

  console.log(opened ? `opened ${target}` : `${opener} ${target}`)
}

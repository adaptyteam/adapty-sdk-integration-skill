#!/usr/bin/env node
/**
 * Headless screenshot capture for a flow-config preview.
 *
 * Point it at the file `adapty flows config get` gave you:
 *
 *   npm i --prefix ~/.cache/adapty-flow-playwright playwright        # ONCE, not per call
 *   (cd ~/.cache/adapty-flow-playwright && node <this-file> --config flow.working.json \
 *     --screen <screen_id> --out preview.png
 *
 * It opens the render page on a short URL and hands the config to the page's file input, so the
 * config never travels through the address bar. That matters: `adapty flows config preview` packs
 * the whole config into the URL fragment, which runs to ~113K characters for a large flow and
 * makes the render page fail to boot. Use that command for a quick look by hand; use this script
 * for anything captured.
 *
 * Chromium is needed once: `npx playwright install chromium`.
 *
 * An agent that already has a browser or computer-use tool should skip this script and drive the
 * page the same way: open <app-url>/flow-preview?screen=…&device=…&orientation=…, set the config
 * file on [data-testid="preview-config-input"], then screenshot [data-screen-content].
 */

import {readFileSync} from 'node:fs'
import {createRequire} from 'node:module'
import {basename, delimiter, join, resolve} from 'node:path'
import {parseArgs} from 'node:util'

const CONFIG_INPUT_SELECTOR = '[data-testid="preview-config-input"]'
const SCREEN_CONTENT_SELECTOR = '[data-screen-content]'
const DEFAULT_APP_URL = 'https://app.adapty.io'
const SETTLE_MS = 500
const TIMEOUT_MS = 30_000

const USAGE =
  'Usage: node preview-with-playwright.mjs --config <flow.json> [--screen <id>]\n' +
  '         [--device iphone-14] [--orientation portrait] [--out preview.png] [--app-url <url>]'

function fail(message) {
  console.error(`${message}\n${USAGE}`)
  process.exit(2)
}

/** Playwright is a run-time dependency of the caller: this script, npx, or the current project. */
async function loadChromium() {
  try {
    // eslint-disable-next-line import/no-unresolved -- supplied at run time, never a CLI dependency
    return (await import('playwright')).chromium
  } catch {
    // Not resolvable from this file; fall back to the caller's project and to any node_modules
    // that npx put on PATH.
    const roots = [
      process.cwd(),
      ...(process.env.PATH ?? '')
        .split(delimiter)
        .filter((dir) => dir.endsWith(join('node_modules', '.bin')))
        .map((dir) => join(dir, '..')),
    ]

    for (const root of roots) {
      try {
        return createRequire(join(root, 'noop.js'))('playwright').chromium
      } catch {
        continue
      }
    }

    console.error(
      'Could not resolve Playwright. Run this script through `npx --yes --package=playwright node ...`, or `npm i -D playwright` first.',
    )
    process.exit(1)
  }
}

/**
 * The render page insists on `{flow, remoteConfigs}`, which is neither of the two shapes you
 * actually have on disk: `flows config get` returns `{config, remote_configs, …}`, and
 * `validate`/`update` take the bare flow. Accept all three so the caller never has to care.
 */
function normalize(doc) {
  if (doc && typeof doc === 'object' && 'flow' in doc) return doc
  if (doc && typeof doc === 'object' && 'config' in doc) {
    return {flow: doc.config, remoteConfigs: doc.remote_configs ?? doc.remoteConfigs ?? null}
  }

  return {flow: doc, remoteConfigs: null}
}

let args
try {
  ;({values: args} = parseArgs({
    options: {
      'app-url': {type: 'string'},
      config: {type: 'string'},
      device: {default: 'iphone-14', type: 'string'},
      orientation: {default: 'portrait', type: 'string'},
      out: {default: 'preview.png', type: 'string'},
      screen: {type: 'string'},
    },
  }))
} catch (error) {
  fail(error.message)
}

if (!args.config) fail('No config: pass --config <path to the flow JSON>.')

let payload
try {
  payload = normalize(JSON.parse(readFileSync(resolve(args.config), 'utf8')))
} catch (error) {
  fail(`Could not read ${args.config}: ${error.message}`)
}

// Default to the flow's first screen, the same as the CLI does.
const screen = args.screen ?? payload.flow?.screens?.[0]?.id
if (!screen) fail(`No screen to render: ${args.config} has no screens, and --screen was not given.`)

const appUrl = (args['app-url'] ?? process.env.ADAPTY_APP_URL ?? DEFAULT_APP_URL).replace(/\/+$/, '')
const url = `${appUrl}/flow-preview?screen=${encodeURIComponent(screen)}&device=${encodeURIComponent(
  args.device,
)}&orientation=${encodeURIComponent(args.orientation)}`

const chromium = await loadChromium()

let browser
try {
  browser = await chromium.launch({headless: true})
} catch (error) {
  console.error(`Could not launch headless Chromium. Run \`npx playwright install chromium\`.\n${error.message}`)
  process.exit(1)
}

/** Errors here run to dozens of lines of Playwright call log; the first few carry all the signal. */
const brief = (error) => String(error?.message ?? error).split('\n').slice(0, 3).join('\n')

try {
  const page = await browser.newPage()
  page.setDefaultTimeout(TIMEOUT_MS)

  // `load` is the wrong signal: the render host runs third-party analytics that never settle, so
  // `load` and `networkidle` can hang long past the point where the screen is fully drawn.
  try {
    await page.goto(url, {waitUntil: 'domcontentloaded'})
  } catch (error) {
    console.error(
      `Could not open ${url}\n${brief(error)}\n` +
        'Check --app-url / $ADAPTY_APP_URL — it must point at a host that is up.',
    )
    process.exit(1)
  }

  await page.locator(CONFIG_INPUT_SELECTOR).setInputFiles({
    buffer: Buffer.from(JSON.stringify(payload)),
    mimeType: 'application/json',
    name: basename(args.config),
  })

  const content = page.locator(SCREEN_CONTENT_SELECTOR).first()

  try {
    await content.waitFor({state: 'visible'})
  } catch (error) {
    // The page reports config problems as plain text where the screen would be; show that instead
    // of a timeout, since it names the actual fault.
    const shown = await page.evaluate(() => document.body.innerText ?? '').catch(() => '')
    console.error(
      `The render page never drew ${SCREEN_CONTENT_SELECTOR} within ${TIMEOUT_MS / 1000}s.\n` +
        (shown.trim() ? `Page says: ${shown.trim().slice(0, 300)}` : brief(error)),
    )
    process.exit(1)
  }

  await page.waitForTimeout(SETTLE_MS)
  await content.screenshot({path: resolve(args.out), type: 'png'})
  console.log(resolve(args.out))
} finally {
  await browser.close()
}

# Adapty Skills

[![skills.sh](https://skills.sh/b/adaptyteam/adapty-skills)](https://skills.sh/adaptyteam/adapty-skills)

Subscriptions are the part of a mobile app nobody wants to build and everybody has to — SDK wiring, paywall UI, store config, then the ads and tests that make it pay.

**These skills hand that whole surface to the agent you already have open.**

```
> /adapty-integration

  Detected Flutter — pubspec.yaml, ios/ and android/ present

? Paywall approach          → Flow Builder (no-code editor)
? Integrations              → Amplitude, AppsFlyer
? Adapty app                → Create a new one

  Creating app, access level, products and placement via the Adapty CLI…
  Fetching flutter-sdk-overview docs before writing Stage 1…
```

**Supported platforms:** iOS · Android · Flutter · React Native · Unity · Kotlin Multiplatform · Capacitor

## The toolkit

Every install below gives you the whole toolkit — and it grows, so an update brings new skills with it.

| Skill | What it does | Needs |
|---|---|---|
| [`adapty-integration`](#integrating-the-sdk) | Sets up in-app purchases end to end — dashboard, SDK, paywall, store config — or moves you over from another purchase system | Adapty CLI |
| [`ads-manager`](#managing-apple-search-ads) | Runs your Apple Search Ads: performance across campaigns and keywords, bid and budget changes, search-term harvesting, campaigns on and off | Adapty CLI, Apple Ads account |
| [`flow-audit`](#auditing-a-flow) | Answers "did I forget anything?" before you publish a flow — triggers, products, variables — with a verdict and ranked fixes | Adapty CLI |
| [`flow-generator`](#building-flows-and-paywalls) | Builds a paywall or onboarding flow, or changes one you have: translate it, rewrite the copy, add or reorder screens, add tabs and plan pickers, wire quiz branching | Adapty CLI |
| [`paywall-teardown`](#tearing-down-a-paywall) | Reads any paywall — yours, a competitor's, a work in progress — and ranks what to change and test | nothing |

The Adapty CLI comes from `npm install -g adapty`. You don't have to keep it current — the skills check the version themselves and fetch a newer one when they need it, rather than telling you a command doesn't exist.

## Install

### Claude Code

```bash
claude plugin marketplace add adaptyteam/adapty-skills
claude plugin install adapty-skills@adapty
```

Then run `/reload-plugins` inside Claude Code. One plugin, `adapty-skills`, carries every skill in the repo.

<details>
<summary><strong>Already installed as <code>adapty-sdk-integration</code>?</strong></summary>

<br>

That handle still works and still updates, so nothing breaks if you do nothing. To move over, install the new one and remove the old one — leaving both installed loads the same skills twice:

```bash
claude plugin install adapty-skills@adapty
claude plugin uninstall adapty-sdk-integration@adapty
```

The skill you invoke is now `/adapty-integration` (previously `/adapty-sdk-integration`).

</details>

### Any agentic CLI

The [skills CLI](https://skills.sh) installs into any supported agent — Cursor, Copilot, Codex, Gemini CLI, Zed, Amp, and more:

```bash
npx skills add adaptyteam/adapty-skills --all
```

`--all` is `--skill '*' --agent '*' -y`: every skill, every agent it detects, no prompts. Drop it and the CLI asks which ones you want, which is fine at a keyboard but hangs in a script.

For one skill only, name it:

```bash
npx skills add adaptyteam/adapty-skills --skill ads-manager
```

Skills installed this way don't update automatically. To get the latest later:

```bash
npx skills update
```

### Copy the directories

The skills are portable directories under `skills/`, and every CLI below reads the same Claude-style `SKILL.md` format — so copying them into place works. The `skills/*` glob takes all of them.

**GitHub Copilot CLI** — [docs](https://docs.github.com/en/copilot/concepts/agents/about-agent-skills):

```bash
git clone https://github.com/adaptyteam/adapty-skills.git
cp -r adapty-skills/skills/* ~/.copilot/skills/
```

**OpenAI Codex CLI** — [docs](https://developers.openai.com/codex/skills). Use `~/.agents/skills/` for personal, `<repo>/.agents/skills/` for project:

```bash
git clone https://github.com/adaptyteam/adapty-skills.git
cp -r adapty-skills/skills/* ~/.agents/skills/
```

**Gemini CLI** — [docs](https://geminicli.com/docs/cli/skills/):

```bash
gemini skills install https://github.com/adaptyteam/adapty-skills
# or manually:
git clone https://github.com/adaptyteam/adapty-skills.git
cp -r adapty-skills/skills/* ~/.gemini/skills/
```

## Integrating the SDK

Working in-app purchases: dashboard, SDK code, paywall, store config. Open your mobile project in your agentic CLI and run:

```
/adapty-integration
```

(In CLIs that don't map slash commands to skills, "Use the adapty-integration skill" does the same. That holds for every skill below.)

The skill takes over from there. It will:

1. **Detect the platform** from the project structure
2. **Ask three questions** — paywall approach, third-party integrations, and whether to use an existing Adapty app or create a new one
3. **Configure the Adapty dashboard** via the Adapty CLI
4. **Implement the SDK** stage by stage, fetching the latest docs before writing each piece of code
5. **Verify each step** with build checks and visual checkpoints before moving on

You'll be asked for your Adapty credentials and a few decisions along the way — the rest is automated.

### Flow & paywall approaches

- **Flow Builder** (recommended) — Adapty renders paywalls *and* onboarding in a no-code editor; nothing to build. On Unity and Capacitor this is Paywall Builder, the previous generation, which does paywalls only
- **Custom paywall** — you build the UI; Adapty provides products and handles purchases
- **Observer mode** — keep your existing StoreKit / Billing code; Adapty tracks events only

## Managing Apple Search Ads

An analyst on your ad account — bids, budgets, keyword harvests, dead-ad diagnosis.

You need a connected Apple Search Ads account and an active Ads Manager subscription — `adapty asa whoami` tells you where you stand.

Open your terminal in any directory and ask for it:

```
/ads-manager
```

It covers ten workflows: orienting on your account, reporting performance, launching a campaign, harvesting keywords from search terms, a bid-and-budget optimization pass, pausing or resuming, running ads against a custom product page, diagnosing an ad that isn't serving, rule-based automations, and a competitor check.

**It treats your ad account as live money.** There is no delete and no undo in this surface, so the skill confirms before every write, never invents an ID or a budget, prefers small keyword batches, and pins idempotency keys so a re-run can't double-apply. Reads and automation dry runs are free, and it uses them freely.

## Auditing a flow

The broken product binding, caught before your users find it. `flow-audit` answers one question: **is this Flow Builder flow ready for production?**

**It's read-only.** It never calls `flows config update`, `products create`, or `flows create` — it fetches the flow's config and cross-references it against your live dashboard (catalog, access levels) to catch what an offline checker can't, like a bound product that doesn't exist or a card whose copy claims a period the product doesn't have.

```
/flow-audit
```

(Or "audit my flow" / "is this ready to publish?")

It checks six families — triggers, store compliance, products, variables, localization, and placeholders — and comes back with a verdict (`READY FOR PRODUCTION`, `NOT READY — n blockers`, or `READY, PENDING n CHECKS I CANNOT MAKE`), ranked findings with a concrete fix for each, and a `WHAT TO DO NEXT` section that routes every finding into what you need to answer, what the agent can fix in the flow, what only you can change in the dashboard, and what's optional.

**It never certifies what it couldn't see.** A question it can't answer from the data — can the host app dismiss this paywall on its own, is the flow attached to a placement — keeps the verdict from reading a bare `READY` until you've weighed in. When you want something fixed, it hands the findings to `flow-generator`, which owns the actual write.

## Building flows and paywalls

Describe the screen you want and get it built — or change one you already have, without opening the editor. `flow-generator` writes an [Adapty Flow Builder](https://adapty.io/docs/adapty-flow-builder) flow as JSON.

**It authors new flows, and it transforms flows that exist.** Authoring is what most people reach for: product IDs come from your catalog (it asks which to use before designing anything), and the only things it will never invent are uploaded images and videos, real store prices, and proof numbers like ratings — those it asks you for, or leaves visibly out. Transforming your own flow is the safer path when you have one — theme, fonts, locales and products are inherited, so everything the skill writes is real.

It reads and writes the config through the Adapty CLI, so you don't export or upload anything by hand, and it sorts out the CLI itself rather than telling you a command doesn't exist.

```
/flow-generator
```

It runs five phases: authenticate, work out whether to create a flow or edit an existing one, validate the config, preview it and iterate until it looks right, then save and hand the publish back to you. Validate and preview both run on a local file, so the agent gets it right before anything reaches your dashboard.

Four transforms:

- **Add a locale** — extend the flow's locales and fill in every localizable field
- **Rewrite copy** — change wording without touching structure
- **Screens** — add, remove, or reorder, repairing the navigation that a deletion breaks
- **Branching and conditions** — selectable groups, option IDs, and the conditional actions that route on them

**It saves to a draft; it never publishes.** There is no publish command in the CLI and no delete either, so both stay yours. Every write after the first carries the flow's `updated_at` as an optimistic lock, so a save can't quietly overwrite an edit someone else made in the meantime — it fails instead. It asks before creating a product. And because a config can save cleanly and still not render, the agent screenshots the preview and looks at it before telling you it's done.

## Tearing down a paywall

A screenshot turned into a ranked list of things to test. Alone among them, `paywall-teardown` needs **no CLI, no account and no credentials** — it reads what you give it and writes nothing anywhere.

Paste a paywall screenshot and say roughly nothing:

```
/paywall-teardown
```

(Or just drop the image in — "here's my paywall" is enough.)

You get back a read of the vertical and its trust axis, a line on what's already working, and 5–8 prioritized rows: the named pattern, the specific change applied to *your* screen, where that pattern shows up across categories, and an expected-impact range. It handles competitor screenshots and half-finished designs too.

**It also works forwards.** Ask for a paywall instead of a critique of one — or hand an agent "add a paywall screen" with no design attached — and the library becomes the reference the agent designs against: a build list of the patterns that belong on the screen for your category, in priority order, plus the short list of real values it refuses to invent for you (your actual rating, your actual review count, your actual outcome data, your hero asset). Then it grades the result and fixes what it finds, rather than handing you a report on a screen it just built. `flow-generator` calls it at both ends for exactly this — before it writes the config, and again over the render — so a generated screen is held to the same library a live one would be. If you *do* give a design reference, that reference wins; the library only fills what it leaves unsaid.

Impact ranges are expected effect calibrated from Adapty's teardowns of top subscription apps across many verticals — not measured lift for your app. Ship the tests and get your own numbers.

## Requirements

- An agentic CLI that supports the Claude Skills format — [Claude Code](https://claude.com/claude-code), [GitHub Copilot CLI](https://docs.github.com/en/copilot/concepts/agents/about-agent-skills), [OpenAI Codex](https://developers.openai.com/codex/skills), or [Gemini CLI](https://geminicli.com/docs/cli/skills/)
- An [Adapty account](https://app.adapty.io/) (free tier works)

Adapty SDK overviews: [iOS](https://adapty.io/docs/ios-sdk-overview) · [Android](https://adapty.io/docs/android-sdk-overview) · [Flutter](https://adapty.io/docs/flutter-sdk-overview) · [React Native](https://adapty.io/docs/react-native-sdk-overview) · [Unity](https://adapty.io/docs/unity-sdk-overview) · [Kotlin Multiplatform](https://adapty.io/docs/kmp-sdk-overview) · [Capacitor](https://adapty.io/docs/capacitor-sdk-overview)

### Corporate environments with a domain allowlist

If your agent runs somewhere with restricted outbound network access — Claude Cowork on a corporate plan, a managed sandbox, an egress proxy — an administrator has to allow both:

```
adapty.io
*.adapty.io
```

**List both.** A wildcard does not cover the apex domain in most allowlist implementations, and the apex is where almost everything goes: the skills fetch documentation from `adapty.io/docs/...` (the large majority of requests), the dashboard is `app.adapty.io`, and the Adapty CLI talks to `api-admin.adapty.io` and, for Apple Search Ads, `api-asa-admin.adapty.io`. Allowing only `*.adapty.io` blocks the docs the agent reads before writing any code.

## Feedback

`adapty-integration` is the only skill here that sends anything back. At the end of a successful integration it asks whether you'd like to share anonymous signals — platform, steps completed, rating — with no code, no project details and nothing identifying. Say no and nothing is sent. Every other skill here collects nothing at any point.

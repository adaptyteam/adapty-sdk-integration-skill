# adapty-skills

[![skills.sh](https://skills.sh/b/adaptyteam/adapty-skills)](https://skills.sh/adaptyteam/adapty-skills)

A skill for agentic coding tools (Claude Code, GitHub Copilot CLI, OpenAI Codex, Gemini CLI) that guides you through integrating the [Adapty](https://adapty.io) SDK into a mobile app end-to-end — dashboard setup, SDK install, paywall, and store configuration — step by step, with the agent doing the work and pointing you to the right docs when input is needed.

**Supported platforms:** iOS · Android · Flutter · React Native · Unity · Kotlin Multiplatform · Capacitor

> **Also in this repo: `ads-manager`, `flow-generator` and `paywall-teardown`.** Every install below ships three more skills. `ads-manager` runs your Apple Search Ads through the Adapty CLI — reading campaign, ad group and keyword performance, changing bids and budgets, harvesting search terms, launching and pausing campaigns; needs `adapty` **0.4.0 or newer** for the `adapty asa` commands. `flow-generator` edits a Flow Builder config through the CLI's `flows` commands — adding a locale, rewriting copy, adding or removing screens, wiring branching — validating and previewing before it saves; needs `adapty` **0.6.0 or newer**, or **0.7.0** for the preview command (`flows config validate` is beta-only and its endpoint is not live yet). `paywall-teardown` reads a paywall screenshot and hands back ranked, testable conversion hypotheses — no CLI, no account, no install. See [Managing Apple Search Ads](#managing-apple-search-ads), [Transforming a Flow Builder config](#transforming-a-flow-builder-config) and [Tearing down a paywall](#tearing-down-a-paywall) below.

## Quickstart

### Install

This repo holds **four skills** — `adapty-integration`, `ads-manager`, `flow-generator` and `paywall-teardown`. Every command below installs all four.

#### Claude Code

From your shell:

```bash
claude plugin marketplace add adaptyteam/adapty-skills
claude plugin install adapty-skills@adapty
```

Then run `/reload-plugins` inside Claude Code to activate them. One plugin, `adapty-skills`, carries every skill in the repo — installing it gives you all four.

> **Already installed as `adapty-sdk-integration`?** That handle still works and still updates, so nothing breaks if you do nothing. To move over, install the new one and remove the old one — leaving both installed loads the same skills twice:
>
> ```bash
> claude plugin install adapty-skills@adapty
> claude plugin uninstall adapty-sdk-integration@adapty
> ```
>
> The skill you invoke is now `/adapty-integration` (previously `/adapty-sdk-integration`).

#### Any agentic CLI (skills CLI)

The [skills CLI](https://skills.sh) installs into any supported agent — Cursor, Copilot, Codex, Gemini CLI, Zed, Amp, and more:

```bash
npx skills add adaptyteam/adapty-skills --all
```

`--all` is `--skill '*' --agent '*' -y`: every skill, every agent it detects, no prompts. Drop it and the CLI asks which of the four you want, which is fine at a keyboard but hangs in a script.

For one skill only, name it:

```bash
npx skills add adaptyteam/adapty-skills --skill ads-manager
```

Skills installed this way don't update automatically; to get the latest version later, run:

```bash
npx skills update
```

#### Tool-specific installs

All four skills are portable directories — `skills/adapty-integration/`, `skills/ads-manager/`, `skills/flow-generator/` and `skills/paywall-teardown/`. Every CLI below reads the same Claude-style `SKILL.md` format, so copying the directories in place works. The `skills/*` glob takes all of them.

**GitHub Copilot CLI**:

```bash
git clone https://github.com/adaptyteam/adapty-skills.git
cp -r adapty-skills/skills/* ~/.copilot/skills/
```

Docs: [About agent skills (GitHub)](https://docs.github.com/en/copilot/concepts/agents/about-agent-skills).

**OpenAI Codex CLI** — under `~/.agents/skills/` (personal) or `<repo>/.agents/skills/` (project):

```bash
git clone https://github.com/adaptyteam/adapty-skills.git
cp -r adapty-skills/skills/* ~/.agents/skills/
```

Docs: [Codex Skills](https://developers.openai.com/codex/skills).

**Gemini CLI** — install command, or drop the folders in place:

```bash
gemini skills install https://github.com/adaptyteam/adapty-skills
# or manually:
git clone https://github.com/adaptyteam/adapty-skills.git
cp -r adapty-skills/skills/* ~/.gemini/skills/
```

Docs: [Gemini CLI Skills](https://geminicli.com/docs/cli/skills/).

### Use

Open your mobile project in your agentic CLI and run:

```
/adapty-integration
```

(In CLIs that don't map slash commands to skills, just say "Use the adapty-integration skill" instead.)

The skill takes over from there. It will:

1. **Detect the platform** from the project structure
2. **Ask three questions** — paywall approach, third-party integrations, and whether to use an existing Adapty app or create a new one
3. **Configure the Adapty dashboard** via the Adapty CLI
4. **Implement the SDK** stage by stage, fetching the latest docs before writing each piece of code
5. **Verify each step** with build checks and visual checkpoints before moving on

You'll be asked for your Adapty credentials and a few decisions along the way — the rest is automated.

## Managing Apple Search Ads

The `ads-manager` skill in this repo operates Apple Search Ads through the Adapty CLI. It comes with every install above — you don't add anything.

**Requires `adapty` 0.4.0 or newer** (`npm install -g adapty`), which is where the `adapty asa` commands ship. You also need a connected Apple Search Ads account and an active Ads Manager subscription — `adapty asa whoami` tells you where you stand.

Open your terminal in any directory and ask for it:

```
/ads-manager
```

(Or "Use the ads-manager skill" in CLIs that don't map slash commands.)

It covers ten workflows: orienting on your account, reporting performance, launching a campaign, harvesting keywords from search terms, a bid-and-budget optimization pass, pausing or resuming, running ads against a custom product page, diagnosing an ad that isn't serving, rule-based automations, and a competitor check.

**It treats your ad account as live money.** There is no delete and no undo in this surface, so the skill confirms before every write, never invents an ID or a budget, prefers small keyword batches, and pins idempotency keys so a re-run can't double-apply. Reads and automation dry runs are free and it uses them freely.

## Transforming a Flow Builder config

The `flow-generator` skill edits an [Adapty Flow Builder](https://adapty.io/docs/adapty-flow-builder) flow as JSON. It comes with every install above too.

**It transforms a flow that exists — it does not author one from nothing.** Product UUIDs, icon SVG markup, uploaded images and videos, and your project's theme can't be invented; transforming your own flow inherits all of them, so everything the skill writes is real. Point it at a flow you already have, or ask it to start a new one from a copy of one.

The skill reads and writes the config with the Adapty CLI, so you don't export or upload anything by hand. **Requires `adapty` 0.6.0 or newer** (`npm install -g adapty`) for `flows` and `flows config get` / `update`, and **0.7.0** for `flows config preview` — which is the version `npm install -g adapty` gives you today. `flows config validate` is the one exception: it ships in the beta channel only and its endpoint is not live yet, so the skill falls back to its own checklist. If your global `adapty` is older, the skill runs everything through `npx --yes adapty@latest` instead of telling you a command doesn't exist.

It runs five phases: authenticate, work out whether to create a flow or edit an existing one, validate the config, preview it and iterate until it looks right, then save and hand the publish back to you. Validate and preview both run on a local file, so the agent gets it right before anything reaches your dashboard.

Ask for it:

```
/flow-generator
```

(Or "Use the flow-generator skill" in CLIs that don't map slash commands.)

Four transforms:

- **Add a locale** — extend the flow's locales and fill in every localizable field
- **Rewrite copy** — change wording without touching structure
- **Screens** — add, remove, or reorder, repairing the navigation that a deletion breaks
- **Branching and conditions** — selectable groups, option ids, and the conditional actions that route on them

**It saves to a draft; it never publishes.** There is no publish command in the CLI and no delete either, so both stay yours. Every write after the first carries the flow's `updated_at` as an optimistic lock, so a save can't quietly overwrite an edit someone else made in the meantime — it fails instead. It asks before creating a product. And because a config can save cleanly and still not render, the agent screenshots the preview and looks at it before telling you it's done.

## Tearing down a paywall

The `paywall-teardown` skill reads a paywall and hands back a ranked set of testable growth hypotheses. It ships with every install above, and unlike the other three it needs **no CLI, no account and no credentials** — it reads what you give it and writes nothing anywhere.

Paste a paywall screenshot and say roughly nothing:

```
/paywall-teardown
```

(Or just drop the image in — "here's my paywall" is enough.)

You get back a read of the vertical and its trust axis, a line on what's already working, and 5–8 prioritized rows: the named pattern, the specific change applied to *your* screen, where that pattern shows up across categories, and an expected-impact range. It handles competitor screenshots and half-finished designs too.

**It also works forwards.** Ask for a paywall instead of a critique of one — or hand an agent "add a paywall screen" with no design attached — and the library becomes the reference the agent designs against: a build list of the patterns that belong on the screen for your category, in priority order, plus the short list of real values it refuses to invent for you (your actual rating, your actual review count, your actual outcome data, your hero asset). Then it grades the result and fixes what it finds, rather than handing you a report on a screen it just built. `flow-generator` calls it at both ends for exactly this — before it writes the config, and again over the render — so a generated screen is held to the same library a live one would be. If you *do* give a design reference, that reference wins; the library only fills what it leaves unsaid.

Impact ranges are expected effect calibrated from Adapty's teardowns of top subscription apps across many verticals — not measured lift for your app. Ship the tests and get your own numbers.

## Paywall approaches

- **Paywall Builder** (recommended) — Adapty renders the UI in a no-code editor; nothing to build
- **Custom paywall** — you build the UI; Adapty provides products and handles purchases
- **Observer mode** — keep your existing StoreKit / Billing code; Adapty tracks events only

## Platform docs

Adapty SDK overviews: [iOS](https://adapty.io/docs/ios-sdk-overview) · [Android](https://adapty.io/docs/android-sdk-overview) · [Flutter](https://adapty.io/docs/flutter-sdk-overview) · [React Native](https://adapty.io/docs/react-native-sdk-overview) · [Unity](https://adapty.io/docs/unity-sdk-overview) · [Kotlin Multiplatform](https://adapty.io/docs/kmp-sdk-overview) · [Capacitor](https://adapty.io/docs/capacitor-sdk-overview)

## Requirements

- An agentic CLI that supports the Claude Skills format — [Claude Code](https://claude.com/claude-code), [GitHub Copilot CLI](https://docs.github.com/en/copilot/concepts/agents/about-agent-skills), [OpenAI Codex](https://developers.openai.com/codex/skills), or [Gemini CLI](https://geminicli.com/docs/cli/skills/)
- An [Adapty account](https://app.adapty.io/) (free tier works)

### Corporate environments with a domain allowlist

If your agent runs somewhere with restricted outbound network access — Claude Cowork on a corporate plan, a managed sandbox, an egress proxy — an administrator has to allow both:

```
adapty.io
*.adapty.io
```

**List both.** A wildcard does not cover the apex domain in most allowlist implementations, and the apex is where almost everything goes: the skills fetch documentation from `adapty.io/docs/...` (the large majority of requests), the dashboard is `app.adapty.io`, and the Adapty CLI talks to `api-admin.adapty.io` and, for Apple Search Ads, `api-asa-admin.adapty.io`. Allowing only `*.adapty.io` blocks the docs the agent reads before writing any code.

## Feedback

At the end of a successful integration, the skill optionally collects anonymous signals (platform, steps completed, rating) — no code, no project details, nothing identifying. Helps the Adapty team improve this guide.

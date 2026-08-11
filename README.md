# adapty-sdk-integration

[![skills.sh](https://skills.sh/b/adaptyteam/adapty-sdk-integration-skill)](https://skills.sh/adaptyteam/adapty-sdk-integration-skill)

A skill for agentic coding tools (Claude Code, GitHub Copilot CLI, OpenAI Codex, Gemini CLI) that guides you through integrating the [Adapty](https://adapty.io) SDK into a mobile app end-to-end — dashboard setup, SDK install, paywall, and store configuration — step by step, with the agent doing the work and pointing you to the right docs when input is needed.

**Supported platforms:** iOS · Android · Flutter · React Native · Unity · Kotlin Multiplatform · Capacitor

> **Also in this repo: `ads-manager`.** Every install below ships a second skill that runs your Apple Search Ads through the Adapty CLI — reading campaign, ad group and keyword performance, changing bids and budgets, harvesting search terms, launching and pausing campaigns. Needs `adapty` **0.4.0 or newer** for the `adapty asa` commands. See [Managing Apple Search Ads](#managing-apple-search-ads) below.

## Quickstart

### Install

#### Claude Code

From your shell:

```bash
claude plugin marketplace add adaptyteam/adapty-sdk-integration-skill
claude plugin install adapty-sdk-integration@adapty
```

Then run `/reload-plugins` inside Claude Code to activate it.

#### Any agentic CLI (skills CLI)

The [skills CLI](https://skills.sh) installs the skill into any supported agent — Cursor, Copilot, Codex, Gemini CLI, Zed, Amp, and more:

```bash
npx skills add adaptyteam/adapty-sdk-integration-skill
```

Skills installed this way don't update automatically; to get the latest version later, run:

```bash
npx skills update
```

#### Tool-specific installs

The skill is a portable directory — `skills/adapty-sdk-integration/` in this repo. All three CLIs below read the same Claude-style `SKILL.md` format.

**GitHub Copilot CLI** — install command, or drop the folder in place:

```bash
gh skill install adaptyteam/adapty-sdk-integration-skill
# or manually:
git clone https://github.com/adaptyteam/adapty-sdk-integration-skill.git
cp -r adapty-sdk-integration-skill/skills/adapty-sdk-integration ~/.copilot/skills/
```

Docs: [About agent skills (GitHub)](https://docs.github.com/en/copilot/concepts/agents/about-agent-skills).

**OpenAI Codex CLI** — drop the folder under `~/.agents/skills/` (personal) or `<repo>/.agents/skills/` (project):

```bash
git clone https://github.com/adaptyteam/adapty-sdk-integration-skill.git
cp -r adapty-sdk-integration-skill/skills/adapty-sdk-integration ~/.agents/skills/
```

Docs: [Codex Skills](https://developers.openai.com/codex/skills).

**Gemini CLI** — install command, or drop the folder in place:

```bash
gemini skills install https://github.com/adaptyteam/adapty-sdk-integration-skill
# or manually:
git clone https://github.com/adaptyteam/adapty-sdk-integration-skill.git
cp -r adapty-sdk-integration-skill/skills/adapty-sdk-integration ~/.gemini/skills/
```

Docs: [Gemini CLI Skills](https://geminicli.com/docs/cli/skills/).

### Use

Open your mobile project in your agentic CLI and run:

```
/adapty-sdk-integration
```

(In CLIs that don't map slash commands to skills, just say "Use the adapty-sdk-integration skill" instead.)

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

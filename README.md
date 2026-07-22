# adapty-sdk-integration

A skill for agentic coding tools (Claude Code, GitHub Copilot CLI, OpenAI Codex, Gemini CLI) that guides you through integrating the [Adapty](https://adapty.io) SDK into a mobile app end-to-end — dashboard setup, SDK install, paywall, and store configuration — step by step, with the agent doing the work and pointing you to the right docs when input is needed.

**Supported platforms:** iOS · Android · Flutter · React Native · Unity · Kotlin Multiplatform · Capacitor

## Quickstart

### Install

#### Claude Code

From your shell:

```bash
claude plugin marketplace add adaptyteam/adapty-sdk-integration-skill
claude plugin install adapty-sdk-integration@adapty
```

Then run `/reload-plugins` inside Claude Code to activate it.

#### Other agentic CLIs

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

## Paywall approaches

- **Paywall Builder** (recommended) — Adapty renders the UI in a no-code editor; nothing to build
- **Custom paywall** — you build the UI; Adapty provides products and handles purchases
- **Observer mode** — keep your existing StoreKit / Billing code; Adapty tracks events only

## Platform docs

Adapty SDK overviews: [iOS](https://adapty.io/docs/ios-sdk-overview) · [Android](https://adapty.io/docs/android-sdk-overview) · [Flutter](https://adapty.io/docs/flutter-sdk-overview) · [React Native](https://adapty.io/docs/react-native-sdk-overview) · [Unity](https://adapty.io/docs/unity-sdk-overview) · [Kotlin Multiplatform](https://adapty.io/docs/kmp-sdk-overview) · [Capacitor](https://adapty.io/docs/capacitor-sdk-overview)

## Requirements

- An agentic CLI that supports the Claude Skills format — [Claude Code](https://claude.com/claude-code), [GitHub Copilot CLI](https://docs.github.com/en/copilot/concepts/agents/about-agent-skills), [OpenAI Codex](https://developers.openai.com/codex/skills), or [Gemini CLI](https://geminicli.com/docs/cli/skills/)
- An [Adapty account](https://app.adapty.io/) (free tier works)

## Feedback

At the end of a successful integration, the skill optionally collects anonymous signals (platform, steps completed, rating) — no code, no project details, nothing identifying. Helps the Adapty team improve this guide.

# adapty-sdk-integration

A Claude Code skill that integrates Adapty SDK into a mobile app end-to-end — dashboard setup, SDK installation, paywall implementation, and third-party integrations — without the developer having to read docs or run CLI commands manually.

## What it does

When a developer asks to "integrate Adapty", "add a paywall", or "set up subscriptions", the skill takes over and:

1. **Detects the platform** by reading the project structure (iOS, Android, Flutter, React Native, Unity, KMP, Capacitor)
2. **Asks three questions** upfront — paywall approach, third-party integrations, and whether to use an existing Adapty app or create a new one
3. **Configures the Adapty dashboard** via the Adapty CLI — authenticates, selects or creates the app, creates products, paywalls, and placements
4. **Implements the SDK** stage by stage, fetching up-to-date docs before writing each piece of code
5. **Verifies each step** with build checks and user-confirmed visual checkpoints before moving on

## Platforms supported

iOS · Android · Flutter · React Native · Unity · Kotlin Multiplatform · Capacitor

## Paywall approaches

- **Paywall Builder** (recommended) — Adapty renders the paywall UI in a no-code editor; no UI to build
- **Custom paywall** — developer builds their own UI; Adapty fetches products and handles purchases
- **Observer mode** — keep existing StoreKit/Billing infrastructure; Adapty tracks events only

## How to install

Install via the Claude Code plugin system, or drop the contents of this repo into your project's `.claude/skills/adapty-sdk-integration/` directory.

The skill requires the [Adapty CLI](https://github.com/adaptyteam/adapty-cli) (`npx adapty@latest`) to be runnable — no pre-installation needed.

## Repository structure

```
SKILL.md                        # The skill itself — instructions for the Claude agent
references/
  ios.md                        # Platform-specific doc URLs and implementation order
  android.md
  flutter.md
  react-native.md
  unity.md
  kmp.md
  capacitor.md
  testing-setup-ios.md          # Sandbox testing setup guides
  testing-setup-android.md
feedback-endpoint/              # Vercel serverless function that collects anonymous usage feedback
  api/sdk-integration-feedback.js
```

## Feedback

At the end of a successful integration, the skill optionally collects anonymous signals (platform, steps completed, rating) — no code or project details. The `feedback-endpoint/` directory contains the Vercel function that receives this data.

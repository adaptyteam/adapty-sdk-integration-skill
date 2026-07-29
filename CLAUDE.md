# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

The `adapty-sdk-integration` skill: a portable, Claude-style skill that guides agentic CLIs (Claude Code, GitHub Copilot CLI, OpenAI Codex, Gemini CLI) through integrating the Adapty SDK into a mobile app end-to-end — dashboard setup via the Adapty CLI, SDK install, paywall, store configuration. One repo, three distribution channels: a Claude Code plugin (`.claude-plugin/` holds the marketplace + plugin manifests), the skills.sh CLI, and plain directory copy of `skills/adapty-sdk-integration/` into a tool's skills folder. Keep the skill directory self-contained and format-portable — nothing in it may assume Claude Code specifically.

## Layout

- `skills/adapty-sdk-integration/SKILL.md` — the skill entry point. Phase-by-phase flow: state tracking → setup (docs-fetching rules, session marker, feedback consent) → project analysis → three user questions → dashboard setup through the Adapty CLI → staged, per-platform implementation → closing review → feedback delivery. Platform-agnostic on purpose; per-platform details belong in references.
- `skills/adapty-sdk-integration/references/<platform>.md` — one per platform (`ios`, `android`, `flutter`, `react-native`, `unity`, `kmp`, `capacitor`) plus `testing-setup-{ios,android}.md`. Code snippets and the exact docs URLs the agent fetches before writing each piece of code.
- `scripts/` — the two validation lints and their plain-text allowlists (see below).
- `feedback-endpoint/` — a single Vercel serverless function that receives the end-of-run feedback payload and forwards it to Slack + Airtable. Deployed separately (`npx vercel deploy --prod` from inside that directory); its README documents the env vars and the stable production URL that SKILL.md points at. Has its own tests: `node --test test/endpoint.test.js` from inside that directory.
- `context7.json` — Context7 indexing config.

## Validation lints

There is no test suite for the skill itself — the lints are the verification gates. Run them after any edit to SKILL.md or a reference:

```bash
node scripts/lint-symbols.mjs [platform ...]   # default: all platforms
node scripts/lint-links.mjs
```

Exit codes for both: `0` clean (warnings allowed), `1` findings, `2` infrastructure error (docs unreachable — fix the network, not the skill).

- **Symbol lint** — every Adapty-branded symbol used in a reference's code contexts (`Adapty.x` / `adapty.x` / `AdaptyUI().x` member calls, `Adapty*` type names, in fenced blocks and inline backticks) must exist in that platform's official docs. Ground truth is the `<platform>-llms-full.txt` docs aggregate plus pages the reference links; the docs are verified against SDK sources by the docs team's release process, so docs presence transitively means the symbol exists in the SDK. A reference's platform comes from its filename (`testing-setup-*` files are pinned to their platform in the script). Two plain-text escape hatches, editable without touching code:
  - `scripts/app-side-allowlist.txt` — wrapper names the references deliberately tell the *user* to create. They look Adapty-branded but are not SDK symbols; add the name here when a reference introduces a new suggested wrapper.
  - `scripts/undocumented-sdk-symbols.txt` — real SDK symbols deliberately absent from the docs. Each entry pins a source-of-truth code URL and is verified against the SDK source instead, so a rename still turns the lint red. Format: `<reference>: <symbol> <source-url>`.
- **Link lint** — every https URL in the skill must work the way an agent fetches it: `adapty.io/docs` pages are checked via their `.md` variant with query/hash stripped, `*-llms*.txt` aggregates as-is. A docs 404/410 is a hard failure (the skill literally instructs fetching that URL); external links (stores, consoles, GitHub) failing are warnings only, as are docs pages missing from `llms.txt` (they work but agents can't discover them).

CI (`.github/workflows/skill-lints.yml`) runs both lints on PRs and pushes to `main` (red blocks merge) and on a daily cron that catches drift with no skill commit involved — docs renames, SDK releases. A scheduled failure files one deduped `skill-drift` GitHub issue; repeats become comments on it.

## Conventions when editing the skill

- **Docs URLs are load-bearing.** SKILL.md forbids the runtime agent from guessing slugs — it may only open URLs written in the skill or found in a fetched `llms.txt` index. So every docs URL you add must literally exist (the link lint enforces this); never assemble one from a topic and platform name.
- **The session marker matters.** SKILL.md tells the runtime agent to mint a random `sessionToken` and tag every docs fetch with `?ref=skill-<sessionToken>` (a docs-analytics marker, documented in SKILL.md's "Session marker" section). Don't remove, rename, or add a literal example token to that format — hardcoded example tokens get copied verbatim by agents, which corrupts the analytics.
- **Test runs from this repo are not real integrations.** When you run or debug the skill from inside this repo, have it tag docs fetches with `?ref=skill-dev-<sessionToken>` instead (or drop the `ref` on ad-hoc curl spot-checks), so Adapty's docs analytics can tell development traffic from real usage. The lint scripts already strip refs and need no special handling.
- **New wrapper names need the allowlist.** If a reference introduces a new app-side wrapper (service, notifier, context, constant) with an Adapty-ish name, add it to `scripts/app-side-allowlist.txt` in the same change, or the symbol lint turns red.
- **New platform = new reference + docs coverage.** Add `references/<platform>.md` and confirm the docs publish `<platform>-llms-full.txt` — the symbol lint builds its ground-truth corpus from it.
- SKILL.md and the references are agent-facing prose: imperative, unambiguous, no dead weight. Match the existing voice and structure when editing.

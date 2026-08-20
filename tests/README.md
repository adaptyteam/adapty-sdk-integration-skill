# tests/

Not a test suite for the skills — a fixture corpus for `flow-generator` plus the tools that
check it. The skills themselves are prose; testing those means running agents against them
(see `docs/superpowers/plans/` for that design, which is local-only).

## The corpus

`fixtures/` holds four sanitized flow configs, tracked. The raw exports stay gitignored in
`fixtures-raw/` because they carry real product UUIDs and real `public-media.adapty.io` URLs.

| Fixture | What it exercises |
| :--- | :--- |
| `onboarding-quiz-paywall.json` | 5 screens, branching, a component, cross-screen variables, 42 localizable fields |
| `comparison-paywall.json` | comparison table, custom typography preset, one product |
| `vpn-timer-draft.json` | countdown timer, four uploaded custom fonts, no products |
| `tabs-paywall.json` | the five-element tabs composite, three `const` product purchases — **confirmed to render** |

`tabs-paywall.json` is the one with unusual standing: it is the artifact that resolved the tabs
crash, so it is evidence rather than just coverage. Sanitizing it does **not** change its render
(verified), because remapped product UUIDs only reach purchase payloads, not layout.

## The tools

```bash
python3 tests/sanitize-fixture.py fixtures-raw/x.json fixtures/x.json   # regenerate a fixture
python3 tests/verify-fixture.py tests/fixtures/*.json                   # structural checks
python3 tests/render-check.py                                           # does it draw?
python3 tests/render-check.py --baseline                                # record references
python3 tests/render-check.py --keep                                    # keep PNGs to look at
```

Exit codes match the repo's lint convention: `0` clean, `1` findings, `2` infrastructure
problem (CLI or Chrome missing — fix the tooling, not the fixture).

`render-check.py` needs `adapty@beta` (for `flows config preview`, which is local-only and needs
no auth) and Chrome or Chromium.

### Which tool catches what

Measured 2026-08-20 by injecting the two defects from `flow-schema.md` trap 10 into
`tabs-paywall.json`, the config confirmed to render:

| Defect | `verify-fixture` | `render-check` blank test | `render-check` baseline diff |
| :--- | :--- | :--- | :--- |
| 108 elements missing `states` | **caught** | passed | caught — 1.2% |
| group typed `tabs` not `single_choice` | **caught** | passed | caught — 1.2% |
| every screen emptied | caught | **caught** | — |

Two things follow, and both are easy to get backwards:

**The structural checks are the trap-10 defense, not the render.** Both broken configs draw
pixels; they just lose a selected-tab highlight. "Did anything render" is blind to that.

**The baseline diff works but is not portable.** The control — an unmodified config against its
own baseline — is 0.00%, so there is no false-positive floor to tune around, which is what makes
1.2% a signal. But font rasterization differs across machines, so a macOS baseline will not match
one taken in Linux CI. `render-baseline/` is gitignored deliberately: it is a local gate for
"I changed a skeleton, did the render move?", and calling it a CI gate would be false.

**And a preview is not the builder.** The preview page and the Flow Builder's editor are
different renderers. Both configs that broke the builder render fine here, so a clean render
means "this looked right at this size", never "the flow opens".

## `schema-check.py` — validating against the official schema

```bash
python3 tests/schema-check.py tests/fixtures/*.json      # summary per file
python3 tests/schema-check.py --verbose config.json      # every error
```

Validates a config against `skills/flow-generator/references/flow.schema.json` (the official
draft-2020-12 snapshot). Needs `jsonschema`. **It is the weakest of the gates** — read the trust
order in `flow-schema.md` first. The snapshot is schemaVersion **10** and most live flows are **9**,
so a v9 config will report shape errors that are not defects; never "fix" a v9 flow to satisfy it.

It suppresses one class of error by design. Expression nodes (`JSONVariable` / `JSONConstant`) are
declared as a `oneOf` over two **identical** permissive branches, commented *"shape intentionally
opaque, validated by the transformer"* — so every value matches both and `oneOf` always fails. That
fires on every `purchase` payload and every conditional predicate, including in real builder
exports, so it is a schema artifact rather than a finding. The count is still reported.

What it is genuinely good for: typo-class errors in something you authored — a misspelled element
`type`, a non-existent enum value, a prop borrowed from a different element.

## `preserve-builder-state.py` — do not clobber the builder's own work

```bash
adapty flows config get --app $APP $FLOW --json > live.json
python3 tests/preserve-builder-state.py live.json regenerated.json
```

`config update` replaces the whole config. A script that rebuilds a config from source emits
`_meta.screens: {}`, which silently destroys product attachments made in the Flow Builder — and
`flowProductId` cannot be recomputed, so the next publish 422s and the user redoes the pass.

Run this between building and writing whenever the config was *regenerated* rather than *patched*.
It carries `_meta.screens` per surviving screen id (and uploaded `_meta.fonts` if the new config has
none), and reports what it carried, what was already authored, and what it dropped because the screen
no longer exists — the last one being legitimate but worth seeing.


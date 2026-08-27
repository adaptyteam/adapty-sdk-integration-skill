# Flow snippets — reusing a piece of one flow inside another

Save a piece of a flow to a local file, then graft it into another flow — the same app or a
different one. `references/snippet.py` does both halves; this file is the prose that goes with
it. Ships alongside `verify-config.py` and `diff-config.py`: stdlib only, fully offline. Live
dashboard data reaches it as a `--catalog` file you fetched, never as a call from inside the
script.

## When this applies

The user wants a piece of one flow to show up in another — a plan card, a whole screen, a
`pb_*` component, or a design system with no elements at all (colours, typography, fonts,
icons). That is what this file covers.

Out of scope: anything the four existing transforms already do. Adding a locale, rewriting
copy, adding/removing/reordering screens within one flow, and branching are `flow-generator`'s
own phase spine — reach for those directly rather than routing a same-flow edit through a
snippet.

## Where snippets live

Don't compute the path by hand. Run:

```bash
python3 references/snippet.py where
```

It prints the absolute path on one line and whether the folder already exists on the next
(`existing`, or `proposed — ask before writing`).

The rule it applies: an `adapty-flow-snippets/` directory already at the repo root wins; failing
that, one already in `$HOME` wins. Use it and say which. Otherwise the proposed path is
`<repo-root>/adapty-flow-snippets/` (or `~/adapty-flow-snippets/` with no git repo above the
working directory), and you **ask once** before writing into it — offer to put it somewhere
else. Visible, not a dotfolder.

Always show the absolute path in what you print. A user who has to email the file to a
colleague needs to know exactly which one, not a path relative to wherever you happened to be
running.

Never touch `.gitignore`. A snippet saved under a repo's `adapty-flow-snippets/` is visible to
`git status` like any other new file — that is how a team shares one. Whether to commit it is
the user's call; say so, don't decide it for them.

## Saving

One `extract` call per kind, target selection matching the kind:

```bash
# an element and its descendants
python3 references/snippet.py extract --config flow.json --element el_X@scr_Y \
  --name "Annual plan card" --scope same-app \
  --out adapty-flow-snippets/annual-plan-card.flow-snippet.json

# a whole screen
python3 references/snippet.py extract --config flow.json --screen scr_Y \
  --name "Quiz screen" --out adapty-flow-snippets/quiz-screen.flow-snippet.json

# a reusable pb_* component
python3 references/snippet.py extract --config flow.json --component pb_XXXXXXXX \
  --name "Header block" --out adapty-flow-snippets/header-block.flow-snippet.json

# the design system alone, no elements
python3 references/snippet.py extract --config flow.json --theme \
  --name "Finance design tokens" \
  --out adapty-flow-snippets/finance-design-tokens.flow-snippet.json
```

`--config` takes a live flow's `config get` output or a local file — the same two sources phase
2 already reads from. `--element` takes `<elementId>@<screenId>`; `--screen` and `--component`
take a bare id; `--theme` takes no target at all. Resolve the id by reading the config — an
agent inference here is silent and wrong the same way a wrong subtree ever is: the file still
saves, the graft still succeeds, and the wrong thing lands. Confirm what you are about to save
with the user before writing it, the same way you'd confirm any other target.

**The one question, asked once**: *"reuse inside this app, or anywhere?"* — `--scope same-app`
(default) or `--scope any-app`, recorded as `intendedScope`. It only sets `graft`'s default
behaviour later; every product UUID, variable reference and media URL is preserved verbatim in
the file regardless of the answer. **The file is lossless either way, so a wrong answer costs
nothing** — do not turn this into a longer interrogation.

Pass `--catalog <file>` (your own `adapty products list --json` output) when the snippet binds
a product, so the store ids ride along:

```bash
python3 references/snippet.py extract --config flow.json --element el_X@scr_Y \
  --name "Annual plan card" --scope any-app --catalog products.json \
  --out adapty-flow-snippets/annual-plan-card.flow-snippet.json
```

Without `--catalog` the snippet still saves — it just carries bare product UUIDs, and `extract`
prints a line saying so. Those store ids are what make a cross-app rebind proposable at all
(see **Grafting** below); nothing else in the file can substitute for them.

`extract` exits **0** clean, **1** when it has something to tell you (a product with no store id
recorded, a consumed variable with no producer inside the fragment, an image element with an
empty `values` map), **2** on a bad path or unreadable input. Exit 1 here is the same disclosure
convention as everywhere else in this skill — see **Grafting**.

## The format

One self-contained `<slug>.flow-snippet.json`, kebab-case. Four kinds, one payload shape each:

| Kind | Payload |
| :--- | :--- |
| `element` | the subtree's own slice of the screen's `elements.map`, plus its `hierarchy` node |
| `screen` | the full screen object — `elements`, `selectableGroups`, `caption`, everything |
| `component` | one entry from top-level `components` |
| `theme` | `null` — no elements, just the design-system definitions below |

Alongside the payload, every snippet carries a `dependencies` block: everything the fragment
references but does not itself define — colours, typography presets, fonts, icons, custom
variables, media URLs, products, consumed/produced variable names, groups, navigate targets,
locales. Which of those can travel inside the file and which can only be a pointer is
[`flow-schema.md`](flow-schema.md#invariants)'s own invariant table — colours and presets
(invariant 8), fonts (invariant 9), icons (invariant 10), price and group variables (invariants
5 and 12), navigate targets (invariant 3), locale parity (invariant 11). Read the dependency
split there rather than here; this file only says what `snippet.py` does with each kind.

`inspect` prints a one-screen summary of a saved file — kind, scope, source app, dependency
counts. `list --dir <folder>` enumerates every `*.flow-snippet.json` in a folder with its kind
and name.

## Grafting

`plan` and `graft` take **identical flags** — committing means changing the word:

```bash
python3 references/snippet.py plan  --config dest.json --snippet s.flow-snippet.json \
  --screen scr_dest [--parent el_P] [--index N] [--catalog dest-products.json]
python3 references/snippet.py graft --config dest.json --snippet s.flow-snippet.json \
  --screen scr_dest [--parent el_P] [--index N] [--catalog dest-products.json] \
  --out grafted.json
```

**Run `plan` first, always, and read it before ever running `graft`.** `plan` mutates nothing —
it resolves every dependency against the destination and prints what would happen, and it fails
exactly the way `graft` does — same message, same exit code — whenever `--screen` cannot be
resolved. `graft` runs the identical resolution and writes the result to `--out`.

`--screen` names the destination screen an `element` snippet attaches to, and is **required for
`element` alone**. `--parent` and `--index` place it under a specific parent and position within
that screen (default: appended to the screen root). A `screen` snippet takes no `--screen` — it
is inserted into `screens[]` directly, at `--index` (default: appended last). A `component`
snippet takes no `--screen` either — it lands in top-level `components`, which isn't
screen-scoped. A `theme` snippet takes neither: it changes `theme`/`_meta`/`variables` alone.

Every definable dependency (colour, typography preset, font, icon, custom variable — see **The
format**) resolves one of three ways:

| Destination | Action | Reported |
| :--- | :--- | :--- |
| has the id, same definition | reuse | no |
| has the id, a different definition | adopt the destination's | yes, both values shown |
| lacks the id entirely | carry the snippet's definition in | yes |

Adoption is the default on a same-id collision, not a fork — a card grafted into another app
should look like *that* app's `primary`, not grow a second `primary-snippet-2` on every graft.
It is visible in the plan before anything is written, so a user who wants exact fidelity instead
can say so.

Two facts the implementation turned up, and neither is written anywhere else:

- **A carried typography preset drags its font with it** — the second reference path of
  [invariant 9](flow-schema.md#invariants). A preset that gets **carried** (the destination never
  heard of it) pulls its font along; a preset that gets **adopted** needs nothing, because it now
  resolves against the destination's own fonts. `comparison-paywall.json` is the fixture where
  this matters: all three of its declared fonts are reachable only through theme presets, never
  through an element directly.
- **Adoption rewrites nothing in the payload.** The snippet's elements go on saying
  `colorId: "accent"` or `font.preset: "h1"` exactly as extracted; only the *destination's*
  theme changes definition. There is no id to chase through the grafted elements after an
  adopt — the id was never the thing that moved.

Identity dependencies (a pointer into an account or another screen — products, navigate
targets, variable producers) resolve against `--catalog`/`intendedScope` and are reported the
same way. Anything unresolved lands in `NEEDS YOU`, one line per thing, `!` for a publish
blocker or a renders-empty risk, `?` for something milder (a placeholder asset). Ids that would
collide with the destination are re-minted and every internal reference is rewritten with them —
`WILL RENAME` lines show old → new.

**Media and font URLs travel unchanged across a cross-app graft — measured 2026-08-27,
`adapty` 0.8.1.** A `flows media upload` CDN URL and a `_meta.fonts[].url` are not
app-scoped: a probe image uploaded to `app_finance` loaded (`200 image/png`) and drew
visibly inside a different app's flow with no re-upload, and a font entry lifted
verbatim from one app's flow rendered in that face inside another app's flow preview.
Neither needs a rewrite step. That preview result is not a device guarantee for the
font (`flow-schema.md` trap 7 — a resolvable reference is not proof the font ships), so
still name it as unconfirmed-on-device when a font-carrying snippet is grafted. The
`fill` object-versus-array question was only tested for a single-layer `color` fill in
either shape — the split does not track `schemaVersion` cleanly (the tracked fixture
corpus includes a real `schemaVersion: 9` export with array-form fills), so read a fill's own
shape rather than inferring it from version. Leaving that shape unconverted validated
and rendered identically either way — `snippet.py` does no fill conversion today and
this one case doesn't require it. That does **not** extend to multi-layer, image or
gradient fills — see the design spec's Risks section for the full evidence and what
remains open.

`plan`/`graft` exit **0** clean, **1** when `NEEDS YOU` has at least one line, **2** on usage or
an unreadable input (a bad snippet, a `--screen` that doesn't exist — `plan` and `graft` both
refuse it, identically). **Exit 1 is a
disclosure obligation, not a defect** — it means "there is something you must know before this
ships", not "something went wrong". The file writes regardless. Treat it exactly like
`diff-config.py`'s exit 1 ([merge.md](merge.md)): a check whose red means *"you did something
wrong"* gets argued with.

**The guarantee `graft` actually gives you**: the output is `verify-config.py`-clean, **or**
every remaining ERROR corresponds to something the plan already put in `NEEDS YOU`. The graft
introduces no *undisclosed* breakage — that is not the same claim as "the output always passes".
Measured: grafting a screen whose `navigate` targets a screen the destination lacks reports that
target in `NEEDS YOU` and leaves it dangling on purpose, because inventing a destination changes
routing nothing asked to change. Run `verify-config.py` on the graft output the same way phase 3
always does, expect it to agree with what the plan told you, and never report a graft as clean
without having read both.

## What cannot be reused

- **`flowProductId`.** Builder-minted and screen-scoped — [`products.md`](products.md) owns why.
  A grafted `product` element arrives on its new screen unattached
  ([invariant 4](flow-schema.md#invariants)); the graft cannot fix that, and the user resolves it
  in the Flow Builder. It is named in `NEEDS YOU` and warned on by `verify-config.py` too.
- **A stranded variable's producer.** If the destination has no `text-input`, group, or product
  to supply what the fragment consumes, the reference breaks silently — the
  [invariant 12](flow-schema.md#invariants) consequence, and just as invisible to `config preview`
  ([preview.md](preview.md#what-a-render-cannot-show-you)). `NEEDS YOU` is the only place this
  becomes visible before a device does.
- **`raw` SVG that was never there.** An icon the source snippet didn't carry a real `raw`
  markup for cannot be synthesized here any more than anywhere else in this skill
  ([`flow-schema.md` invariant 10](flow-schema.md#invariants)).
- **Locale correctness.** `config preview` draws one locale and is byte-identical whichever one
  you force ([`preview.md`](preview.md#what-a-render-cannot-show-you)) — so a graft's locale
  handling (drop what the destination doesn't declare, fill what it does from the snippet's
  default, report both) is **invisible to every visual check**. Read the plan's `WILL FILL` /
  `WILL DROP` lines; do not look at the screenshot for this.

## After a graft

A graft output is a working file like any other phase-2 output — hand it straight to
[`SKILL.md`'s phase 3](../SKILL.md#3-check-the-shape-then-clear-the-publish-gate) onward:
`verify-config.py`, `flows config validate`, preview and iterate, then the phase-5 approval gate
before any write. Nothing about the gates changes because the file came from a snippet instead
of a hand transform.

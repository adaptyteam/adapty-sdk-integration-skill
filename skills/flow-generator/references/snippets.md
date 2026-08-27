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
a product, so the store ids ride along. `products list` paginates like `flows list` — defaults
to `--page-size 20`, caps at 100 — so build the catalog with `--page-size 100` and walk `--page`
if a full page comes back. A truncated catalog does not error: a product past the cutoff simply
has no match, and `NEEDS YOU` reports its binding as stripped as if the product didn't exist in
the destination app:

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

**When the destination sells something different from the source, the imported copy is wrong even
though every gate passes.** This is from a real failure: a three-step "how it works" timeline
grafted from a personal-finance paywall into an AI language-learning one. `verify-config.py`
passed (every reference resolves), `validate` passed (the document publishes), the render was
legible — and the shipped screen told someone learning French to *"Link your accounts once —
balances keep themselves up to date."* None of those checks knows what the product **is**; each
checks that a reference resolves, that the document publishes, that pixels are legible, never
whether the sentence is true of this app. `plan`'s **WILL SAY** section is the moment this becomes
checkable — it prints the actual copy the graft is importing, in hierarchy order, under the
destination screen's own name. Read it against the destination screen and rewrite whatever
doesn't belong, or say plainly that you did not.

**A carried colour brings the source's background assumption with it — an adopted one cannot,
because the destination already has an opinion about that id.** This is from a real failure: a
timeline grafted from a light-background flow into a dark one. `muted` existed in both flows and
was adopted — fine, since it now resolves against the destination's own definition. `ink`
(`#0C1116`) did not exist in the destination, so it was carried in verbatim, and the destination
screen's background is `#080D1C` — step titles rendered near-black on near-black. `verify-config.py`
passed (the reference resolves), the schema passed, and only the render showed it. `plan` now
checks every **carried** colour actually referenced by an element in the payload against the
destination screen's own background (a `color` fill via `colorId` or a literal hex, or a
`gradient`'s first stop — an image fill, or no fill at all, is skipped silently rather than
guessed at) and flags a WCAG contrast ratio below 3.0 as a `?`-level `NEEDS YOU` line naming both
hex values. It never fires on a reused or adopted colour — those can't have this problem, the
destination already defines them — and it never repoints the colour itself; that is a design
decision for the user. Calibrated against the tracked fixture corpus: silent across 108 same-app
element grafts (the realistic in-flow case, where every carried colour is by definition never
carried at all — same theme, same definition, always reused).

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

**The plan header states the insertion point precisely, and `graft` confirms it landed there.**
`placement: {screen, parent, index}` alone told you the coordinates, not what they meant — an
`element` snippet's header now reads *"appended as the last child of `root`"* or *"at index 3
under `el_card`, after `el_title`"*, derived from the destination's own hierarchy: the sibling
that will precede the new node, or the one it displaces when inserted at index 0. A `screen`
snippet's header says where in `screens[]` it lands and which screen it follows. A `theme`
snippet has no placement and the header says nothing rather than inventing one — same for
`component`, which lands in top-level `components`, not on any one screen. After `graft` writes,
an `APPLIED` line reports what actually landed, using the same placement text: element count (or
the screen/component id), the destination, and the resolved position — the line a user reads to
confirm the write did what the plan promised, not merely that it exited 0.

## Grafting into multiple flows

A request like *"add timeline-products.json to flows A and B"* names **flows, not screens**. The
CLI stays one flow per call — there is no multi-target flag, and adding one would hide exactly
the differences that matter. The contract:

1. **Resolve each named flow to its id, and show the resolution.** A user who says "flows A and
   B" must see which flows you matched before anything else happens — never graft against a
   guess. `flows list` paginates and defaults to `--page-size 20`; **always pass
   `--page-size 100`** (the documented max) when resolving a flow by name, and if a full page of
   100 comes back, walk `--page` until a short page does — a count equal to the page size is a
   signal more remain, not a total. **Never report "no such flow" from a single unpaginated
   call**: a negative result is only trustworthy after the full list has been walked — a
   confident wrong negative sends the user to check their own dashboard, which is worse than
   saying "I looked at 20 of N".
2. **Run `plan` for each flow separately, and show all plans together.** Per-flow differences —
   a different theme so one adopts and the other carries, a collision in one flow and not the
   other, a product declared in one and not the other — are the whole point of running it more
   than once. A merged plan would hide exactly those differences; run and read every one.
3. **Take one approval covering the set,** naming every flow, once every plan is in front of the
   user.
4. **Graft each, then report a per-flow table**: flow, destination screen, what landed
   (`APPLIED`'s own line), exit code. One row per flow, not one paragraph.

**Resolving the destination screen is the agent's job, per flow, and it is never a guess.** The
request named flows, not screens, so each flow's own screen has to be picked and the choice
stated — say which screen and why (the flow's only screen; the screen the user pointed at; the
screen matching the source's own role). A single-screen flow is unambiguous. A multi-screen flow
usually is not — ask rather than pick silently, the same rule as everywhere else a target has to
be resolved before a write.

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

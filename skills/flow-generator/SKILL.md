---
name: flow-generator
description: Use when a user wants to change an Adapty flow by editing its builder config JSON — add a locale, translate a paywall or onboarding, rewrite copy, add/remove/reorder screens, add tabs or plan pickers, or wire quiz branching. Triggers on "edit my flow config", "add a language to my paywall", "translate my onboarding", "remove a screen from the flow", "add tabs to my paywall", "build me a paywall like this", or a supplied Adapty flow config.
---

# Flow generator

Read an Adapty flow's builder config, transform it, check the result, and write it back.
Transforming a config that exists is the default, and the safer path: everything you emit is then
grounded in a document that already works.

**Authoring a new flow is also in scope**, and three things — and only these three — genuinely
cannot be synthesized:

- **`flowProductId`**, the per-screen product declaration in `_meta.screens[].products[]`. Only the
  Flow Builder writes it, and it is not a UUIDv5 over anything the config contains (2,944
  combinations over 4 triples with full provenance). But you do not need the real value: the
  transform service only checks that a declaration is **present and consistent**, so **write a
  provisional one and a brand-new draft previews on a device straight away** — measured, with no
  publish and no builder visit. Use `flowkit.predeclare(screen_id, product_ids)`. Omit it and
  device preview returns 422 (`missing_flow_product_id`, `unknown_product_id`) until the builder
  saves the flow. When *rewriting* a flow, never generate one — carry the live `_meta.screens`
  forward. See [products.md](references/products.md).
- **Uploaded assets.** An image you do not have is an empty values map, never a made-up URL
  (trap 5).
- **Real store prices.** They come from the store, not from Adapty; `products create` has no price
  flag.

Everything else is reachable: product UUIDs from `adapty products list` (or `products create`),
`theme` colours sampled off a reference screenshot, and icon SVG authored and then render-verified.
When you do author, [`references/flowkit.py`](references/flowkit.py) owns the mechanical parts —
the `hierarchy`/`map` split above all — and [patterns.md](references/patterns.md) owns the shapes.

## What you print

The user reads your messages, not this file. Keep them short.

**Two fixed blocks, and nothing else is fixed:** the approval ask before a write, and the closing
callout after one. Both are in phase 5; fill their slots and do not pad them.

**Everything else is one line or omitted** — what changed, what still needs them (products to
attach, assets to upload), any decision where two answers were defensible, and what your checks
did and did not cover. **Say each thing once**: if the approval ask already named it, the closing
note does not repeat it.

Do not narrate phases, restate the config back, list warnings you did not act on, or explain the
CLI to someone who asked for a paywall.

## The CLI surface

```
$ADAPTY auth login                                             # browser flow
$ADAPTY auth whoami                                            # verifies the token server-side
$ADAPTY apps list --json                                       # to get <APP_UUID>

$ADAPTY flows list   --app <APP_UUID> [--page N] [--page-size N]    # page-size max 100
$ADAPTY flows create --app <APP_UUID> --name <name>            # row only; always `draft`
$ADAPTY flows get    <FLOW_ID> --app <APP_UUID>
$ADAPTY flows config get      <FLOW_ID> --app <APP_UUID> --json     # 404 until first write
$ADAPTY flows config validate <FLOW_ID> --app <APP_UUID> (--config-file <f|-> | --config <json>) --json
$ADAPTY flows config preview  <CONFIG_FILE> [--screen <id>] [--device <id>] [--orientation …]
$ADAPTY flows config update   <FLOW_ID> --app <APP_UUID> \
    (--config-file <file|-> | --config <json-string>) \
    [--expected-updated-at <int>] [--remote-configs <json>]
$ADAPTY flows media upload    <IMAGE_FILE> --app <APP_UUID>   # DO NOT CALL — endpoint not live
```

**Resolve `$ADAPTY` once, here, and use it for every command.** A global `adapty` is frequently old
— measured at `0.3.0` on a real machine, which has no `flows` topic — and three agents read that as
"validate and preview do not exist" and skipped phases 3 and 4:

```bash
adapty --version                      # >= 0.8.0 ?  ADAPTY="adapty"
ADAPTY="npx --yes adapty@latest"      # otherwise, and always pass --yes
```

`--yes` is not optional: without it `npx` stops to ask permission to install. Declare a command
unavailable only after `npx --yes adapty@latest` *and* `npx --yes adapty@beta` both lack it — never
from a version number you read somewhere.

**In `zsh` — the macOS default — a multi-word `$ADAPTY` is not split into words**, so every command
below fails with `command not found: npx --yes adapty@latest`. Run `setopt shwordsplit` once in the
same shell (verified), or call `npx --yes adapty@latest` in full. That error is a shell problem,
never evidence the command or the CLI is missing.

**One command is not usable, whatever the CLI offers.** `flows media upload` reaches its endpoint
and gets `http_404` in production: **do not call it and do not offer it** — an image you do not
have stays an empty values map (trap 5) and the user uploads it in the Flow Builder.

**There is no `flows publish` and no `flows delete`.** Both are dashboard actions. Never write a
command name the CLI does not have, and never invent a flag — `config validate` takes only `--app`,
`--config`/`--config-file` and `--json`.

Four facts about the config commands that are not guessable:

- **`config get` returns an envelope, not the config**: `{config, remote_configs, status,
  updated_at}`. The document you transform is the `config` field, and both `update` and
  `validate` take that field alone. Handing `validate` the envelope returns
  `Invalid flow input` — which reads exactly like a broken config and is not one. (`preview`
  is the odd one out: it accepts either.)
- **`status` is not yours to write.** It belongs to the envelope and is **discarded** if you put
  it inside `config`. Do not emit it in a config you send to `update`, and do not treat its
  absence as a defect. (A *browser export* does carry `status` and `id` at the top level — that
  is a different document shape, and phase 5 covers what to do when the user wants a file.)
- **`updated_at` is an epoch integer** (e.g. `1787210847609`) and it is the optimistic lock.
  `flows create` prints an **ISO** timestamp instead, which `--expected-updated-at` rejects — so
  always take the integer from `config get`.
- **`config update` has no dry run.** `validate` and `preview` are the pre-flight checks, and
  both run *before* a write — see phase 5 on why that ordering matters.
## The five phases

### 1. Resolve the invocation, then authenticate

**First** set `$ADAPTY` as [the CLI surface](#the-cli-surface) describes — probe `adapty --version`
and fall back to `npx --yes adapty@latest`. Do it before the first command, not after one fails,
and print the version you resolved in the same command you run next so the two cannot disagree.

Then `$ADAPTY auth whoami`. It hits the server and prints the name and companies, so it proves the
token works. Prefer it to `auth status`, which only reports what is stored locally and does not
verify it — it happily prints `Email: undefined` next to a working token.

If it fails, `$ADAPTY auth login` opens a browser. That is the user's to complete; wait for them
rather than retrying in a loop. Then `$ADAPTY apps list --json` for the `<APP_UUID>` every later
command needs.

### 2. New flow, or existing flow

Decide this explicitly and say which you chose, because the two paths differ in what they can
destroy.

**Existing flow** — the user names it, or `flows list` and confirm the match back to them
before touching it. Then `flows config get`, and **keep the `updated_at`** for the write.

**Take a backup before the first edit.** `config update` replaces the whole config and there is no
undo, so the copy you fetched is the only way back:

```bash
$ADAPTY flows config get --app $APP $FLOW --json > flow.working.json
cp flow.working.json flow.backup.json
```

**New flow** — `flows create`, then seed its config from one the user already has
(`flows list` → `config get`) so theme, fonts, locales and products are real. A brand-new flow
has no config, so its first `config update` omits `--expected-updated-at`.

Building into a *new* flow is the safe default whenever the user asks for something new:
`config update` replaces the whole config, so generating over a flow that already has content
discards that content.

Then, before editing: **report what the source config contains** — screens and captions,
locales, products, the navigation graph. Before proposing anything; it grounds the user and
catches a wrong flow immediately.

**Confirm the transform.** In scope: add a locale, rewrite copy, add/remove/reorder screens,
branching and conditions. A request outside those is named as out of scope, not improvised.

**Were you given a design to follow?** Answer it out loud, because it decides who is choosing the
design. A reference image, an existing screen to copy, or a layout the user spelled out means
*they* chose it: follow the reference, and compare against the file rather than your memory of it
(phase 4). **Follow the reference for visual style, colors, typography, icon style and element
hierarchy, but always preserve Adapty's fluid layout discipline** (`width: fill`,
`height: hug`, `position: relative`). Never hardcode fixed container dimensions or fixed
positioning offsets just to match a screenshot's static pixel measurements — fixed geometry
breaks across devices (ADP-7117). **No reference means you are choosing it** — "build me a
paywall", "add a paywall
screen", "make one that converts" — and the request map only turns their nouns into element types;
it says nothing about what belongs on a screen that sells.

When you are the one choosing, the **`paywall-teardown`** skill is the reference. Invoke it before
you write anything and build from its list: it returns a **composition** for the screen plus the
patterns this vertical needs, in priority order, and it names the values it refuses to invent — a rating, a review count, an outcome
stat, a discount, an uploaded hero. **Put those asks to the user before you write the config**, and
leave the element out rather than filling it with a plausible number. A screen that ships with an
element missing is recoverable; one that ships with a fabricated rating is a lie in front of real
buyers. Build the composition it names — **do not substitute a shape you built last time.** Two
paywalls in a row came out of this pairing as the same comparison-table-over-plan-cards screen in
two unrelated verticals, from a build script copied forward rather than a decision. That skill also
evaluates and corrects the result — see phase 4, where the correction is still free. And reach for it when the user wants to know how good a flow is rather than to change
it: that answer is a teardown, not a transform.

**Products are the user's to pick — catalog first, store ids second, create last.** For any
screen that sells, resolve the products **before the design**, in this order, and never skip a
step silently:

1. `$ADAPTY products list` and show what exists — title, period, store bindings — and ask which
   of these belong on the screen. Most accounts already have the right products.
2. Only if nothing fits: ask for their **store product ids** (App Store product id; Google
   product id **plus base plan id** for subscriptions) — those are the bindings `products create`
   cannot run without, so asking later just stalls the create.
3. Only then `products create`, behind its own confirmation gate
   ([products.md → Creating a product](references/products.md)).

Before the design because the catalog *gates* the design: a trial-timeline archetype needs a
verified offer, a period switcher needs plans differing only by period, and a price variable needs
a product whose period matches its field. Picking a product yourself from the list is not a
shortcut — it decides what the user sells, and it is the one choice on the screen they cannot see
in a screenshot.

**Resolve the request into schema terms.** The user's noun is rarely the element `type` — there
is no `button` and no `toggle` element, and tabs are a five-element composite. Use the request
map in [flow-schema.md → Vocabulary](references/flow-schema.md), and source any shape the config
does not already contain via
[patterns.md → Where to source a pattern, in order](references/patterns.md).

**Apply**, preserving every key you did not deliberately change — including unrecognized ones.
**Nested** unknown keys survive a round trip; unknown keys at the **top level of `config`** are
discarded, so never park anything there.

Write the result to a local file. Phases 3 and 4 both work on that file, with nothing saved yet —
**and they apply whether the deliverable is a flow write or the file itself.** "No CLI write
happened" exempts you from the approval gate, never from the phases.

**If the file IS the deliverable, its contract applies the moment you write it, here.** A source
export carries top-level `status` and `id`; **never emit `"status": "published"`** — it imports as
live-looking content — and the `id` names the flow the export came *from*. Drop them or downgrade
`status`, **say which you chose**, and say the import must be pointed at the flow the user means.
`tests/verify-fixture.py` warns on both fields; that warning in your own check output is this rule
firing — act on it, never paste it through.

### 3. Check the shape, then clear the publish gate

Walk [Verify](#verify) first — it is local and free and it finds every defect at once, which the
commands below do not. Then two checks, in this order:

```bash
npx --yes --package=ajv@8 node references/validate-with-schema.mjs \
  --config flow.working.json --baseline flow.backup.json          # are the props well-formed?

$ADAPTY flows config validate <FLOW_ID> --app <APP_UUID> \
  --config-file flow.working.json --json                          # is it publishable?
```

**Always pass `--baseline`** — the pristine copy from step 2. The schema tracks the newest
`schemaVersion` while most live flows are older, so an unbaselined run on a v9 flow reports
hundreds of pre-existing mismatches, none of them yours. Details in
[flow-schema.md → the two different validators](references/flow-schema.md).

`validate` runs the **same transform service that gates publishing**, so it is the only pre-write
check here that speaks for the publish gate. It saves nothing, needs no confirmation and needs no
baseline — a v9 config validates clean. It takes the **bare `config`**, not the envelope, and the
flow must already exist, so on new work it runs after `flows create`.

**Read the verdict, not the exit code.** Exit 1 means "not publishable" *or* "the call failed", and
only `--json` separates them: a `valid` field versus an `error` object. An agent gating on the exit
code reports a good config as broken and a dead call as a defect.

> **Done here is a run that printed `valid: true` over the exact bytes you are about to write.**
> It reports one fatal per run, so fix, re-run, repeat — a shorter list is not progress.

**Neither check is a proof, and they do not overlap.** `validate` catches the stranded references
the schema cannot see — an undeclared product, a `groupId` or a `navigate` pointing at something
that is gone. It also passes `fill: "banana"`, `schemaVersion: 999`, an element with no `states`,
and every property the service will silently drop on the device. The schema check answers the
opposite question and knows nothing about publishability. Coverage both ways, and how to read each
message family: [validate.md](references/validate.md).

### 4. Preview, and iterate until it looks right

```bash
# no --json (it prints an object, not the URL); never print the URL itself — it is ~6K chars
URL="$($ADAPTY flows config preview draft.json)"  # local: no --app, no auth, no save — file-only tasks included
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --disable-gpu \
  --hide-scrollbars --window-size=430,932 --virtual-time-budget=12000 \
  --screenshot=shot.png "$URL"
```

**Open `shot.png` and look at it**, against what the user asked for and — if they gave one — against
the reference image file, re-opened, not remembered. `--screen <id>` steps through the rest.
Measure rather than eyeball with `tests/render-measure.py`. Always try the preview: never decide
from the config's size.

**A reference image raises the bar from "matches the request" to "matches the reference" — run the
fidelity pass before anything is written, every time one was given.** "Nothing jumped out" is not a
result: a side-by-side look passes screens the user rejects on sight, because "close" is a claim
about structure and fidelity lives in everything else. The pass produces a written difference list,
element by element:

1. **Inventory the reference:** per-element colors, typeface feel, icon style, photos and
   backgrounds (gradient, glow), and the proportions between blocks. For each item, record what
   your render has — match, gap, or unreachable.
2. **Close every gap the format can reach:** sample colors from the image instead of naming them
   from memory; match sizes and spacing to the reference's proportions using relative layout
   discipline (`fill`/`hug`/`relative`) — never hardcode fixed container widths or heights to
   match image pixels; author monochrome SVG
   icons (render-verified — [patterns.md](references/patterns.md)) where the reference uses
   designed glyphs, and where you cannot draw one faithfully ship a **styled empty placeholder**,
   never an emoji — a placeholder asks to be filled, an emoji looks finished and ships a
   different design ([trap 5](references/flow-schema.md)); rebuild gradients and glows rather
   than flattening them. **Reach for the layout props before padding or docking** —
   `distribution` has four modes, and `space-between` on the screen root is what puts a footer at
   the bottom ([trap 10b](references/flow-schema.md)). A screen assembled from gaps plus reserved
   padding is the shape that reads as "broken everywhere": a dead void under the content on a
   tall device, or a footer sitting on top of it.
3. **Turn what the format cannot reach into named user asks** — uploaded assets, account fonts
   (both are manual Flow Builder uploads; no CLI path) — in the handoff, never silent
   downgrades. **Ship every asset placeholder fully styled** — `borderRadius`, `objectFit`,
   fixed size, on the `image` element itself — so the upload lands styled instead of handing
   the user styling work ([flow-schema.md → trap 5](references/flow-schema.md)).
4. **Re-render and walk the pair again.** Done means every remaining difference is on the ask
   list — a user declining previews waives the deliverable, not this pass.

**What it cannot tell you**, each measured: a stranded variable, a `states[].condition`
(unlike a `visibility` one, which *is* evaluated), selection in any non-product group, any locale
but the one it draws, anything resolving at runtime, an element it draws that a device will not,
and **the device's own frame** — it draws no notch and no home indicator, and no `--device` id it
knows is a short phone, so author `safeArea: true` and hand short-device clipping over as a device
check. Full statements in
[preview.md → What a render cannot show you](references/preview.md#what-a-render-cannot-show-you)
— read them before you report what a screenshot proves.

**Confirm you screenshotted the flow at all.** A bad `--device`, a broken fragment and a wrong host
all render as *pages* that pass a "did anything draw" check. If the render is blank, slow or wrong,
switch to [`preview-with-playwright.mjs`](references/preview-with-playwright.mjs), which uses the
page's file input instead of the URL — do not shrink the config. If you cannot render at all, say
so and ask the user to look; never report the work finished on a clean validate.

**A missing element may not be your bug, and a clean preview is not the builder opening the flow.**
Both, with the four surfaces and what each one proves:
[preview.md](references/preview.md).

**A render that matches the request can still be a weak paywall.** Every check above asks whether
you built what was asked for; none asks whether the screen sells. **If you chose the design — no
reference image, no source screen (phase 2) — running the `paywall-teardown` skill over this PNG is
part of the work, not a courtesy.** Hand it the render *and* the config, since one shows what is
visible and the other what is there, then **apply** what it ranks *Fix first* or *High* and
re-render. Findings on a screen you designed yourself are defects, not suggestions: a screen handed
over with a list of the patterns you skipped is unfinished. This is the cheapest moment for it —
nothing is written yet, so a correction costs a screenshot instead of a `config update`. Skip it
only on an edit the user specified literally: a typo fix, a locale add.

**Iterate here.** Anything off, go back and fix it, then re-run phases 3 and 4. Nothing has
been saved yet, so an iteration costs a screenshot rather than a write.

### 5. Get approval, then deliver — a write or a file

**Whether you need a yes before writing is decided by one observable fact: does the target flow
already have a config?**

**It does not** — a flow you just created with `flows create`, whose `config get` 404s. Write it.
There is nothing to lose and nothing to overwrite, and stopping to ask would be friction over an
empty document. Report what you wrote afterwards.

**It does** — anything you fetched in phase 2. **Stop and get an explicit yes before the write.**
`config update` replaces the entire config, there is no partial write, no undo and no version
history in this surface, so the document you are about to replace exists in exactly one other
place: the backup you took in phase 2. Put all of this in front of the user in one message and
wait:

**Show them the change first — an approval on a description is not an approval on the screen.**
Split it in two, because the two halves need different things from the reader.

**Screens that changed — one row each, so "there are four of these" is visible at a glance.**
Render every touched screen from the draft, and its `before` from the backup (`preview` takes the
backup envelope as-is, no `jq`). A new screen has no before; say so rather than dropping the row.

> | Screen | What changed | Look at |
> | :-- | :-- | :-- |
> | Paywall *(new)* | outcome rows, two plans, trial badge | `after-scr_paywall.png` — **open in your browser** |
> | Daily goal | nothing visual | `after-scr_commit.png` |

**Changes with nothing to see — list them separately and say why.** A reader who has just looked at
four screenshots will otherwise assume the pictures were the whole change:

> - `scr_commit` CTA: `closeFlow` → `navigate scr_paywall` — an action, not a pixel
> - `_meta.screens`: product declaration added for the two new plan cards
> - 42 localizable fields gained `de` — the render only ever draws one locale

**Open exactly one of them live, and mark which row it is.** You are on their machine, so open it
rather than handing over a command to paste:

```bash
URL="$($ADAPTY flows config preview draft.json --screen <id>)"
open "$URL"          # macOS; xdg-open on Linux, start on Windows
```

The explicit opener is needed because your shell captures stdout, so the CLI prints the URL instead
of launching a browser as it would on a terminal. `preview` is fully local — no auth, no app id, no
write. **Print the command instead only when there is no display** (remote or headless) and say
that is why.

One tab, whatever the size of the change: the page renders a single screen and **does not walk the
flow** — measured, a button carrying `navigate` leaves the page where it was — so N tabs is N times
the noise and still not the flow. Open the screen whose *state* matters most (a picker, a toggle, a
selected plan), because state is the one thing a static PNG cannot show.

**Identical screenshots do not mean an identical config.** Measured: deleting an entire
`bottom-sheet` element produced a **byte-identical** render, because the sheet was hidden in the
state that draws. That is what the second list is for.

> About to overwrite the config of **<flow name>** (`<flow-id>`), currently **<status>**.
>
> <the two lists above>
>
> - Element count: <before> → <after>
> - Restore: `flow.backup.json`, taken before this edit.
>
> Write it?

Do not paraphrase this into "shall I save?" — the flow name, the id, the status and the restore
path are the content, and an approval given without them is not informed. Wait for a yes; a
screenshot the user liked is not one.

**If the flow is `published`, disclose what the save changes — then edit in place on their yes.**
A `published` flow you save becomes `dirty`: the status is visible to their whole team and cannot
be reverted from the CLI, while end users keep seeing the published version until the next
publish. Put that sentence in the approval ask and proceed — editing a live flow is the normal
case, and the preview pair, the backup and the lock exist precisely so it is safe. Suggest a
fresh `flows create` only when the work is exploratory — a redesign the user wants next to the
original — never as the default answer to an edit.

**Restoring from the backup — verified end to end.** Re-read `updated_at` first, because your own
write has just invalidated the one you were holding:

```bash
UA="$($ADAPTY flows config get --app $APP $FLOW --json | jq -r .updated_at)"
jq '.config' flow.backup.json > restore.json
$ADAPTY flows config update $FLOW --app $APP --config-file restore.json --expected-updated-at "$UA"
```

Measured on a real flow: an element deleted and written, then restored this way, came back
**byte-identical** to the backup. So the recovery is real — but it only exists if phase 2 actually
took the backup, which is the reason that step is not optional.

Only then:

```
$ADAPTY flows config update <FLOW_ID> --app <APP_UUID> --config-file draft.json \
    --expected-updated-at <int-from-config-get>
```

Validate and preview both run on a local file, which is why the write comes last: one write when
the thing is right, instead of one per iteration. If you have already written and then found a
problem, that is fine — re-read `updated_at` from `config get` before the next write, because
yours is now stale.

**Read it back — and `update --json` already gave it to you.** The write returns the **same
envelope as `get`**: verified equal key for key, `config` for `config`, same `updated_at` and
`status`. So redirect it over your working file and you are in sync for the next round with no
extra call, and diff *that* against what you sent. A faithful round trip is normal — 108 of 108
elements on a real screen — so a difference is a real finding, and it catches the drop-silently
class: a top-level key that vanished, a `status` you should not have emitted.

```bash
$ADAPTY flows config update $FLOW --app $APP --config-file config.only.json \
    --expected-updated-at "$UA" --json > flow.working.json
```

A write that changes nothing does not bump `updated_at` (measured once), so re-running the same
content is not a fresh lock token. **On a 409** someone edited the flow since you fetched it and
nothing was written: re-`get`, re-apply your change **to their config**, write again. Never force
past it and never re-send your local copy — that is the content that would erase their work. If
their version differs in ways you did not author, ask rather than restore.

**If you rebuilt the config from a script rather than patching the fetched one**, merge the live
`_meta.screens` back in first — `config update` replaces everything, and an empty one wipes product
attachments the builder made ([products.md](references/products.md)).

#### The file deliverable

When the user asked for a file rather than a write, there is no approval gate — the contract lives
in phase 2, **at the moment the file is written**, and your closing report repeats which
`status`/`id` shape you chose. A file handed over without that sentence is undelivered.

**Never end with the work in a local file.** `config update` is the only save this surface has, and
there is no publish command, so saving is as far as you can take it.

**Then end with this callout, every time.** A save is not a release, and the user is the only one
who can finish it. Fill the slots and keep all four lines — the last one is the point:

> **Saved as a draft — your users can't see this yet.**
>
> 1. **Review it:** `https://app.adapty.io/flows/<FLOW_ID>/builder` — refresh the page if you
>    already have it open, the builder does not notice a CLI write.
> 2. **Preview on a real device:** open the flow in the **Adapty mobile app** — the actual SDK
>    renderer. **Check `<the specific things this build could not verify>`.**
> 3. **Publish:** the button at the **top right of the editor**.
>
> Until you publish, everyone continues to see the previous version.

**Fill that slot with the actual list, never with "check it works".** You know which of your choices
the render could not reach — a branch that fires on tap, a toggle, a non-default locale, a progress
bar that advances, glyph metrics that differ on iOS. A generic instruction gets skipped; three named
things get tapped. The one defect that reached a user from this skill was an emoji clipped on iOS in
a build whose every preview was clean, so this slot is where that gap gets handed over deliberately
instead of by luck.

## Safety

**Pass `--expected-updated-at` on every write except the first.** A stale value fails instead of
clobbering, so this is a real guarantee rather than a warning. Read it from `config get`
immediately before you write. Omitting it is last-write-wins and will silently overwrite an edit
someone else made in between.

**Never write to a flow the user did not name.** `flows list` is for finding the right one and
confirming it back to them, not for picking one yourself.

**`config update` replaces the whole config.** There is no partial write, no undo and no version
history. Prefer a fresh `flows create` for new work.

**Overwriting an existing config needs an explicit yes.** Phase 5 owns the form. The gate is keyed
to whether the flow already has a config, not to how confident you feel about the edit — a clean
validate, a good screenshot and a user who liked the design are all upstream of the question and
none of them is an approval.

**Deleting a flow is a dashboard action.** There is no `flows delete`, so never claim to have
removed one — including a throwaway you created yourself. Name the flow and tell the user where
to delete it.

`validate` and `preview` change nothing and cost nothing. Use them freely.

## Verify

Walked in phase 3, **before** the two commands. `validate` calls the same transform service that
gates publishing, so it can confirm several of the rows below — but only one per run, and only
after a round trip. This list finds them all at once, locally, and it covers rows `validate` never
reports. Marked **[V]** below: a row `validate` will catch if you miss it.

**Publishing runs a transform service that refuses configs `config update` accepted** — with an
HTTP 422, a fatal `error`, and an `issues` array whose `severity` separates fatal from advisory.
See
[flow-schema.md → The transform service is the authoritative validator](references/flow-schema.md).
If the user shows you its output, read the `path` fields: they name the offending element, not just
the screen.

Referential — full statements in [flow-schema.md → Invariants](references/flow-schema.md):

- `elements.map` keys equal each element's own `id`
- **[V]** `hierarchy` resolves into `map`; `root` and `{"type": "global"}` component nodes are the only
  hierarchy ids with no `map` entry
- **[V]** every `navigate` `payload.screen` names a screen that still exists, including targets nested
  inside a `conditional`'s `cases` and `default`
- **[V]** every `product` element's `props.product.id` is declared in
  `_meta.screens.<thatScreenId>.products[]` — and so is every product named only by a `const`
  **purchase** action, which has no element of its own ([validate.md](references/validate.md))
- price variables resolve by their own form — a product-relative head is a declared product, a
  group-relative head is a `product`-typed group; **never validate one against the other**
- **[V]** `selectableGroups` and `groupId` agree in both directions
- every `const` compared against `<groupId>.selectedOptionId` matches a member's `customId`,
  and every `const` compared against `<groupId>.selectedProduct` is a product bound on that
  screen
- every variable consumer still has its producer, including across screens
- `colorId` and `font.preset` resolve in *this config's* `theme`; `font.family.id` in `_meta.fonts`
- every icon used appears in `_meta.icons` **with real `raw` SVG** — never fabricate the markup
- **[V]** every locale in `locales[]` has a value in each `_localizable` field you touched — and where
  that value is a `switch`, the **same number of branches** as the default locale, since a
  half-translated conditional looks finished

Well-formedness — cheap, and it is what a crash looks like:

- **every element under a screen's `elements.map` carries `states`** (`[]` is fine). Missing it
  produced a config the API accepted and the builder could not open — and `validate` accepts it
  too, so this row is yours alone.
- `id`, `type`, `props` present on every element
- `fill` keeps the form the input used — object or array, never converted

Publish blockers, from [Common issues](https://adapty.io/docs/flow-common-issues.md): no screen
with zero elements; no product element with no product attached; no incomplete interaction.
These are what `validate` is for, one per run. **Never treat a
publish blocker as protection for a defect you left in** — the user clears blockers, and clearing
one often activates whatever it was masking
([products.md → a mismatch you cannot resolve](references/products.md)).

Every price variable's field agrees with its product's period. If the catalog has no product with
the period the design needs, **stop before the write** — that one is not a disclosure.

Warnings — **report, never "fix"**: a component defined but unreferenced; a declared but
unreferenced entry in `variables[]` or `theme`; an inert `conditional` whose branches all
resolve to `nothing`. Real configs contain all of these.

**One warning splits by authorship: a locale value under a code `locales[]` does not declare.**
It renders nowhere. If **you** wrote that value in this run, it is your defect and the fix is
yours — add the code to `locales[]` (`flowkit.config` refuses to emit the stray at all), and make
the parity pass over the *whole* config that adding a locale implies. Only where the stray was
**already in the config you fetched** is it a report-never-fix warning like the others: it is
usually half a locale run someone started, and silently completing or deleting their work is not
your call. Name the two exits — declare it or drop the values — and ask.

## References

- [flow-schema.md](references/flow-schema.md) — what the format **is**: `## The envelope`,
  `## Browser export versus CLI config`, `## Invariants`, `## Shape traps`, `## Vocabulary`,
  including the map from what a user asks for to what the JSON calls it. Read the traps before
  any edit; trap 10 is why phase 4 exists.
- [preview.md](references/preview.md) — `## What a render cannot show you`,
  `## Four surfaces, and they do not agree`, `## When the render fails: the file input, not a
  smaller config`. The evidence behind phase 4; read it when a render surprises you.
- [transforms.md](references/transforms.md) — `## Risk table` and
  `## Decisions you must disclose`: the six points where two answers are both defensible and
  silence is the only wrong one.
- [products.md](references/products.md) — `## Where product ids come from`,
  `## The builder owns product binding`, `## Creating a product`. Read it before touching a
  product element; `products create` writes to a live dashboard.
- the **`paywall-teardown`** skill (ships alongside this one) — what *should* be on the screen and
  what a change is worth: a pattern library with cross-checks, impact tiers and category playbooks,
  read forwards as the design reference when the user gave you none, and backwards to grade a
  render, including your own. It owns every conversion claim and every impact number; this skill
  owns the JSON. Invoke it in phase 2 whenever you are choosing the design, and again in phase 4 to
  correct what you built.
- [patterns.md](references/patterns.md) — `## Where to source a pattern, in order`,
  `## What is safe to lift, and what breaks`, `## Skeletons` for the composites you cannot
  guess: tabs, progress bars, toggles, countdowns.

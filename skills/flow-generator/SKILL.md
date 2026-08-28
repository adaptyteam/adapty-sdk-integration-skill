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

- **`flowProductId`**, the per-screen declaration in `_meta.screens[].products[]` — only the
  builder mints the real value. But you do not need it: the transform service checks a declaration
  is **present and consistent**, so `flowkit.predeclare(screen_id, product_ids)` lets a brand-new
  draft preview on a device with no publish and no builder visit. Omit it and device preview 422s.
  When *rewriting* a flow, never generate one — carry the live `_meta.screens` forward
  ([products.md](references/products.md)).
- **An image you have no readable FILE for.** Given a path you can now upload it —
  `flows media upload` ([media.md](references/media.md)). An image you can only *see* — pasted or
  attached into the conversation — is not one you have: ask for a path. With no file there is
  nothing to upload, so it stays an empty values map, never a made-up URL (trap 5). **SVG uploads
  fail**, so a monochrome glyph is authored inline in `_meta.icons`; a graphic no element can
  express, you draw and rasterize ([media.md](references/media.md)).
- **Real store prices.** They come from the store, not from Adapty; `products create` has no price
  flag.

Everything else is reachable: product UUIDs from `adapty products list` (or `products create`),
`theme` colours sampled off a reference screenshot, and icon SVG authored and then render-verified.
When you do author, [`references/flowkit.py`](references/flowkit.py) owns the mechanical parts —
the `hierarchy`/`map` split above all — and [patterns.md](references/patterns.md) owns the shapes.

It also covers conditions (`when`/`ref`/`all_`/`not_empty`), all fourteen action types, the
eight inputs and the tabs composite — each raising on the shape the transform service refuses.

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
$ADAPTY flows media upload    <IMAGE_FILE> --app <APP_UUID>   # PNG/JPEG/WEBP/GIF, < ~2.5 MB; no SVG
```

**Resolve `$ADAPTY` once, here, and use it for every command.** A global `adapty` is frequently old
— measured at `0.3.0` on a real machine, which has no `flows` topic — and three agents read that as
"validate and preview do not exist" and skipped phases 3 and 4:

```bash
adapty --version                                   # >= 0.8.0 ?  ADAPTY="adapty", done
npm i -g adapty@latest >/dev/null 2>&1 \
  && ADAPTY="adapty" \
  || ADAPTY="npx --yes adapty@latest"              # fallback: prefix not writable
```

**Install once; do not wrap every call in `npx`.** The wrapper costs ~1 s *per call* against
0.07 s installed — more than most of the commands it wraps — and a run makes dozens of calls. When
the global prefix is not writable the `npx` form still works, and there `--yes` is not optional:
without it npx stops to ask permission to install.

Declare a command unavailable only after `npx --yes adapty@latest` *and* `npx --yes adapty@beta`
both lack it — never from a version number you read somewhere.

**In `zsh` — the macOS default — a multi-word `$ADAPTY` is not split into words**, so every command
below fails with `command not found: npx --yes adapty@latest`. Run `setopt shwordsplit` once in the
same shell (verified), or call `npx --yes adapty@latest` in full. That error is a shell problem,
never evidence the command or the CLI is missing.

**`flows media upload` works in production** (measured 2026-08-24, `adapty` 0.8.0). It takes a
local image file and prints a live CDN URL to bind into the config, so an image the user *handed
you a file for* is yours to place, not a user ask. Two limits shape when you reach for it: **SVG
returns `http_500`**, and the ceiling is **~2.5 MB of file bytes** (a bare `http_400` means too
large). Call shape, the two config shapes it binds into, and the geometry:
[media.md](references/media.md).

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

**First** set `$ADAPTY` as [the CLI surface](#the-cli-surface) describes — probe
`adapty --version`, and if it is old **install once globally** rather than paying the npx wrapper's
~1 s on every later call (`npx` only as the fallback). Do it before the first command, not after one fails,
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

**Patch what you just fetched.** A build script or a `draft.json` from an earlier run predates
whatever was done in the builder since, and `config update` replaces everything
([merge.md](references/merge.md)). If such a copy is lying around, diff it against live, report
the `ADDS`/`CHANGES` as the human's edits, and move it out of the way:

```bash
python3 references/diff-config.py <the-old-local-copy>.json flow.working.json
```

**New flow** — `flows create`, then seed its config from one the user already has
(`flows list` → `config get`) so theme, fonts, locales and products are real. Its first
`config update` omits `--expected-updated-at`. **A new flow is the safe default for anything the
user calls new**, because `config update` replaces everything and generating over a flow with
content discards that content.

Then, before editing: **report what the source config contains** — screens and captions,
locales, products, the navigation graph. Before proposing anything; it grounds the user and
catches a wrong flow immediately.

**Confirm the transform.** In scope: add a locale, rewrite copy, add/remove/reorder screens,
branching and conditions, and reusing a piece of another flow — its dependency resolution has a
measured hard-422 class (`flow-schema.md` invariant 8), so it runs through
`references/snippet.py`, never by hand ([snippets.md](references/snippets.md)). A request outside
those is named as out of scope, not improvised.

If the request is *"save this for reuse"* or *"add the thing I saved"*, run
`references/snippet.py plan` before any `graft` — read [snippets.md](references/snippets.md) first.

**Were you given a design to follow?** Answer it out loud: it decides who is choosing. A reference
image, a screen to copy, or a layout they spelled out means *they* chose it — follow it, and
compare against the file rather than your memory of it (phase 4). **Follow the reference for style,
colour, typography, icon style and hierarchy, but keep Adapty's fluid layout discipline**
(`width: fill`, `height: hug`, `position: relative`): never hardcode fixed dimensions or offsets to
match a screenshot's pixels, because fixed geometry breaks across devices (ADP-7117). **No
reference means you are choosing it** — "build me a paywall", "make one that converts" — and the
request map only turns nouns into element types; it says nothing about what sells.

When you are the one choosing, the **`paywall-teardown`** skill is the reference. Invoke it before
you write anything: it returns a **composition** plus the patterns this vertical needs, and it
names the values it refuses to invent — a rating, a review count, an outcome stat, a discount, a
hero asset. **Put those asks to the user before you write the config**, and leave the element out
rather than filling it with a plausible number: a missing element is recoverable, a fabricated
rating is a lie in front of real buyers. Build the composition it names and **do not substitute a
shape you built last time** — that is how two unrelated verticals got the same screen. It also
grades the result in phase 4, where a correction is still free. And when the user wants to know how
*good* a flow is rather than to change it, that answer is a teardown, not a transform.

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

Before the design, because the catalog *gates* it: a trial timeline needs a verified offer, a
period switcher needs plans differing only by period, a price variable needs a matching period.
And picking for them is not a shortcut — it decides what they sell, and it is the one choice on
the screen a screenshot cannot show.

**Assets are resolved here too — upload the file, then build with its URL.** The upload reads a
**path**, so **an image you can only see is not an image you have**: one the user pasted or
attached arrives as pixels in your context with no file behind it, and you cannot write the bytes
you were shown. For every image the screen needs, one of three states, decided before you write the
element:

1. **You have a path that reads** — one they gave you, or a project file you found and *named*.
   Upload it now and bind the URL it returns:
   ```bash
   URL="$($ADAPTY flows media upload --app "$APP" ./hero.png | sed -n 's/^URL: //p')"
   ```
   Bind it as `{"_localizable": true, "values": {"en": {"id": "<id>", "url": "<URL>"}}}` on an
   `image` element, or flat inside a `fill` — two different shapes, and the `id` is a **string**
   even though the command prints a number ([media.md](references/media.md)).
2. **You can see the image but have no path** (pasted, attached), or they named one they have not
   sent — **ask for a path**, once, batched with your other asks. Never guess one: a guess that
   misses fails loudly, and a guess that *hits* ships the wrong picture in a screen that renders
   perfectly. A URL they pointed at is fetchable, but say what you are downloading first.
3. **Nobody has a file** — an empty `values` map (trap 5), reported in the handoff.

**Upload before the preview loop, not after it, and upload each asset once.** A placeholder does
not occupy the space the real asset will, so a screen previewed with placeholders is a screen whose
layout was never checked; and the upload does not deduplicate, so re-running it per iteration
litters the user's media library with copies no CLI command can remove
([media.md](references/media.md#geometry-what-changes-when-the-asset-lands)).

**Before you author a construct you have not seen in a real document, count it.** The schema says
what is *permitted*; a real export says what is *produced*; only the second predicts the device.
One `jq` over the config you fetched and over `references/component-catalog.json` settles it in
seconds — and a count of **zero** is a finding to say out loud, not an absence to shrug at. Three
device-only defects have shipped from skipping this, two of them green on every local gate
([flow-schema.md → Before authoring a shape you have not seen
produced](references/flow-schema.md)).

**Resolve the request into schema terms.** The user's noun is rarely the element `type` — there
is no `button` and no `toggle` element, and tabs are a five-element composite. Use the request
map in [flow-schema.md → Vocabulary](references/flow-schema.md), and source any shape the config
does not already contain via
[patterns.md → Where to source a pattern, in order](references/patterns.md).

**Editing one screen of many? Patch in place with a script — never slice the screen out.** An
isolated mid-flow screen **fails the publish gate** the moment it navigates to a screen that is no
longer there, and isolation buys no speed anyway: `validate` is latency-bound not size-bound, and
`--screen` already isolates the render. A scripted patch of a 187 KB config took 0.01 s and left
every other screen and every flow-level key byte-identical, so there is nothing to stitch back
([transforms.md](references/transforms.md)). Reach the screen with `jq` or a short Python patch
instead of reading the whole file into context.

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
`references/verify-config.py` warns on both fields, and that warning **is** this rule firing —
act on it, never paste it through.

### 3. Check the shape, then clear the publish gate

Walk [Verify](#verify) first — it is local and free and it finds every defect at once, which the
commands below do not. Then **all three gates in one call**:

```bash
BASELINE=flow.backup.json references/gates.sh flow.working.json <APP_UUID> <FLOW_ID>
```

It runs the structural walk, the schema shape check and the publish gate over the *same bytes*,
prints one verdict, and exits non-zero only when something blocking was found. **One call, not
three** — the gates cost well under a second each while an extra round trip costs tens of seconds,
so the turns were the expensive part. Drop the app and flow ids and it says so rather than
pretending a local pass is a publish gate. The three underlying commands, if you need to run one
alone, are in [validate.md](references/validate.md).

**Always pass `BASELINE=`** — the pristine copy from step 2. The schema tracks the newest
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

**Render the screens you changed, in ONE call, and get back one strip to look at:**

```bash
references/shoot.sh draft.json scr_a scr_b scr_c     # preview + screenshot + montage
```

It previews locally (no `--app`, no auth, no save — file-only tasks included), screenshots each
screen with a watchdog, joins them left-to-right and prints the one path to open. **Open that
image and look at it**, against what the user asked for and — if they gave one — against the
reference image file, re-opened, not remembered.

**Render only what you changed.** A screenshot is ~18 s of Chrome cold start, so the number of
renders *is* the cost of this phase, and re-shooting seven screens to check an edit to one is six
wasted launches. One strip is also one *look* instead of N, and a before/after or
default-vs-selected pair only reads as a *difference* when the halves are adjacent.

**Do not try to speed the screenshot itself up** — shrinking `--virtual-time-budget` does nothing
on a fast host, and parallel Chrome is slower than serial. But **raise it when a shot comes back
empty**: on a slow render host 8 s yields no file where 60 s renders correctly, so *no file* is
usually a slow host, not a broken config — `shoot.sh` retries at 60 s for you, and after that,
load the URL in a real browser before suspecting your work
([preview.md](references/preview.md#what-a-render-costs-and-which-knobs-do-nothing)). A dead render
is never a reason to report the work finished.
Measure rather than eyeball with `references/render-measure.py`. Always try the preview: never decide
from the config's size.

**Every image gets its properties checked here — reference build or not — because no other gate
looks at an image at all.** Read the drawn box off the screenshot and choose: `height: hug` takes
its height from the **asset's** aspect, so the layout moves if the file changes and any `value` on
the size is dead; `height: fixed` holds the box and the asset absorbs the mismatch — `cover` crops,
`fit` letterboxes and leaves a dead band. `objectFit` is `fit` or `cover`, no CSS set. Re-render
after each change ([media.md → Geometry](references/media.md#geometry-what-changes-when-the-asset-lands)).

**A reference image raises the bar from "matches the request" to "matches the reference" — run the
fidelity pass before anything is written, every time one was given.** "Nothing jumped out" is not a
result. **Produce a written per-element difference list — colour, typeface, icon style, imagery,
proportions — marking each one match, gap, or unreachable**, then close every gap the format can
reach and turn the rest into named asks. The list is the mechanism, not the looking: measured,
agents who only *looked* shipped emoji for designed icons and colours from memory while disclosing
them, and agents who wrote the list fixed everything reachable.

**Done means every remaining difference is on the ask list** — a user declining previews waives the
deliverable, not this pass. What to inventory and what to do with each gap:
[fidelity.md](references/fidelity.md).

**Read [preview.md → What a render cannot show you](references/preview.md#what-a-render-cannot-show-you)
before you report what a screenshot proves** — every blindness on it measured, and two of them run
the *wrong* way: the render draws things a device will not. Two you act on here: it draws no notch
and no home indicator, so author `safeArea: true` and hand short-device clipping over as a device
check.

**Never downgrade a correct element to a preview-visible lookalike to make the screenshot look
complete.** When an element is preview-blind — a `spinner` that draws nothing on this screen, a
`video`, a toggle's `selected` state, a progress bar's advance — the answer is to keep the real
element, say the preview cannot show it, and hand it to the device check; not to swap in something
the render *can* draw. Standing a static `icon` in for a `spinner` (or any impostor for the element
it mimics) ships a thing that passes the screenshot and does nothing on the device — the
[fake-footer](references/patterns.md#a-bar-that-stays-at-the-bottom-use-footer) mistake in a new
place, and no local gate catches it. A blank in the render is a reason to reach for a device (the
Adapty app), never a reason to author a fake. The loading-screen shape and the `spinner`'s two
non-guessable facts are in [patterns.md](references/patterns.md).

**And the rule is not only about preview-blind elements — it also forbids faking a fully
previewable element because building it properly looks hard.** A **`carousel`** renders in the
preview, so this is where the trap is easiest to rationalize: a static review card plus three
decorative dot `stack`s screenshots exactly like a testimonials slider and is one — one frozen
slide, no swipe, dead dots. The `carousel` is a real element with **built-in `dots`**, so the real
thing is usually *less* work than the fake, and the seed flow you already fetched often contains one
to copy. Resolve the request through the map in
[flow-schema.md](references/flow-schema.md#from-what-the-user-asks-for-to-what-the-json-calls-it)
before you reach for a lookalike — reviews, sliders, swipeable cards and dots all route to
`carousel`, never to hand-built dots. `component-catalog.json` ships a filled `reviews-carousel`
template and `flowkit.carousel()` builds one from scratch; `verify-config.py` **errors** on a
hand-built indicator row and warns on the dotless form. The same trap catches the **`progress-bar`**:
a static filled `stack` or a row of step `stack`s looks like progress and never advances — build the
real `components` entry and wire it per screen via `props.progressBar`, never a bar that cannot move.

**If you built a screen that advances itself, ship the diagnostic with the first ask.** The page
never navigates, so a working auto-advance and a broken one look identical here and only the user's
device can tell them apart — at a real cycle per attempt. Give the `timer` a child `text` carrying
the `timer_minutes`/`timer_seconds` tokens: *digits never appear* is the element not mounting,
*digits reach zero and nothing happens* is the trigger not firing. Without it a failed test returns
one bit and you guess again. Say it is temporary and remove it; the device-verified timer shape is
in [patterns.md](references/patterns.md).

**Confirm you screenshotted the flow at all.** A bad `--device`, a broken fragment and a wrong host
all render as *pages* that pass a "did anything draw" check. If the render is blank, slow or wrong,
switch to [`preview-with-playwright.mjs`](references/preview-with-playwright.mjs), which uses the
page's file input instead of the URL — do not shrink the config. If you cannot render at all, say
so and ask the user to look; never report the work finished on a clean validate.

**A missing element may not be your bug, and a clean preview is not the builder opening the flow.**
Both, with the four surfaces and what each one proves:
[preview.md](references/preview.md).

**A render that matches the request can still be a weak paywall.** Every check above asks whether
you built what was asked; none asks whether the screen sells. **If you chose the design — no
reference, no source screen — running `paywall-teardown` over this PNG is part of the work, not a
courtesy.** Hand it the render *and* the config (one shows what is visible, the other what is
there), then **apply** what it ranks *Fix first* or *High* and re-render. Findings on a screen you
designed are defects, not suggestions — a screen handed over with a list of the patterns you
skipped is unfinished — and this is the cheapest moment, a screenshot instead of a `config update`.
Skip it only on a literal edit: a typo fix, a locale add.

**Iterate here.** Anything off, go back and fix it, then re-run phases 3 and 4. Nothing has
been saved yet, so an iteration costs a screenshot rather than a write.

### 5. Get approval, then deliver — a write or a file

**Whether you need a yes before writing is decided by one observable fact: does the target flow
already have a config?**

**It does not** — a flow you just created with `flows create`, whose `config get` 404s. Write it.
There is nothing to lose and nothing to overwrite, and stopping to ask would be friction over an
empty document. Report what you wrote afterwards.

**It does** — anything you fetched in phase 2. **Stop and get an explicit yes before the write.**
`config update` replaces the entire config: no partial write, no undo, no version history here, so
the document you are replacing exists in exactly one other place — the phase-2 backup. Put all of
this in front of the user in one message and wait:

**First, compute what the write destroys — never describe it from memory.** Run this on the bytes
you are about to write, after the last edit:

```bash
python3 references/diff-config.py flow.backup.json draft.json      # REMOVES = what you destroy
```

The **backup** is the baseline, not your working file: it is the one copy nothing in the run has
touched, so it is the only honest answer to "what was there before me". (An edit that landed after
you fetched is the lock's job, not this one's.)

Every `REMOVES` line goes in the ask below, traced to the request that asked for it, and **one you
cannot trace is someone else's work**: name it and ask, never write past it. Exit 1 says the list
is non-empty, not that anything is wrong — deleting a screen is a supported transform, doing it
silently is not ([merge.md](references/merge.md)).

**Then show them the change — an approval on a description is not an approval on the screen.**
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
flow**, so N tabs is N times the noise and still not the flow. Open the screen whose *state* matters
most — a picker, a toggle, a selected plan — because state is the one thing a static PNG cannot
show. **Identical screenshots do not mean an identical config**
([preview.md](references/preview.md)); that is what the second list is for.

> About to overwrite the config of **<flow name>** (`<flow-id>`), currently **<status>**.
>
> <the two lists above>
>
> - Element count: <before> → <after>
> - Removes: <the `REMOVES` lines, each traced to the request that asked for it — or "nothing">
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

Verified byte-identical on a real flow — so the recovery is real, but only if phase 2 actually
took the backup, which is why that step is not optional.

Only then:

```bash
# one call: re-read the lock and write under it, because your own last write invalidated it
UA="$($ADAPTY flows config get $FLOW --app $APP --json | jq -r .updated_at)" \
  && $ADAPTY flows config update $FLOW --app $APP --config-file draft.json \
       --expected-updated-at "$UA" --json > flow.working.json
```

Validate and preview both run on a local file, which is why the write comes last: one write when
the thing is right, instead of one per iteration. If you have already written and then found a
problem, that is fine — re-read `updated_at` from `config get` before the next write, because
yours is now stale.

**That `--json` redirect *is* the read-back — no extra call.** The write returns the **same
envelope as `get`**, so your working file is already in sync for the next round, and you can diff
it against what you sent. A faithful round trip is the norm, so any difference is a real finding —
a top-level key that vanished, a `status` you should not have emitted.

A write that changes nothing does not bump `updated_at` (measured once), so re-running the same
content is not a fresh lock token. **On a 409** someone edited the flow since you fetched it and
nothing was written: re-`get`, re-apply your change **to their config**, write again. Never force
past it and never re-send your local copy — that is the content that would erase their work. If
their version differs in ways you did not author, ask rather than restore.

**If you rebuilt the config from a script rather than patching the fetched one, you have the wrong
document** — a rebuild replaces the live flow, taking `_meta.screens`
([products.md](references/products.md)) and every manual edit with it. Patch the fetched config;
[merge.md](references/merge.md) names the only two cases where a rebuild is right.

#### The file deliverable

When the user asked for a file rather than a write, there is no approval gate — the contract lives
in phase 2, **at the moment the file is written**, and your closing report repeats which
`status`/`id` shape you chose. A file handed over without that sentence is undelivered.

**Never end with the work in a local file.** `config update` is the only save this surface has, and
there is no publish command, so saving is as far as you can take it.

**Then end with this callout, every time.** A save is not a release, and the user is the only one
who can finish it. Fill the slots and keep all three steps plus the closing line — that line is the
point:

> **Saved as a draft — your users can't see this yet.**
>
> 1. **Review it:** https://app.adapty.io/flows/<FLOW_ID>/builder — refresh the page if you
>    already have it open, the builder does not notice a CLI write.
> 2. **Preview on a real device.** **Check `<the specific things this build could not verify>`.**
>
>    Open this on the device you want to test on — it launches the flow in the **Adapty mobile app**,
>    the actual SDK renderer.
>
>    <the preview link, bare>
>
>    On mobile, tap the link to preview.
>    <the QR image line if they asked for one; otherwise the offer, or nothing>
> 3. **Publish:** the button at the **top right of the editor**.
>
> Until you publish, everyone continues to see the previous version.

**Build the link for slot 2 yourself — do not send the user hunting for it.** It is pure string
construction from the app id, the flow id and the config's `locales`, so
[`mobile-preview.mjs`](references/mobile-preview.mjs) produces it with no network call and no auth:

```bash
# The link alone — the default. No image, no window, no `qrcode` dependency.
(cd ~/.cache/adapty-flow-qr && node <abs-path>/references/mobile-preview.mjs \
  --app <APP_UUID> --flow <FLOW_ID> --config <abs-path>/flow.working.json)

# Add a QR as well, when it will actually be scanned:
#   … --qr --md-base <your working directory>
```

**The link is required in the callout. The QR is off unless the user asked for it.** `--qr` writes a
PNG into the working tree and opens a window on their screen, so it is not a free addition.

**Decide from what they actually said — nothing else is observable.** You cannot tell whether someone
is at a laptop, holding a phone, or about to test anything, so do not build the decision on it:

| What you have | What you do |
| :--- | :--- |
| they asked for a QR, to scan, or to test on a device | `--qr`, and keep doing it for the session |
| they asked for the link only, or declined a QR | link only, and **do not offer again** |
| anything else, including no signal at all | **link only, plus the one-line offer below** |

The offer is what makes it discoverable without imposing it. Add to the callout, once:

> On mobile, tap the link to preview. If you want a QR code to scan for device preview, just say so
> and I'll generate one.

**Frame it as two situations, not two options for one situation.** The link works when they are
reading *on the device they want to preview on* — they tap it and the flow opens there. The QR is for
when they are reading on a laptop and the device is a separate one they have to reach. "A QR instead
of tapping the link" gets that wrong: it implies the two are interchangeable, when the link alone
already covers the phone reader completely and the QR exists only for the reader whose phone is not
the thing in front of them.

That costs a line, works whatever surface they are on, and puts the choice with the person who knows
the answer. **A default-on QR is the wrong trade**: it pops a window at everyone to save one round
trip for the subset who wanted it.

The callout degrades cleanly either way — slot 2 keeps its sentence and its link, and loses only the
image.

**Run it after the write, never before:** the app fetches the saved draft, so a link built over an
unsaved file previews the *previous* version and looks like your edit did nothing
([preview.md](references/preview.md#the-mobile-app-link-and-why-it-is-not-the-render-url)). One
link survives later writes, so it is worth handing over once rather than per change.

**When you do pass `--qr`, it opens the image and prints one line to paste:**

```
![Scan to preview on your phone](flow-preview-qr-<flowid8>.png)
opened /abs/path/flow-preview-qr-<flowid8>.png
```

**Opening it is the point — do not replace that with something the reader has to act on.** Two
attempts came before it and both left work for them: a `file://` URL is *not clickable in a
terminal* (measured), and printing `open <path>` still means copy-pasting before they can scan
anything. `flows config preview` already opens a browser on a TTY rather than handing over a URL;
this is the same move. On a headless host, in a container or under `CI` there is nothing to open
with, so the script prints the opener command instead and the run is still fine.

**Paste the `![...](...)` line into your answer as well, and do not try to detect whether it will
render.** `$TERM` describes where your *bash calls* run, not where your *answer* is displayed — a
property of the subprocess against a property of the reader's app, and they come apart over SSH, in
containers, and in any client driving a remote shell. The one data point in hand is a client with an
empty `TERM` that rendered an inline image perfectly, i.e. the heuristic pointing the wrong way.

Emitting it unconditionally is safe because the costs are asymmetric: where images render, the reader
scans without leaving your answer; where they do not, Claude Code's terminal shows
`Scan to preview on your phone (flow-preview-qr-b49806c9.png)` — **one readable line** (measured).
Dropping it loses the inline QR on every client that would have shown one.

`--md-base <your working directory>` is what makes the inline form work: the path has to be
**relative and inside the directory the client resolves from**. An absolute one is refused outright
— *"This file is outside the working directory. It can't be opened here."* The script warns if the
image landed outside the base rather than emitting a path that silently will not render. That is
also why `--qr` writes beside the config rather than into the current directory: the invocation
above runs from the `qrcode` cache dir. The image is a throwaway — regenerate rather than keep it,
and never commit it.

**There is no character-art QR, and do not add one.** It was built twice and removed twice: it
tolerates zero line gap so it dies in any rendered answer, `qrcode`'s own terminal renderer is wrong
in two ways that only show on a dark theme, and a correct block is 31 rows x 61 cols for this link —
too big to put in front of anyone, with no payload change that meaningfully helps
([preview.md](references/preview.md#why-there-is-no-terminal-qr-after-two-attempts-at-one)).

**The bare link goes in every callout, on its own line.** It is the only form that serves a reader on
the device they want to preview on — a QR is unusable to someone holding the only camera they have,
and that reader needs no second affordance. Keep it out of backticks: a code span is not a link, and
most terminals will linkify a bare URL.

**Fill that slot with the actual list, never with "check it works".** You know which of your
choices the render could not reach — a branch that fires on tap, a toggle, a non-default locale, a
progress bar that advances, a screen that advances itself, glyph metrics that differ on iOS. A
generic instruction gets skipped; three named things get tapped, and every defect this skill has
shipped to a user came through a gap this slot exists to hand over
([preview.md](references/preview.md)).

## Safety

**Pass `--expected-updated-at` on every write except the first.** A stale value fails instead of
clobbering, so this is a real guarantee rather than a warning. Read it from `config get`
immediately before you write. Omitting it is last-write-wins and will silently overwrite an edit
someone else made in between.

**The lock is not a merge.** It guards the *timing* of a write and says nothing about its
*content*: a document that was never based on the live config — regenerated, or patched from a
stale local file — passes the lock and overwrites the flow anyway. So patch what you fetched, and
diff before you write ([merge.md](references/merge.md)).

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

Walked in phase 3 **before** the two commands, because this finds every row at once locally where
`validate` reports one per round trip.

**`references/verify-config.py` ships and phase 3 runs it, and it mechanises all but two of the
referential rows.** So do not re-derive them by eye: run it, and read its output as the checklist.
The full statements — what each invariant is, what breaks it, what a violation does — are
[flow-schema.md → Invariants](references/flow-schema.md#invariants), which owns them.

**What the tool cannot answer, and you must:**

| Check | Why no tool catches it |
| :--- | :--- |
| `fill` keeps the form the input used — object or array, **never converted**, and **one layer** | the form is only wrong relative to the input you fetched |
| an image URL is one **`flows media upload` printed in this session** | a plausible `public-media.adapty.io` path is indistinguishable from a real one |
| `_meta.icons[].raw` is **real** SVG, not fabricated markup | presence is checkable, authenticity is not |
| **every price variable's field agrees with its product's period** | needs the catalog, not the config |

That last one is a **hard stop, not a disclosure**: if the catalog has no product with the period
the design needs, stop before the write.

**Publish blockers** ([Common issues](https://adapty.io/docs/flow-common-issues.md)): a screen with
zero elements, a product element with no product, an incomplete interaction. `validate` reports one
per run. **Never treat a publish blocker as protection for a defect you left in** — the user clears
blockers, and clearing one often activates whatever it was masking
([products.md](references/products.md)).

**Warnings — report, never "fix":** an unreferenced component; a declared but unreferenced entry in
`variables[]` or `theme`; an inert `conditional` whose branches all resolve to `nothing`. Real
configs contain all of these.

**One warning splits by authorship: a locale value under a code `locales[]` does not declare.** If
**you** wrote it this run it is your defect — add the code and make the parity pass that adding a
locale implies. If it came **with the config you fetched**, it is report-never-fix like the others:
it is usually half a locale run someone started, and finishing or deleting their work is not your
call. Name the two exits and ask.

## References

Each file **owns** its facts; link rather than restate, or the copies drift.

| File | Read it when |
| :--- | :--- |
| [flow-schema.md](references/flow-schema.md) | **Before any edit.** The envelope, `## Invariants`, `## Shape traps`, and `## Vocabulary` — the map from what a user asks for to what the JSON calls it |
| [validate.md](references/validate.md) | `validate` says no, or you want to know what a green run does *not* prove |
| [preview.md](references/preview.md) | A render surprises you: what it cannot show, what it costs, the four disagreeing surfaces, and what to do when it fails |
| [fidelity.md](references/fidelity.md) | A reference image was given — the per-element inventory, the gap-closing ladder, and what becomes a user ask |
| [media.md](references/media.md) | The screen has an image: the upload's limits, element-versus-`fill` shapes, geometry, and when to rasterize |
| [products.md](references/products.md) | Before touching a `product` element — `products create` writes to a live dashboard |
| [merge.md](references/merge.md) | The flow has been edited by a human since it was generated, or you are tempted to re-run a build script over an existing flow |
| [transforms.md](references/transforms.md) | You hit a point where two answers are defensible and silence is the only wrong one |
| [patterns.md](references/patterns.md) | You need a composite you cannot guess: tabs, progress bars, toggles, countdowns, plan cards |
| the **`paywall-teardown`** skill | **Phase 2** when *you* choose the design, **phase 4** to grade what you built. It owns whether the screen sells; this skill owns the JSON |

Executable, all under `references/`: `flowkit.py` (authoring), `verify-config.py` (phase 3),
`validate-with-schema.mjs` (phase 3), `diff-config.py` (phase 2 and phase 5), `montage.py` and
`render-measure.py` (phase 4), `preview-with-playwright.mjs` (when a render fails),
`mobile-preview.mjs` (phase 5, the device-preview link).

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
  combinations tested against 5 real triples). This is a **handoff step, not a dead end**: binding
  `product.id` on a `product` element is all an agent needs to do, and the builder declares the
  products the first time someone opens the flow. Tell the user to open it once before publishing —
  a publish before that first open is what produces *Unknown Product Id*. See
  [products.md](references/products.md).
- **Uploaded assets.** An image you do not have is an empty values map, never a made-up URL
  (trap 5).
- **Real store prices.** They come from the store, not from Adapty; `products create` has no price
  flag.

Everything else is reachable: product UUIDs from `adapty products list` (or `products create`),
`theme` colours sampled off a reference screenshot, and icon SVG authored and then render-verified.
When you do author, [`references/flowkit.py`](references/flowkit.py) owns the mechanical parts —
the `hierarchy`/`map` split above all — and [patterns.md](references/patterns.md) owns the shapes.

## The CLI surface

```
adapty auth login                                             # browser flow
adapty auth whoami                                            # verifies the token server-side
adapty apps list --json                                       # to get <APP_UUID>

adapty flows list   --app <APP_UUID> [--page N] [--page-size N]    # page-size max 100
adapty flows create --app <APP_UUID> --name <name>            # row only; always `draft`
adapty flows get    <FLOW_ID> --app <APP_UUID>
adapty flows config get      <FLOW_ID> --app <APP_UUID> --json     # 404 until first write
adapty flows config validate <FLOW_ID> --app <APP_UUID> (--config-file <f|-> | --config <json>)
                                     [--source <caller>]
adapty flows config preview  <CONFIG_FILE> [--screen <id>] [--device <id>] [--orientation …]
adapty flows config update   <FLOW_ID> --app <APP_UUID> \
    (--config-file <file|-> | --config <json-string>) \
    [--expected-updated-at <int>] [--remote-configs <json>]
```

**Version floor, and it is split.** `flows` and `flows config get/update` ship in `adapty`
**0.6.0**. `config validate` and `config preview` ship only in **0.6.1-beta.0** so far. Check with
`adapty flows config --help`.

**If the commands are missing, run them through `npx` before concluding anything.** A globally
installed `adapty` is frequently old — measured on a real machine at `0.3.0`, which has no `flows`
topic at all — and three agents in a row read that as "validate and preview do not exist here" and
skipped phases 3 and 4 entirely. They do exist; the invocation was wrong:

```bash
npx adapty@beta flows config --help      # then use `npx adapty@beta …` for every command
```

Only after `npx adapty@beta` also fails to offer them may you tell the user they are unavailable.
Do not compute their absence from a version number you read somewhere.

**There is no `flows publish` and no `flows delete`.** Publishing and deleting are dashboard
actions. Never write a command name the CLI does not have.

Four facts about the config commands that are not guessable:

- **`config get` returns an envelope, not the config**: `{config, remote_configs, status,
  updated_at}`. The document you transform is the `config` field, and `--config-file` on
  `update` takes that field alone.
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

### 1. Authenticate

`adapty auth whoami`. It hits the server and prints the name and companies, so it proves the
token works. Prefer it to `auth status`, which only reports what is stored locally and does not
verify it — it happily prints `Email: undefined` next to a working token.

If it fails, `adapty auth login` opens a browser. That is the user's to complete; wait for them
rather than retrying in a loop. Then `adapty apps list --json` for the `<APP_UUID>` every later
command needs.

### 2. New flow, or existing flow

Decide this explicitly and say which you chose, because the two paths differ in what they can
destroy.

**Existing flow** — the user names it, or `flows list` and confirm the match back to them
before touching it. Then `flows config get`, and **keep the `updated_at`** for the write.

**Take a backup before the first edit.** `config update` replaces the whole config and there is no
undo, so the copy you fetched is the only way back:

```bash
adapty flows config get --app $APP $FLOW --json > flow.working.json
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

**Resolve the request into schema terms.** The user's noun is rarely the element `type` — there
is no `button` and no `toggle` element, and tabs are a five-element composite. Use the request
map in [flow-schema.md → Vocabulary](references/flow-schema.md), and source any shape the config
does not already contain via
[patterns.md → Where to source a pattern, in order](references/patterns.md).

**Apply**, preserving every key you did not deliberately change — including unrecognized ones.
**Nested** unknown keys survive a round trip; unknown keys at the **top level of `config`** are
discarded, so never park anything there.

Write the result to a local file. Phases 3 and 4 both work on that file, with nothing saved yet.

### 3. Check the shape, then validate

**Two checks, and they do not overlap.** `flows config validate` answers *is this publishable* and
does **not** check the shape of most props — it accepts `fill: "banana"` and `schemaVersion: 999`.
A schema check answers *are these props well-formed* and knows nothing about publishability. A clean
run of either is not evidence about the other.

```bash
npx --yes --package=ajv@8 node references/validate-with-schema.mjs \
  --config flow.working.json --baseline flow.backup.json
```

**Always pass `--baseline`** — the pristine copy from step 2. The published schema tracks the newest
`schemaVersion` while most live flows are older, so an unbaselined run on a v9 flow reports hundreds
of pre-existing mismatches, none of them yours; the baseline leaves only what your edit caused.
Details and the fetch-and-cache line in
[flow-schema.md → the two different validators](references/flow-schema.md).

Then the server-side check:

```
jq '.config' flow.working.json | adapty flows config validate --app $APP $FLOW \
    --config-file - --source byo-cli --json
```

Advisory and **does not save**. It answers one question — *is this publishable* — and prints
`Config is publishable.` or `Config is NOT publishable.` It takes the **bare `config`**, not the
envelope. `--source` is caller attribution; set it when you are not the `adapty` CLI itself.

**Read the shape of a failure.** An element-level error carries a `Code` and a `Path`
(`screens["scr_…"].elements.map["el_…"]`) — act on it directly. A bare **`Invalid flow input`** with
no path means the document is malformed *structurally*, not at an element: diff against the config
you fetched, or bisect the edit. **Warnings are advisory and usually pre-existing** — fix the
errors, and do not report warnings as though they blocked anything.

**A clean validate is weaker than it sounds.** It skips whole prop subtrees, so it is a floor and
not a proof — which is why the schema check above and the checklist below both still run.

**Read the verdict, not the exit code.** Exit 1 means either "not publishable" *or* "the call
failed", and the two are indistinguishable from the status alone. With `--json` they are not:
a publishability verdict has a `valid` field, a failure has an `error` object. At the time of
writing the endpoint itself returns `{"error": {"statusCode": 404, …}}` and exit 1 on a config
known to render — so an agent gating on the exit code alone would report a good config as
broken. Check the field.

If `validate` is absent (0.6.0) or returns an error, say which happened and fall back to
[Verify](#verify) below. Do not skip that checklist even when `validate` passes: it answers
publishability, not well-formedness, and the two configs that broke the builder in trap 10 were
both publishable-looking.

### 4. Preview, and iterate until it looks right

```
adapty flows config preview draft.json [--screen <id>] [--device iphone-14] [--orientation portrait]
```

**Fully local**: no `--app`, no flow id, no auth, no network, no save. The whole config rides in
the URL fragment, so this works on a file you have not written anywhere. It accepts either a
`config get` envelope or a bare config; `screens` must be an array.

**Never print or read the URL.** It is thousands of characters of gzipped base64 — 6,349 for a
56KB config, ~113K for a 668KB flow — and it carries zero information you can act on. On a TTY the
command opens a browser and prints nothing else. **Piped without `--json` it prints the bare URL**,
which is the form you want.

**Do not add `--json` here.** It prints `{"render_url": "…"}`, an object — not the URL. An agent
that captured that into `$URL` and handed it to Chrome silently screenshotted the browser's new-tab
page and nearly reported it as the paywall. Use the bare form:

```bash
URL="$(adapty flows config preview draft.json)"
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --disable-gpu \
  --hide-scrollbars --window-size=430,932 --virtual-time-budget=12000 \
  --screenshot=shot.png "$URL"
```

Then **open `shot.png` and look at it.** Compare it against what the user asked for — layout,
spacing, copy, whether the right tab is selected, whether anything is clipped or detached. Use
`--screen` to step through the rest; the default is the flow's first screen.

**What this catches, precisely.** It catches the class no structural check can see: wrong
spacing, a magic-number indent, a detached element, a state that is silently wrong. It does
**not** subsume [Verify](#verify) — both defects in trap 10 were injected into a known-good
config and measured, and both still rendered. They lost a selected-tab highlight and nothing
else, which is visible to someone who knows what the screen should look like and invisible to
any "did anything draw" test. The structural rows catch them for free; keep walking them.

**If the user gave you a reference image, compare against the image — not your memory of it.**
Save the attachment to a file the moment you receive it, and re-open it beside every render you
take. A description you wrote after one look is not the reference: building from one produced a
timeline whose rail *width* was right to the pixel and whose *continuity, colour order and last-row
rail* were all wrong, none of which was visible without the two images side by side. If the image
has already dropped out of context, it is recoverable — user attachments are stored base64 in the
session transcript (`~/.claude/projects/<project>/<session>.jsonl`, blocks with
`"type":"image"`) — so extract it rather than guessing again.

Comparing means *measuring*, not glancing. `tests/render-measure.py` does it for either image —
`--row Y` for widths, `--column X0:X1` for painted runs and the gaps between them, and
`--scale <image-width>:<device-points>` to convert a reference's pixels into the numbers you put in
a config.
That is how the rail was confirmed correct at 46/38 while the eye kept insisting it was too narrow,
and how the real defect — a 14px break between connector and chip — was found.

Three things it is blind to. Knowing them is what keeps a screenshot from becoming an overclaim:

- **A stranded variable.** The render prints an unresolved reference as its literal token, so a
  screen reading `{{name.value}}` looks *pixel-identical* whether its producer still exists or was
  deleted three screens ago — measured, two renders with the same MD5. Whether a consumer still
  has a producer is a Verify question (invariant 12) and preview will never answer it.
- **Any locale but the one it draws.** The render ignores `defaultLocale` and the order of
  `locales[]` — measured: forcing `defaultLocale: "de"`, and putting `de` first, both produced
  byte-identical screenshots to the untouched file. **A locale transform therefore cannot be
  verified visually at all.** Say so, and tell the user to switch locale in the builder and look
  for overflow, because translated text is routinely longer than its source.
- **Anything resolving at runtime.** Real prices, store currency, user input. Placeholder `$0.00`
  prices and broken asset URLs are usually the preview lacking data, not a defect you introduced —
  and a price variable in particular renders as the full literal `{{<uuid>.prod_price}}`, which is
  *far longer than any price*. It wraps to extra lines and can push text under a docked CTA, so the
  screenshot shows an overlap that will not exist once the price resolves. **Never restyle a layout
  to fix crowding you only see around a token.** Substitute a plausible price into a throwaway copy
  of the config, render that, and judge the layout at production text length.
  render the source too and compare before blaming your own edit.

**A clean preview does not prove the builder will open the flow.** The preview page and the
Flow Builder's editor are different renderers, and the two configs that broke the builder in
this project's history both render here. So report a good screenshot as "this looked right at
this size", never as "the flow works".

**There are four surfaces and they do not agree.** Know which one you are quoting:

| Surface | What it tells you |
| :--- | :--- |
| `config preview` + a screenshot | fast, scriptable, and a *different renderer* — layout and spacing only |
| the Flow Builder editor | whether the authoring tool can open it; where the user reviews and publishes |
| the **Adapty mobile app** | the real **SDK** renderer — the only preview that reflects what a user gets, and therefore the one that would surface an `unsupported_…_setting` the transform service warned about |
| published and live | the truth, and the only state your users ever see |

You can reach the first. Everything below it belongs to the user, which is why the callout in phase 5
asks for the mobile-app preview explicitly rather than treating a screenshot as sign-off.

**Iterate here.** Anything off, go back and fix it, then re-run phases 3 and 4. Nothing has
been saved yet, so an iteration costs a screenshot rather than a write.

**Do not decide whether to preview from the file size.** The command's own help calls it a
quick-look escape hatch and mentions ~32KB of pretty-printed JSON as the point where the render page
gets slow. That is a symptom to watch for, **not a budget to check a config against** — and two
agents used it as grounds to skip previewing entirely, on configs that render fine. Measured:
a 171KB config renders, and so does a 143KB one; gzip in the fragment is very effective, so 56KB of
config yields a 6,349-character URL. Always try the preview. If the render comes back slow,
truncated or blank, *then* fall back to the dashboard.

**`--device` is not validated — a wrong value renders a page, not an error.** The flag accepts any
string, exits 0, and the render page answers an unrecognized id with the words
`Unknown device "…"` on a blank background. That screenshot carries a few hundred distinct colours
from text antialiasing, so it survives a naive "did anything draw" check and looks like a successful
preview. `iphone-14` (the default) and `iphone-13-mini` are confirmed to work; `iphone-se`,
`iphone-12-mini`, `iphone-8` and `pixel-7` are not recognized, and there is no published list. So
stay on the default unless you have a reason to change it, and if you do pass `--device`, confirm
the image shows the frame you asked for rather than that message.

If `preview` is unavailable even through `npx`, or you have no way to render a page, say so plainly
and ask the user to look — never report the work finished on the strength of a clean validate.

### 5. Write, then hand off the publish

Only now:

```
adapty flows config update <FLOW_ID> --app <APP_UUID> --config-file draft.json \
    --expected-updated-at <int-from-config-get>
```

Validate and preview both run on a local file, which is why the write comes last: one write when
the thing is right, instead of one per iteration. If you have already written and then found a
problem, that is fine — re-read `updated_at` from `config get` before the next write, because
yours is now stale.

**When the user wants a file instead** — "write the result to a new file", "give it back so I can
upload it" — there is no `config update` and no envelope, so the `status`/`id` rule above does not
decide it for you. Two things are certain: **never emit `"status": "published"`**, and the flow
`id` in a document names the flow it came *from*, not the one the user will import into. Beyond
that, pick a shape and **say what you picked** — whether you dropped `status` and `id` or kept
them, and that the user must direct the import at the flow they actually mean. Measured: three
agents on one round split on this silently-ish, which is exactly the kind of divergence a sentence
in the report resolves.

**A 409 means someone else edited the flow, and it is the lock working — never force past it.**
The write is rejected with `statusCode: 409` and a message naming the person: *"This flow
configuration was already updated by <name>. Reload before saving to avoid overwriting their
changes."* Nothing was written. The recovery is **re-`get`, re-apply your change to the config you
just fetched, write again** — never retry the same body against a newer `updated_at`, and never
reach for the version you built locally, because that is precisely the content that would erase
their work.

Re-applying means editing *their* config, not diffing yours over it. Fetch, make your specific
change to the fetched document, and write that — a config the user has opened in the builder may
differ from your local copy in ways you did not author, including a **`schemaVersion` migration**
(see [flow-schema.md → the schema is not the authority](references/flow-schema.md)). And check what
actually changed before you re-apply: a 409 sometimes means the user deliberately removed something
you added, in which case putting it back is not a merge but a reversal. Diff element captions and
copy against your own version, and if the difference looks intentional, **ask rather than restore**.

**Read it back.** `flows config get` again and diff against what you sent. A faithful round trip
is normal — 108 of 108 elements on a real screen — so a difference here is a real finding, and
it catches the drop-silently class: a top-level key that vanished, a `status` you should not
have emitted.

**Before writing a regenerated config, carry builder-owned state forward.** If your edit came
from a script that rebuilds the document rather than patching the one you fetched, re-read the live
config and merge `_meta.screens` into it — `config update` replaces everything, so an empty
`_meta.screens` wipes the product attachments someone made in the builder, and `flowProductId`
cannot be recomputed. See
[products.md → builder-owned means do not omit it](references/products.md).

**Always finish by writing.** Never end a task with the work sitting in a local file — a config
that was validated and previewed but not saved is not delivered. `config update` is the only "save"
this surface has; there is **no publish command** (`flows` is `create`/`get`/`list` plus
`config get/update/validate/preview`, verified on 0.6.1-beta.0), so saving is as far as you can take
it and the final publish is genuinely the user's.

**Then end with this callout, every time.** A save is not a release, and the user is the only one
who can finish it. Fill the slots and keep all four lines — the last one is the point:

> **Saved as a draft — your users can't see this yet.**
>
> 1. **Review it:** `https://app.adapty.io/flows/<FLOW_ID>/builder` — refresh the page if you
>    already have it open, the builder does not notice a CLI write.
> 2. **Preview on a real device:** open the flow in the **Adapty mobile app**. That is the actual
>    SDK renderer, so it is the only preview that reflects what users will really get.
> 3. **Publish:** the button at the **top right of the editor**.
>
> Until you publish, everyone continues to see the previous version.

Say it even when the change was small, and even when the user already knows — a config that is saved
but unpublished looks identical to a config that shipped, and that is precisely the confusion this
prevents. If the flow already had a published version, add that saving moved it to `dirty`: the
draft has now diverged from what users see.

Then say what changed, and what still needs them:

- which decisions had more than one defensible answer
  ([transforms.md → Decisions you must disclose](references/transforms.md))
- products to attach, assets to upload

Say plainly what your checks covered. A clean verify means "this will save"; a clean validate
means "this should publish"; a screenshot you looked at means "this looked right on one screen
at one size". Only the last is evidence about the render, and it is not evidence about the ones
you did not open.

## Safety

**Pass `--expected-updated-at` on every write except the first.** A stale value fails instead of
clobbering, so this is a real guarantee rather than a warning. Read it from `config get`
immediately before you write. Omitting it is last-write-wins and will silently overwrite an edit
someone else made in between.

**Never write to a flow the user did not name.** `flows list` is for finding the right one and
confirming it back to them, not for picking one yourself.

**`config update` replaces the whole config.** There is no partial write and no undo. Prefer a
fresh `flows create` for new work.

**Deleting a flow is a dashboard action.** There is no `flows delete`, so never claim to have
removed one — including a throwaway you created yourself. Name the flow and tell the user where
to delete it.

`validate` and `preview` change nothing and cost nothing. Use them freely.

## Verify

Walked in phase 3, alongside `validate` rather than instead of it.

Neither this list nor `validate` is the binding gate. **Publishing runs a transform service that
refuses configs `config update` accepted** — with an HTTP 422, a fatal `error`, and an `issues`
array whose `severity` separates fatal from advisory. See
[flow-schema.md → The transform service is the authoritative validator](references/flow-schema.md).
If the user shows you its output, read the `path` fields: they name the offending element, not just
the screen.

Referential — full statements in [flow-schema.md → Invariants](references/flow-schema.md):

- `elements.map` keys equal each element's own `id`
- `hierarchy` resolves into `map`; `root` and `{"type": "global"}` component nodes are the only
  hierarchy ids with no `map` entry
- every `navigate` `payload.screen` names a screen that still exists, including targets nested
  inside a `conditional`'s `cases` and `default`
- every `product` element's `props.product.id` is declared in `_meta.screens.<thatScreenId>.products[]`
- price variables resolve by their own form — a product-relative head is a declared product, a
  group-relative head is a `product`-typed group; **never validate one against the other**
- `selectableGroups` and `groupId` agree in both directions
- every `const` compared against `<groupId>.selectedOptionId` matches a member's `customId`
- every variable consumer still has its producer, including across screens
- `colorId` and `font.preset` resolve in *this config's* `theme`; `font.family.id` in `_meta.fonts`
- every icon used appears in `_meta.icons` **with real `raw` SVG** — never fabricate the markup
- every locale in `locales[]` has a value in each `_localizable` field you touched

Well-formedness — cheap, and it is what a crash looks like:

- **every element under a screen's `elements.map` carries `states`** (`[]` is fine). Missing it
  produced a config the API accepted and the builder could not open.
- `id`, `type`, `props` present on every element
- `fill` keeps the form the input used — object or array, never converted

Publish blockers, from [Common issues](https://adapty.io/docs/flow-common-issues.md): no screen
with zero elements; no product element with no product attached; no incomplete interaction.
These are what `validate` is for; check them yourself when it is unavailable. **Never treat a
publish blocker as protection for a defect you left in** — the user clears blockers, and clearing
one often activates whatever it was masking
([products.md → a mismatch you cannot resolve](references/products.md)).

Every price variable's field agrees with its product's period. If the catalog has no product with
the period the design needs, **stop before the write** — that one is not a disclosure.

Warnings — **report, never "fix"**: a component defined but unreferenced; a declared but
unreferenced entry in `variables[]` or `theme`; an inert `conditional` whose branches all
resolve to `nothing`. Real configs contain all of these.

## References

- [flow-schema.md](references/flow-schema.md) — what the format **is**: `## The envelope`,
  `## Browser export versus CLI config`, `## Invariants`, `## Shape traps`, `## Vocabulary`,
  including the map from what a user asks for to what the JSON calls it. Read the traps before
  any edit; trap 10 is why phase 4 exists.
- [transforms.md](references/transforms.md) — `## Risk table` and
  `## Decisions you must disclose`: the six points where two answers are both defensible and
  silence is the only wrong one.
- [products.md](references/products.md) — `## Where product ids come from`,
  `## The builder owns product binding`, `## Creating a product`. Read it before touching a
  product element; `products create` writes to a live dashboard.
- [patterns.md](references/patterns.md) — `## Where to source a pattern, in order`,
  `## What is safe to lift, and what breaks`, `## Skeletons` for the composites you cannot
  guess: tabs, progress bars, toggles, countdowns.

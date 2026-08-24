# Reusing patterns

Where to get a working shape from, what is safe to lift, and the minimal skeletons for the
composites you cannot guess.

Read this when a request names something the input flow does not already contain. If the input
already has one, copy that instead — it is better than anything here.

## Where to source a pattern, in order

1. **The input flow itself.** Always first. Its ids, theme, fonts and products are already
   consistent, so a shape lifted from one of its screens needs no repair. Copy the block,
   change the copy and the ids, keep everything else. A screen that renders today is the
   strongest evidence available about the format.
2. **Another of the user's own flows in the same app.** `adapty flows list --app <APP_UUID>`,
   then `flows config get` the one that has the shape you need — no need to ask for an export.
   Same app means products and custom fonts still resolve; see the break list below for what
   does not.
3. **`component-catalog.json`, which ships in this directory.** 36 official templates with named
   slots — `footer` (cta/terms/privacy), `quiz-icons`, `quiz-icon-grid`, `chk-radio-on`/`off`,
   `chk-toggle-on`/`off`, `list-timeline`, `list-comparison`, `list-icons`, `tabs-segmented`,
   `ue-social-proof`, four timer variants and more. **Query it, never read it whole** (428KB):

   ```bash
   jq -r '.components[].id' references/component-catalog.json
   jq '.components[]|select(.id=="footer")' references/component-catalog.json
   ```

   Each entry carries `slots`, `keywords`, `insertion_policy` and an **`agent_allowed`** flag.
   Respect it: `prod-vertical-list` is `agent_allowed: false`. Filling a template's slots beats
   assembling a skeleton below, because the template's internal wiring is already correct.
4. **The skeletons in this file.** Last resort. They are minimal and carry no theme, so every
   `colorId`, `font.preset` and id in them has to be replaced with the input's own before use.

A radio, a toggle, a checkbox and a segmented tab bar all exist as catalog components. Hand-building
one is how this project shipped a radio whose dot was filled at rest, so it looked selected on every
card. Check the catalog first.

Never source a shape from memory of some other flow. The vocabulary is per file: `theme` ids,
`selectableGroups` ids and `customId`s are all local, and a remembered id is a dangling
reference that passes a shape check and renders nothing.

## What is safe to lift, and what breaks

[Copy flows & screens](https://adapty.io/docs/copy-flows.md) enumerates what breaks when a
screen crosses flows. Treat it as the authority — the same five categories break when you lift
a block by hand:

| Category | What happens |
| :--- | :--- |
| **Variables** | Text bindings, conditions and actions stop resolving. A `<customId>.value` or `<groupId>.selectedOptionId` means nothing in a flow with no such producer. |
| **Saved styles** | Elements lose their `colorId` / `font.preset` — those ids live in the destination's `theme`, which does not have them. |
| **Navigation actions** | `navigate` payloads lose their destination. A `scr_…` id from another flow is a dangling target and a publish blocker. |
| **Localizations** | Only locales both flows share keep their values. Everything else falls back to the destination's default locale. |
| **Products and custom fonts** | Same app keeps them; a different app breaks both. Product declarations are builder-owned regardless — see [`products.md`](products.md). |

So, concretely:

**Safe to lift** — element `type` and nesting, `layout` / `padding` / `margin` / sizing shapes,
`propsByState` structure, rich-text node structure, `interactions` structure, and the composite
skeletons below.

**Never lift** — `_meta.screens[].products[]` entries and any `flowProductId`; asset `id`/`url`
pairs; `colorId` / `font.preset` / `font.family.id` values; `navigate` target ids; any
`variableId` whose producer you are not also bringing.

**Rewrite on arrival** — every element `id`, and every `groupId` / `customId` that has to be
unique on its screen.

## Skeletons

Provenance: distilled from the front-format fixtures of Adapty's own builder transformer,
except for the tabs skeleton, which comes from a flow that rendered. They are **minimal by
design** — no `theme`, no `_meta`, no envelope — so treat them as shape, not as content. Fill in
sizing, fills and typography from the input flow's own conventions.

A fixture is weaker evidence than it looks. It proves only what its own test needed, so a prop
absent from one is not a prop the builder tolerates — that inference is what broke the tabs
render. Where a skeleton here disagrees with a flow you have seen render, the render wins.

### A toggle

There is no `toggle` *element* — the group type is what makes it one — but the member is a
**`selectable`**, and that part is not optional.

```json
"selectableGroups": [{"id": "notifications", "type": "toggle"}]
```
```json
{"id": "el_…", "type": "selectable",
 "props": {"groupId": "notifications", "default": true, "customId": "trip_updates",
           "layout": {…}},
 "states": [{"id": "selected", "type": "system"}],
 "propsByState": {"selected": {"fill": {…}}}}
```

> **This section previously said `type: "stack"`, and that does not work.** `IStackElementProps`
> has no `groupId` and no `default`, so a stack carrying them is not a group member: the props are
> ignored, it never receives the `selected` state, and **tapping it does nothing**. The failure is
> silent — the config saves, passes a schema check, and renders — and it was shipped to a user
> before anyone noticed the switch would not flip. `tests/verify-fixture.py` now fails on it.
>
> Verified against real exports, the member type is dictated by the group: `product` for a
> product group, `selectable` for `single_choice` / `multi_choice` / `toggle`, `tab-item` inside
> tabs. Nothing else is a member.

Swap `type` to `single_choice` for pick-one, `multi_choice` for pick-several. The element does
not change — only the group type and how many members carry `default`.

**Style both states, and remember you cannot check this in a preview.** An iOS-style switch needs
its track fill *and* its knob position to change, and `layout` is a prop like any other, so both go
in `propsByState`:

```json
"props":          {"layout": {"direction": "horizontal", "alignH": "start",  …}, "fill": [grey]},
"propsByState":   {"selected": {"layout": {"direction": "horizontal", "alignH": "end", …},
                                "fill": [accent]}}
```

Style only the track and you get a switch that never visibly flips. And `config preview` **ignores
toggle-group selection** — measured byte-identical renders with `default` true and false — so the
off state is all you will ever see there. Verify a toggle in the Adapty mobile app.

**A toggle cannot drive product selection by itself, and repeated toggling loses the selected
state.** Both from the support channel: the head-on binding "can't be done", and the standing
workaround is a **Conditional Action on the toggle's tap that re-asserts the selection** — if
toggle=true and selected=yearly → `Select product = yearly`, one case per plan. Wire it whenever a
toggle is supposed to switch plans, and note conditions of the form "if off → turn on" are
meaningless — just set the toggle on tap.

### Tabs

A five-element composite. Each `tab-item` is a group member.

**The group is `single_choice`, not `tabs`:**

```json
"selectableGroups": [{"id": "tabs", "type": "single_choice"}]
```

```
tabs                    props: {width, height, layout(+clipContent), position}
├── tab-bar             props: {fill, width, height, layout, padding, position, borderRadius}
│   ├── tab-item        props: {width, height, layout, default, groupId, padding,
│   │                           position, borderRadius}  + states + propsByState.selected
│   └── tab-item        same, default: false
└── tab-content-wrapper props: {width, height, position}
    ├── tab-content     props: {width, height, layout, position}
    └── tab-content     same
```

Every element carries `states` (`[]` is fine). The `tab-bar` children and the `tab-content`
children are positional: the *n*th item shows the *n*th content. Add or remove them in pairs, or
the mapping silently shifts.

**Verified by render**, not by diff: a three-tab paywall built from exactly these prop sets —
one product per tab — saved, round-tripped 108 of 108 elements intact, and displayed correctly
in the builder. Two earlier attempts did not: declaring the group `{"type": "tabs"}`, and
stripping these props down to `layout` alone, each produced a config the API accepted and the
builder could not open. See [flow-schema.md trap 10](flow-schema.md) for why the two wrong
answers looked well-sourced — and use `flows config preview` to check a skeleton you adapt from
here before you trust it, since that is how this one was confirmed.

**Two tab facts from the support channel:** if **no `tab-item` carries `default: true`, no tab
renders at all** — always mark one. And conditioning on the selected tab is possible despite the
UI exposing no tab-item id field (ADP-7611): use the tab element's **id from the builder URL** in
the condition — team-verified in preview, unconfirmed on device.

### A progress bar

Lives in `components`, not on a screen, and is switched on per screen.

```json
"components": {"pb_…": {
  "map": {
    "el_bar":  {"id": "el_bar",  "type": "progress-bar",
                "props": {"type": "single-segment", "template": "linear",
                          "oneSegmentPerScreen": false, "width": {…}, "height": {…}}},
    "el_seg":  {"id": "el_seg",  "type": "progress-bar-segment",
                "props": {"customId": "progress", …},
                "propsByState": {"current": {…}, "upcoming": {…}, "completed": {…}}},
    "el_load": {"id": "el_load", "type": "progress-bar-loader",
                "props": {"color": {…}, "fill": {…}, "duration": 320, "easing": "ease-in-out"}}},
  "hierarchy": {"id": "root", "children": [
    {"id": "el_bar", "children": [{"id": "el_seg", "children": [{"id": "el_load"}]}]}]}}}
```

Then, per screen: reference it in `hierarchy` as `{"id": "pb_…", "type": "global"}`, and set
`props.progressBar: {"enabled": true, "segment": "progress"}` — `segment` matches the
`progress-bar-segment`'s `customId`. Screens that should not show it set `{"enabled": false}`.

`template` is `linear` or `segmented`; `type` is `single-segment` or `multiple-segments`; pair
`segmented` + `multiple-segments` + `oneSegmentPerScreen: true` for one dot per screen.

### A countdown

**The invisible Countdown is the flow's only delay primitive.** A Spinner has no completion
trigger, and `On Screen Appear → Navigate Next` fires instantly — so a timed screen is a Countdown
with `Opacity 0`, `Position Absolute`, top/left 0, and `On Timer End → Navigate Next`
(team-recipe). And when a loader must be pinned, the `fixed` position goes on a **container**, not
on the Loader element itself. Details of the visible countdown below.

```json
{"id": "el_…", "type": "timer",
 "props": {"customId": "offer", "behavior": "start_at_every_appear",
           "duration": {"days": 0, "hours": 0, "minutes": 15, "seconds": 0}, …}}
```

with a child `text` whose rich text carries `token` nodes:

```json
{"type": "paragraph", "content": [
  {"type": "token", "attrs": {"token": "timer_minutes"}},
  {"text": ":", "type": "text", "attrs": {"bold": false, "italic": false,
                                          "underline": false, "strikethrough": false}},
  {"type": "token", "attrs": {"token": "timer_seconds"}}]}
```

### A carousel — fixed geometry or nothing

Support-channel distilled (2026-08, team-stated and device-verified). The carousel supports exactly
**two layouts**: adjacent-slide peek (the standard Apple layout), or one full slide with neighbours
invisible. Anything else is an SDK limitation, not a config error, and a true infinite loop is
impossible — the approximation is duplicating slides (ADP-7615).

**`hug` does not survive the trip to the device here.** `Slide Width = Hug` is dropped by the
transformer (Android stretches the slide full-width, the peek disappears, ADP-6653), and a hugged
footer under a carousel collapses to zero when Android measures a flat+scrollable layout. The
working recipe is all-fixed geometry — the team's own verified numbers for a centered 3-card
layout: card width **245**, carousel **402**, symmetric padding **66.5**, gap **12**, footer
heights fixed; the CTA may stay `Fill`. Swipe and autoplay survive. Two more from the same
threads: the slide's configured size and its hugged content are independent (a 200 slide over 148
content is a 52px gap you did not author), and slides have no auto-height — fix the carousel height
to the tallest slide or cut the copy.

### Layout discipline the support channel keeps re-learning

- **Mixed sizing modes across siblings is the root cause of "randomly exploding" screens** — the
  team's own fix for one was "images to fixed, everything else to fill-hug", nothing more.
- **Containers only grow downward in relative layout.** For expanding content, pre-size the
  container for the expanded state and toggle `visibility` — "less pretty, but no jumping".
- **Fixed widths overflow the right edge on narrow iOS screens (≤375pt, ADP-7117)** — any fixed
  number needs an SE / 13-mini sanity check, and the builder previews only 402×874 (no Pro Max
  preset either, so `Fill` heights absorb 82 extra points on a 440×956 device).
- **After restructuring a screen, hunt for orphaned fixed buttons**: two stacked CTAs render as
  one, and the SDK taps the topmost — a footer added late left an old Continue underneath it,
  team-diagnosed.
- **Prefer a pinned container over the native `footer` element**: with `Scrollable = off` a Footer
  never reaches the device at all, and Android computes its height separately, leaving a void.
  A bottom-docked stack (this file, below) has neither behaviour.

### A tappable button

There is no `button` element — see the request map in
[`flow-schema.md`](flow-schema.md#vocabulary).

```json
{"id": "el_…", "type": "stack", "props": {…}, "caption": "Button",
 "interactions": [{"id": "int_…", "trigger": "tap",
                   "actions": [{"id": "act_…", "type": "navigate",
                                "payload": {"type": "screen", "screen": "scr_…"}}]}]}
```

Actions nested inside a `conditional` case carry `"id": ""` instead of an `act_…` id.

## One caution about version skew

These shapes come from fixtures whose `schemaVersion` is absent, `2`, `6` or `8.0`, while a
current export carries `9`. The element and group vocabulary matches, which is why they are
here — but do not import a fixture's envelope, and do not change the input's `schemaVersion`
to match one. Carry the input's own value through untouched.

### Putting a footer at the bottom: prefer the screen's own distribution

Before reaching for the docked pattern below, check whether the screen just wants
`space-between`. Give the screen root exactly two children — a content stack and a footer stack
(CTA, legal row, footnote) — and set:

```json
"props": {"scrollable": false,
          "layout": {"direction": "vertical", "alignH": "center", "alignV": "start",
                     "distribution": {"type": "space-between"}}}
```

The free space lands between the two, so the footer is at the bottom with **no** `fixed`
positioning, no `padding.bottom` reservation, and no arithmetic to get wrong. Measured across
four screens (2026-08-24) this removed both of the failure modes the alternatives carry: a
footnote that had slid under a docked CTA, and the dead void an in-flow footer leaves on a tall
device. `flowkit.screen(..., distribution='space-between', scrollable=False)`.

**Choose per screen, because the cost is real:** a spread mode needs a definite-height container,
so it wants `scrollable: false`, and that **clips** content taller than the viewport. Short
screens spread; tall screens stay `scrollable: true` (where a spread is inert and the footer
simply follows the content) or use the docked pattern below. See
[flow-schema.md trap 10b](flow-schema.md) for the vocabulary and
[preview.md](preview.md) for why you cannot check the clipping locally.

Docking is still right when content must scroll **under** a CTA that stays put — a long paywall,
a scrolling comparison table.

### A bottom-docked button

`fixed` with `left`/`right`/`bottom` plus `width: auto` is the docked-CTA pattern (trap 9).

```json
{"id": "el_…", "type": "stack", "caption": "Button",
 "props": {"position": {"left": 24, "type": "fixed", "right": 24, "bottom": 24},
           "width": {"type": "auto"}, "height": {"type": "fixed", "value": 56}, …},
 "interactions": [{"id": "int_…", "trigger": "tap", "actions": [ … ]}]}
```

**One historical device defect to know before blaming your config:** `fixed` + `left`/`right` +
`width: auto` once collapsed to content width on device while the preview showed full width
(ADP-6828); the era workaround was a sandwich — outer Stack `fixed`/`auto` with no states, inner
CTA `relative`/`fill` carrying the states and actions. A 2026-08-22 device screenshot from this
project shows the plain form rendering full-width, so treat it as fixed — but if a docked CTA comes
back narrow on a device, this is what it is, and the sandwich is the fallback.

**The `fixed` element must be the button itself and carry the interaction.** Wrapping buttons in
a fixed *container* and putting the interactions on relative children leaves the pinned element
actionless — it still renders and still taps in preview, but in the builder's layer tree you select
the docked bar, see no action on it, and reasonably conclude the buttons have no navigation. That
is how this pattern was first built here, and it is what a reviewer noticed.

For two docked items, give each its own `fixed` element and stack the offsets bottom-up —
`bottom: 24` for the lowest, `bottom: 24 + height + gap` for the next. One fixture screen carries
two non-relative elements, so this has precedent; a fixed container does not.

The one honest exception is a row of several small links (Restore · Terms · Privacy): the row is a
fixed container because each link is separately tappable and carries its own action.

### A connected timeline, where a rail must reach the next chip

A vertical timeline is rows of `[track, text]`, where the track is a column holding a circular
chip and, beneath it, a connector rail. Getting the rail to *touch* the next chip is the whole
difficulty, and the mechanism is arithmetic rather than styling.

The row is `hug`, so its height is `max(chip + rail, text)`. When `chip + rail` wins, the rail's
bottom edge lands exactly on the next chip's top edge and the column is continuous **by
construction**. When the text wins, the row grows, the rail does not, and a gap opens. So:

**Size the rail so `chip + rail` exceeds the tallest text you expect, and let the rail set the row
pitch.** Measured on a three-row timeline: at a snug rail the column was continuous, and growing a
single description from two lines to four reopened a **49px** gap. The same timeline with a longer
rail stayed continuous under both the original and the grown copy. Copy grows for reasons outside
your control — a rewrite, or a locale, since translations run longer than their source — so pick the
generous number, not the one that just barely fits today.

Two things that look like the fix and are not:

- **`position: absolute` plus `zIndex`, to overlap the rail under the next chip.** `zIndex` is real
  (it lives inside `position`, not at the top level of props) and it *is* honoured — inverting it
  moved the rail above the chips. But `absolute` pulls the rail out of flow, so the row collapses to
  text height and the rail stops setting the pitch: measured, a **61px** break plus rails painted
  over the icons. A z-order tool cannot fix a layout-flow problem. Note also that `zIndex` appears in
  **no** real export and **no** catalog template, so it sits at the bottom of the evidence order.
- **`height: {type: "fill"}` on the rail**, to stretch it to whatever the row needs. It collapses
  inside a hug-height parent — see trap 13 in `flow-schema.md`.

Derive the number from the reference if you have one: measure its chip-to-chip pitch in pixels,
divide by (image width ÷ device points), and subtract the chip. On the paywall this was built
against, 190px and 142px at 1.544x gave pitches of 123pt and 92pt, so rails of ~77 and ~46.

Verify by measurement, never by eye: walk the painted runs down the track column and assert **zero
gaps**. A rail that stops one pixel short looks like a design choice in a screenshot.

### A selectable plan card

The commonest paywall shape there is, and the one most likely to be rebuilt from scratch. Radio
and product-card shapes below are lifted from `tests/fixtures/onboarding-quiz-paywall.json` (a real
export); the assembly is **verified by render**.

Three parts have to agree, and the group id is what ties them together:

```json
"selectableGroups": [{"id": "plans", "type": "product"}]
```

The card itself is a **`product` element**, not a stack — that is what makes it selectable and what
a product attaches to. Exactly one card in the group carries `"default": true`:

```json
{ "id": "el_Plan1", "type": "product", "caption": "Plan Individual",
  "props": {
    "width": {"type": "fill"}, "height": {"type": "hug"},
    "layout": {"direction": "horizontal", "alignH": "start", "alignV": "center",
               "distribution": {"type": "gap", "gap": 14}},
    "padding": {"top": 14, "left": 16, "right": 16, "bottom": 14},
    "borderRadius": {"tl": 16, "tr": 16, "bl": 16, "br": 16},
    "position": {"type": "relative"},
    "groupId": "plans", "default": true,
    "product": {"id": "<product-uuid from `adapty products list`>"} },
  "states": [{"id": "selected", "type": "system"}],
  "propsByState": {"selected": {"border": {"color": {"type": "color-style", "colorId": "ink"},
                                           "style": "solid", "width": 1}}} }
```

**Put the selected LOOK in `propsByState`, never on whichever card starts selected.** `default:
true` sets the initial *selection*, not the styling. Give every card the same neutral border and let
`propsByState.selected` recolour it — bake an accent border onto the default card instead and it
stays there forever while only the indicator moves, which reads as "selection is broken on every
other card". Measured on a shipped flow, from a build that had the skeleton above in front of it.

The radio indicator is **two nested stacks, and the inner one has no fill at all** until selected.
Getting this wrong is what makes every card look selected at once:

```json
{ "id": "el_Ring", "type": "stack", "caption": "Radiobutton",
  "props": {"width": {"type": "fixed", "value": 24}, "height": {"type": "fixed", "value": 24},
            "borderRadius": {"tl": 9999, "tr": 9999, "bl": 9999, "br": 9999},
            "fill": [{"type": "color", "color": {"type": "color-style", "colorId": "white"}}],
            "border": {"color": {"type": "color-style", "colorId": "gray-200"},
                       "style": "solid", "width": 1},
            "layout": {"direction": "horizontal", "alignH": "center", "alignV": "center",
                       "distribution": {"type": "gap", "gap": 0}},
            "position": {"type": "relative"}},
  "states": [],
  "propsByState": {"selected": {"border": {"color": {"type": "color-style", "colorId": "gray-800"},
                                           "style": "solid", "width": 1}}} }
```

with a dot inside it — note **no `fill` key in `props`**, only in `propsByState`:

```json
{ "id": "el_Dot", "type": "stack", "caption": "Dot",
  "props": {"width": {"type": "fixed", "value": 8}, "height": {"type": "fixed", "value": 8},
            "borderRadius": {"tl": 9999, "tr": 9999, "bl": 9999, "br": 9999},
            "position": {"type": "relative"}},
  "states": [],
  "propsByState": {"selected": {"fill": {"type": "color",
                                         "color": {"type": "color-style", "colorId": "gray-800"}}}} }
```

`states: []` on both is correct — the `selected` state is contributed by the enclosing `product`
element, and the indicator only supplies the styling for it.

The confirm button buys **the group's selection**, never a hardcoded product:

```json
"interactions": [{"id": "int_buy", "trigger": "tap", "actions": [
  {"id": "act_buy", "type": "purchase",
   "payload": {"product": {"type": "var", "variableId": "plans.selectedProduct"}}}]}]
```

**A price is a rich-text `variable` node in the copy — never literal text.** Literal text is a
number you made up or one that has gone stale; the variable resolves against the store. A
product-relative head must name a product declared in `_meta.screens[].products[]`, so on a card you
authored, **write that declaration yourself in the same update** —
[products.md → Declare the products yourself](products.md) owns the rules, including the one that
matters most: never do it when rewriting a flow, where the live declaration is carried forward.
Skip the declaration and the variable is what breaks: device preview returns 422, publish reports
*Unknown Product Id*.

**The preview renders the token, not a price**, at ~45 characters — long enough to wrap and shove
copy under a docked CTA. Judge the layout on a throwaway copy with plausible prices substituted
(`SKILL.md` phase 4), and never let those substituted numbers reach the config you write.

An earlier version of this section said the opposite — write prices as plain text and let the user
swap them for variables later. That was the rule before a config could carry its own declaration,
and it is retired: it makes an authored paywall ship a fabricated price, which is worse than any
layout defect because the user cannot see that it is wrong. Same distinction as
[`old-price`](flow-schema.md): check whether a claim is about the *element* or about *what only the
builder can write*.

**A `propsByState` entry may restyle an element; it must never resize one.** Colour, fill, opacity,
border *colour* are free. A **border `width`** that differs between base and `selected` changes the
card's outer size, and in a `width: fill` column every sibling re-measures with it — a real build
with base `1` / selected `2` made the comparison table above the cards **grow on every tap**, and
holding the width at `1` while changing only the colour fixed it (user-confirmed on device; the
same delta was also on the radio rings). If a selected card needs more presence than a colour
gives it, change its `fill`, not its geometry. Note also what caught this: **nothing did.** The
config validated, the structural checks passed, and two renders with different `default` cards were
byte-identical — a selected-state reflow needs a *tap*, which no check in this skill performs. Treat
any state that touches `border.width`, `width`, `height`, `padding` or `margin` as a defect on
sight, because you cannot see it.

**A tick badge is not a radio dot, and the difference bites.** The dot above works because when
unselected it has *nothing to draw* — no fill, no children. A tick badge has a **glyph child**, and
that glyph paints whether or not the badge is selected: styling only the circle via `propsByState`
leaves a ghost tick sitting on every unselected card. Hide the container instead, and give the row
holding it a fixed height so the cards do not change size:

```json
{ "id": "el_Tick", "type": "stack", "caption": "Tick",
  "props": {"width": {"type": "fixed", "value": 26}, "height": {"type": "fixed", "value": 26},
            "borderRadius": {"tl": 9999, "tr": 9999, "bl": 9999, "br": 9999},
            "visibility": {"type": "hidden"},
            "layout": {"direction": "horizontal", "alignH": "center", "alignV": "center",
                       "distribution": {"type": "gap", "gap": 0}},
            "position": {"type": "relative"}},
  "states": [],
  "propsByState": {"selected": {"visibility": {"type": "visible"},
                                "fill": [{"type": "color",
                                          "color": {"type": "color-style", "colorId": "accent"}}]}} }
```

The rule generalises: **`propsByState` restyles an element, it does not suppress what is inside
it.** Anything with children needs `visibility` — and hiding collapses the layout, so reserve the
space deliberately (trap 14 in [flow-schema.md](flow-schema.md)).

### A single-plan screen: hide the product element, buy with `const`

One product means there is nothing to pick, and a lone `product` card is worse than no card: it
carries a permanent `selected` look the user cannot change, so the styling says "choice" while the
screen offers none.

The shape that avoids it uses each mechanism for the one thing it is for:

```json
{ "id": "el_attachPoint", "type": "product", "caption": "Product attach point (hidden)",
  "props": {"width": {"type": "hug"}, "height": {"type": "fixed", "value": 0},
            "visibility": {"type": "hidden"},
            "groupId": "plans", "default": true,
            "product": {"id": "<product-uuid>"}, "layout": {…}, "position": {"type": "relative"}},
  "states": [{"id": "selected", "type": "system"}] }
```
```json
"interactions": [{"id": "int_buy", "trigger": "tap", "actions": [
  {"id": "act_buy", "type": "purchase",
   "payload": {"product": {"type": "const", "value": {"id": "<product-uuid>"}}}}]}]
```

- The **hidden `product` element is the attach point**, and it exists for one reason: a price
  variable resolves only against a declared product, and only a `product` element can be
  attached to. Hidden costs nothing — hiding collapses the space (trap 14) — and the price then
  lives in ordinary copy anywhere on the screen.
- The **CTA buys with `const`**, which names the product directly and needs no group and no
  selection. Both facts, with their evidence, are
  [products.md → a price variable REQUIRES a `product` element](products.md) and
  [→ a purchase can bind a product with no `product` element](products.md).
- Keep the `selectableGroups` entry and the element's `groupId` in agreement even though nothing
  reads the selection — the invariant is bidirectional and a stray `groupId` fails verify.

**Verified by render**, and it is what a reviewer asked for over a visible single card. What is
*not* yet verified: whether the builder declares a product on a **hidden** element when it saves.
Provisional declaration via `flowkit.predeclare()` covers device preview meanwhile, so check the
live `_meta.screens` after the flow has been saved in the builder once before relying on it.

### Plans in a `bottom-sheet`

The sell lives on the screen, the picker lives in a sheet the CTA opens. `bottom-sheet` is a real
element type with no catalog template, no fixture and no export in this corpus — the shape below is
schema-derived (`IBottomSheetElement`) and **confirmed by render**, which is the weakest tier this
file admits, so treat it as a starting point and look at your own screenshot.

The sheet is a docked, initially hidden container with its own scrim:

```json
{ "id": "el_planSheet", "type": "bottom-sheet", "caption": "Plan sheet",
  "props": {"position": {"type": "fixed", "bottom": 0, "left": 0, "right": 0},
            "width": {"type": "auto"}, "height": {"type": "hug"},
            "borderRadius": {"tl": 26, "tr": 26, "bl": 0, "br": 0},
            "visibility": {"type": "hidden"},
            "overlayColor": {"type": "hex", "hex": "#000000", "opacity": 60},
            "fill": [ … ], "layout": { … }, "padding": { … }},
  "states": [] }
```

`overlayColor` is the giveaway that this is a modal rather than a panel — it dims the page behind,
and it is a `bottom-sheet` prop that a `stack` does not have. Opacity is a **percentage** (trap 11).

Open and close with `showElement` / `hideElement`, whose payload is a **list of element ids**:

```json
{"id": "act_open", "type": "showElement", "payload": {"elements": ["el_planSheet"]}}
```

**The trap: a docked element of the screen paints OVER the sheet.** The page's own bottom-docked
CTA and legal row kept rendering on top of an open sheet, burying the sheet's purchase button under
the button that had just opened it — measured on the first render of this pattern. A sheet is not a
layer above everything; it is a sibling. So the opening interaction carries **two** actions, and the
dismiss carries their inverse:

```json
"actions": [{"id": "act_open",      "type": "showElement", "payload": {"elements": ["el_planSheet"]}},
            {"id": "act_hide_page", "type": "hideElement", "payload": {"elements": ["el_openCta", "el_legalRow"]}}]
```

Two more things that follow from the sheet being an ordinary part of the document:

- **The product group spans both.** The `product` elements live inside the sheet while
  `selectableGroups` is declared on the screen, and the sheet's CTA buys
  `<groupId>.selectedProduct` exactly as a flat paywall would. Nothing about the group is
  sheet-aware.
- **The render draws whatever `visibility` says and never runs the interaction.** So screenshot it
  twice — once as authored (sheet hidden) and once from a throwaway copy with the sheet visible and
  the page furniture hidden, which is the state the actions produce. That verifies both layouts and
  proves nothing about the tap: whether `showElement` actually fires is an Adapty-app check.

### A side-by-side docked footer

Two buttons on one row at the bottom, each with its own action. The trap is treating it as one
fixed container holding two relative children: the container swallows the taps (same failure as
[a bottom-docked button](#a-bottom-docked-button)). Each button is **its own `fixed` element**,
one anchored left and one right, and their widths have to add up:

```json
"props": {"position": {"type": "fixed", "left": 11, "bottom": 18},
          "width": {"type": "fixed", "value": 170}, "height": {"type": "fixed", "value": 50}}
```
```json
"props": {"position": {"type": "fixed", "right": 11, "bottom": 18},
          "width": {"type": "fixed", "value": 182}, "height": {"type": "fixed", "value": 50}}
```

Never set `left` **and** `right` on either one — that stretches it to full width and the two
overlap. Budget the row explicitly: `left + w1 + gap + w2 + right` should equal the device width
(here `11 + 170 + 17 + 182 + 11 = 391` on a 390pt phone). And leave the screen enough
`padding.bottom` to clear the whole bar, or the docked row lands on top of the last content —
measure it rather than assuming, with
[`tests/render-measure.py`](../../../tests/render-measure.py).

### A back button, and authoring an icon that does not exist yet

`navigateBack` needs no target — it pops the stack:

```json
{"id": "el_…", "type": "stack", "caption": "Back",
 "props": {"width": {"type":"fixed","value":40}, "height": {"type":"fixed","value":40}, …},
 "interactions": [{"id":"int_…","trigger":"tap","actions":[{"id":"act_…","type":"navigateBack"}]}]}
```

There is no `header` shortcut for this: `header` and `footer` are plain containers with a stack's
props and no built-in navigation.

**If the arrow glyph is not in `_meta.icons`, you have three options in this order.** A text
affordance ("Back", "Not now") always works and needs nothing. Copying an icon from another flow in
the same account is safe — `_meta.icons` entries are inline SVG in the document, not uploaded
assets, unlike the `id`/`url` pairs in the do-not-lift list above. Authoring one is the last resort
and **only acceptable because you can render it**: the format is visible in any existing entry
(`viewBox="0 0 256 256"`, `fill="currentColor"`, one filled path, `{name, raw, weight}` all
required), so write it, render the screen, and *look at the glyph*. An ArrowLeft authored this way
was confirmed correct by render before being kept. **Mirror a real entry's markup exactly, and use
a phosphor-style name** — measured 2026-08-24: three authored icons with invented lowercase names
(`mf-lock`) and no `width`/`height` attributes on the `<svg>` tag rendered as *blank* in
`config preview` (empty chips, no error anywhere); the same paths drew once the entries copied a
real export's shape — `width="20" height="20" fill="currentColor"` on the tag and phosphor-cased
names (`LockSimple`, `Bell`). Which change fixed it is unisolated (both were made together), and
whether the preview drew the `raw` or a bundled phosphor glyph of that name is ambiguous — the
device SDK reads `raw`, so keep the authored path visually equivalent to the phosphor glyph the
name says it is. Never keep an authored icon you have not seen
drawn — that is the difference between this and inventing a product id, which no render can check.


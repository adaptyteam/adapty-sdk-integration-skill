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

There is no `toggle` element. The group type is what makes it one.

```json
"selectableGroups": [{"id": "notifications", "type": "toggle"}]
```
```json
{"id": "el_…", "type": "stack",
 "props": {"groupId": "notifications", "default": true, "layout": {…}},
 "states": [{"id": "selected", "type": "system"}],
 "propsByState": {"selected": {"fill": {…}}}}
```

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

### A bottom-docked button

`fixed` with `left`/`right`/`bottom` plus `width: auto` is the docked-CTA pattern (trap 9).

```json
{"id": "el_…", "type": "stack", "caption": "Button",
 "props": {"position": {"left": 24, "type": "fixed", "right": 24, "bottom": 24},
           "width": {"type": "auto"}, "height": {"type": "fixed", "value": 56}, …},
 "interactions": [{"id": "int_…", "trigger": "tap", "actions": [ … ]}]}
```

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

**Write the prices as plain text, not price variables.** A price variable resolves only against a
screen's declared products in `_meta.screens[].products[]`, that declaration carries a
`flowProductId` which cannot be synthesized, and **only the Flow Builder writes it** — so on a card
you authored, a variable renders as the literal `{{uuid.prod_price}}` and fails publish with
*Unknown Product Id*. Put the price in the copy, and tell the user to attach the products in the
builder and swap the text for variables if they want them live. See
[products.md](products.md) — this is the same constraint from the other direction.

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
was confirmed correct by render before being kept. Never keep an authored icon you have not seen
drawn — that is the difference between this and inventing a product id, which no render can check.


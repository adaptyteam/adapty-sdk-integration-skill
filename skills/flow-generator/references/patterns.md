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


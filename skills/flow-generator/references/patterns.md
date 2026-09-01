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
> before anyone noticed the switch would not flip. `references/verify-config.py` now fails on it.
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

Lives in `components`, not on a screen, and is switched on per screen. **It is a real element,
not a drawing** — never fake it with a static filled `stack` (a partial bar) or a hand-built row of
step `stack`s. A lookalike renders in the preview but **does not advance** across screens and is not
wired to `props.progressBar`, so it silently ships a dead indicator — the same mistake as the
[fake carousel](#a-carousel--the-real-carousel-element-never-a-static-card-with-dots) and the fake
footer. If step dots are what the design shows, that is still this component (segmented template),
not a row of dot stacks. `verify-config.py` warns on the dot-row shape.

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

**A `spinner`'s `duration` is its ROTATION PERIOD, not a completion time.** It loops forever and
fires nothing, on every surface. The field reads exactly like a delay — a user looking at
`duration: 1000` reasonably asked why the screen never advanced after a second — so when a
spinner and a Countdown share a screen, say in the handoff which one moves the flow.

### A loading screen — fill the `loader-spinner-label` template; never fake the spinner

"A loading screen with a spinner and a label" has a **ready catalog component**,
`loader-spinner-label` (`agent_allowed`) — fill its slots rather than assembling one by hand; the
template's internal wiring is already correct. The primitives underneath it, and the two facts about
the spinner that are not guessable:

- **`spinner`** — a rotating icon. Its `props.icon.type` **must be `"custom"`**, not `"phosphor"`:
  the publish gate rejects a phosphor spinner with a 422 (`Spinner element only supports custom
  icons`). Point the custom icon at a `_meta.icons` entry you authored.
- **`loader`** — a determinate progress bar (`duration`, `easing`), when the affordance is a bar
  rather than a spinner.
- the invisible auto-advance **`timer`** below — that is what actually moves the flow on; the
  spinner is decoration and has no completion trigger.

**A blank where the spinner should be is a preview blindness, not a broken element** — the same
class as a toggle's `selected` state, and measured on the same day; the finding lives with the rest
of the list in [preview.md → What a render cannot show you](preview.md#what-a-render-cannot-show-you).
Verify the spinner on a device, and never judge it by the screenshot.

**Never swap the spinner for a static `icon` to make the preview look complete.** A ring `icon`
renders in the preview and reads as a spinner in a screenshot, but it does **not animate** on device
and it is not the `spinner` element — you would ship a lookalike that no longer does the job. This is
the [fake-footer](#a-bar-that-stays-at-the-bottom-use-footer) mistake wearing a loader: a
preview-visible impostor standing in for a real element to satisfy a screenshot. Keep the
`spinner` / `loader-spinner-label`, disclose that the preview cannot show it, and hand the animation
to the device check. `verify-config.py` cannot see this, so it is on you.

### DEVICE-VERIFIED: the JSON an auto-advancing screen actually needs

The recipe above is written in the builder's vocabulary, and translating it to JSON left three
gaps that together produced a screen that spun forever on a real device while `validate` returned
`valid: true`. This is the shape that **worked on a real device** (2026-08-25) — the project's
first confirmed `timer-end`, since no export in the corpus carries one:

```json
{"id": "el_delay", "type": "timer", "states": [], "caption": "Delay",
 "props": {"customId": "build_delay", "behavior": "start_at_every_appear",
           "duration": {"days": 0, "hours": 0, "minutes": 0, "seconds": 3},
           "width": {"type": "hug"}, "height": {"type": "hug"},
           "padding": {"top": 12, "left": 16, "right": 16, "bottom": 12},
           "visibility": {"type": "visible"},
           "position": {"type": "absolute", "top": 0, "left": 0}},
 "interactions": [{"id": "int_delay", "trigger": "timer-end",
                   "actions": [{"id": "act_after_delay", "type": "navigate",
                                "payload": {"type": "screen", "screen": "scr_next"}}]}]}
```

> **CORRECTED 2026-09-01 — the block above is incomplete, and the missing part is the one that
> makes it work. `el_delay` MUST HAVE AT LEAST ONE CHILD.** A childless timer does **not** fire
> `timer-end` on a device: the flow reaches the screen and stops there for good. Measured over
> three device trips — a real onboarding stuck on its loader; the identical config with one child
> `text` added advancing; and an isolating probe whose two exits led to *different* destinations
> reporting the manual route, never the timer's. The mechanism is the one the fifth bullet below
> already half-stated and then waved away: an element with nothing to lay out is one the renderer
> skips, and a timer is not exempt.
>
> **Why the original verification missed it, and this is the transferable half: that session had
> added visible countdown digits to diagnose the failure, then wrote the shape down without
> them.** The instrumentation *was* the fix, and it was removed from the record as noise. If you
> add instrumentation to make a remote failure observable, the shape you verified is the
> instrumented one — strip it and re-verify, or document it as required. See CLAUDE.md finding 29.
>
> `flowkit.timer()` now raises on the pair and `verify-config.py` errors on it, because no other
> gate can see it: `validate` returns `valid: true` for both forms and `config preview` never
> navigates for any reason, so the working and the dead timer produce the identical local
> observation.

Four things about it, and **which one was decisive is unisolated** — they were fixed together
before the device test, so treat the whole shape as the unit that works:

- **It is a direct child of the screen `root`, not nested in a content stack.** `absolute`
  offsets resolve against the **parent** (trap 9), so nesting it made `top/left: 0` mean the
  stack, which is not what "Position Absolute, top/left 0" describes.
- **`hug` + `padding`, never a `fixed` 1×1 box.** A 1×1 timer is a degenerate size and trap 15
  is explicit that the transformer believes those. The one real export's timer is `hug` *with*
  padding, so it has a genuine box; copy that.
- **No `opacity: 0`.** The recipe's opacity exists to hide a countdown showing **digits**, and
  a zero-opacity element is one a renderer may legitimately skip. **Superseded in its second
  half:** this bullet went on to say a timer with no child draws nothing "anyway", which read as
  a licence to ship one childless. It is not — see the correction above. The surviving rule is
  narrower: do not set `opacity: 0`, *and* give the timer a child. If the countdown should not be
  seen, the child is the loading copy the screen was going to show regardless.
- **An explicit `navigate`, not `navigateNext`.** The recipe says "Navigate Next" because that is
  the builder's dropdown; in JSON an implicit next-in-order target silently re-routes if anyone
  reorders the screens, and it also makes the graph invisible to the reachability check —
  `references/verify-config.py` reported five screens unreachable the moment `navigateNext` went in,
  which is the checker doing its job, not a false positive to suppress.

**Not agent-tested.** The facts above are device-measured, but whether an agent handed "add a
3-second loading screen" produces this shape rather than the 1×1 nested (or childless) form has
had no baseline round — per the Iron Law in `superpowers:writing-skills`, treat that as open.

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

**The token id carries a `timer_` PREFIX — this is not optional and it is the one place two of
this skill's references used to disagree.** The four ids are `timer_days`, `timer_hours`,
`timer_minutes`, `timer_seconds`. The bare names (`hours`, `minutes`, `seconds`) **do not
resolve**: `config validate` accepts them, but the Flow Builder paints them red `Unknown` and the
device/preview renders the literal `%hours%:%minutes%:%seconds%`. Confirmed 2026-08-25 by pushing
both forms to a real flow and reloading the builder — the prefixed ids render a live `23:59:59`
chip, the bare ones stay `Unknown`. **`component-catalog.json`'s four timer templates
(`timer-badge`, `timer-inline`, `timer-blocks`, `timer-inline-units`) shipped the bare names until
2026-08-25** — filling one of their slots is exactly how a broken timer gets authored, so if you
lift a timer from a template, prefix the tokens. `flowkit.timer()` + `flowkit.timer_digits()` emit
the correct ids, and `verify-config.py` now warns on any un-prefixed `token`.

### A carousel — the real `carousel` element, never a static card with dots

A row of testimonials with a peek, or **any set of swipeable cards with indicator dots**, is the
`carousel` **element** — not a stack you dress up to look like one. This is the shape most often
faked, because a static card renders in the preview and a screenshot of it looks finished. It is
not: on the device it shows **one frozen slide**, it does not swipe, and the dots do nothing. That
is the [fake-footer](#a-bar-that-stays-at-the-bottom-use-footer) /
[fake-spinner](#a-loading-screen--fill-the-loader-spinner-label-template-never-fake-the-spinner)
mistake wearing a slider, and **no local gate but `verify-config.py` sees it** — it **errors** on
a hand-built indicator row with no `carousel` on the screen, and the row is recognised in every
form it has been seen in: round dot `stack`s, a wider *pill* for the active one, small phosphor
`Circle`/`DotOutline` icons, and a lone text node of bullet glyphs. With no dots at all to key on
it still warns on the other half of the fake — a horizontal row of equal fixed-width cards wider
than the viewport, which is the peek layout hand-built as a static row. The request map in
[flow-schema.md](flow-schema.md#from-what-the-user-asks-for-to-what-the-json-calls-it) routes the
request here for the same reason the video row exists.

**Start from the catalog: `reviews-carousel` is a filled template** — a real `carousel` with
`props.dots` already set and three review slides to overwrite. Its slots are
`review_N_{title,text,author}`. Reach for it before assembling anything, for the reason the
`loader-spinner-label` row gives: the template's internal wiring is already correct. It exists
because the catalog previously offered `ue-review` — **one static card** — and nothing else, so
"add reviews" led straight to a single frozen slide with dots added by hand.

**And the seed flow usually already has one.** A `carousel`
lifts cleanly (element `type` + nesting are safe, [What is safe to lift](#what-is-safe-to-lift-and-what-breaks));
copy the element and its slide subtrees, swap the copy, keep the shape. A real reviews carousel from
one export, for reference:

```json
{"id": "el_…", "type": "carousel", "caption": "Reviews",
 "props": {"gap": 12, "width": {"type": "fill"},
           "height": {"type": "fixed", "value": 120},
           "slideWidth": {"type": "fixed", "value": 340},
           "slideHeight": {"type": "fixed", "value": 120},
           "dots": {"gap": 6, "size": 6,
                    "color":       {"type": "hex", "hex": "#FFFFFF", "opacity": 30},
                    "activeColor": {"type": "hex", "hex": "#FFFFFF", "opacity": 95}}}}
```

**`height` is the whole box, dots included, and the next element starts immediately after it**
— measured 2026-08-28 by rendering one template at two heights and scanning the column through
the dot row: at `height == slideHeight` the 6px dot band occupies y 324-329 with the following
element at y 330, and at `slideHeight + 30` it sits at 354-359 with the next element at 360. The
band is always the last few pixels of the box, so **the dots collide with whatever follows**
unless you leave room: at `height == slideHeight` the measured clearance to the next element is
**0px**, and against a CTA the dots merge into the button's top edge. Real exports and
`tests/fixtures/reviews-carousel.json` set the two equal — which is fine only because nothing
follows the carousel on those screens, so do not read them as the recipe. The working shape,
measured, is `height = slideHeight + ~28` for the dot band plus `margin.bottom` for clearance
(12px measured); `reviews-carousel` in the catalog ships exactly that. Note that `height` is the
one number a longer translation cannot fix, since slides have no auto-height.

Its `hierarchy` children are **one node per slide** (each a `stack` holding the avatar, name, stars
and body). **The dots come from `props.dots` — do not add your own dot `stack`s**; that is exactly
the fake this section exists to stop.

**Authoring one: `flowkit.carousel(slides, slide_w=…, slide_h=…)`.** It emits exactly the shape
above and enforces the three things that turn a carousel back into the fake: fewer than two slides
raises (that *is* the frozen slide), a dot-like `stack` passed as a slide raises (the dots are the
element's own), and the slide geometry is a required number because a `hug` slide is dropped on
device. All four of `color`, `activeColor`, `size` and `gap` are **required** by the schema's
`IDots`, so the helper always writes them together — a partial `dots` object fails the schema
check. Prefer a **theme colour id** for the dots (`dot_color='muted'`): `IDots.color` is an
`IColor`, so it accepts a `color-style`, and the hardcoded white above is invisible on a light
screen. `tests/fixtures/reviews-carousel.json` is a rendered example — the dots draw, and the file
contains no dot `stack` at all.

Now the SDK limitations, which shape the *geometry* of a real carousel — not whether to use one.
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
- **`Scrollable = off` + `footer` = no footer on the device. CONFIRMED 2026-08-26, not a dated
  report** — it is a hard constraint and it is
  [rule 0](#a-bar-that-stays-at-the-bottom-use-footer). The channel reported it, a preview
  measurement appeared to contradict it, and the device settled it: the preview draws the footer
  in both scroll modes, so believing the render is what made this look retired.
- **The Android height/void report is HISTORICAL — device-tested 2026-08-26 and it did not
  reproduce** (channel, to 2026-08-22: Android computed the footer's height separately, leaving a
  void). Retired against a **device** result, which is the standard ADP-6828 set and the standard
  a render does not meet. A footer on a short scrollable screen sat flush to the physical bottom
  with the gap above it, as designed. If a void ever comes back, this is what it is, and docking
  is the fallback. The pre-2026-08-26 version of this bullet said "prefer a pinned container over
  the native `footer`" — that steer is what talked an agent into building
  [a fake footer](#a-bar-that-stays-at-the-bottom-use-footer) out of `fixed` stacks.

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

### A bar that stays at the bottom: use `footer`

`footer` is a real element type, and it is the one thing on this page you do **not** build out of
`fixed` stacks. It is lifted out of the layout flow and pinned to the bottom of the viewport while
the content scrolls past it — which is exactly what a CTA bar, a legal row or a plan-picker dock
is for.

Take the shape from the builder's own template rather than authoring it:

```bash
jq '.components[]|select(.id=="footer")|.template' references/component-catalog.json
```

It is the only component in that catalog carrying an `insertion_policy` (`screen_footer`), and its
props are the plain container set — `position: relative`, `width: fill`, `height: hug`, padding,
and **an opaque `fill`**. `flowkit.footer([...])` emits it.

**Measured 2026-08-26** on one screen rendered eight ways, changing a single thing at a time
(content 14x80pt against a 900px viewport, so an in-flow bar sits below the fold):

| The bar | Where it drew |
|---|---|
| `type: "footer"`, `scrollable: true` | pinned at the viewport bottom, at its authored 88pt |
| identical props, `type: "stack"` | **nowhere** — below the fold |
| `type: "footer"`, `scrollable: false` | same pinned band in the preview — **and NO FOOTER AT ALL on device** (see the rule below; this row is why a local render is not a device) |
| `footer` declared **first** in `hierarchy` | same pinned band — declaration order is irrelevant |
| a **second** `footer` on the screen | drew **nothing at all**, zero pixels |
| `footer` with **short** content above it | same pinned band, void *above* it |
| `stack` with short content above it | in flow directly under the content, void *below* it |
| `footer` with **no `fill`** | content visibly scrolls **through** it |

**Reserve nothing yourself: the scroll extent already accounts for the footer.** Measured by
scrolling the live preview page to the end rather than screenshotting it (iPhone 14, viewport 844),
and then **confirmed on a device** — the last row clears the bar at full scroll with no authored
reservation. Both halves were worth having: `scrollable` proved the two renderers can disagree, so
a scroll claim from the preview is a hypothesis until hardware agrees.
With no authored `padding.bottom`: `scrollHeight` 1424 = 1300 of content **+ the footer's own 124**,
max scroll 580, and at full scroll the last row ends at 682 against a footer band of 721-844 — it
clears by 39px, so nothing is ever stranded behind the bar. Author `padding.bottom: 124` "to make
room" and every number moves by exactly that: `scrollHeight` 1548, max scroll 704, and the gap
above the bar grows from 39px to **163px of dead space**. The reservation is already made; yours is
added on top of it.

So the mechanism, which accounts for every row of the table above: **a footer contributes its
height at the END of the scroll extent — wherever in the hierarchy it is declared — and is painted
pinned to the viewport bottom.** The contributed height is why content clears at full scroll and
why the identical props on a `stack` fall below the fold; the pinned painting is why the fill has
to be opaque. A docked `fixed` bar contributes nothing, which is exactly why *that* pattern needs
`padding.bottom` to equal the bar's height, and why getting the arithmetic wrong put a footnote
under a CTA.

**Device-confirmed 2026-08-26** (Adapty mobile app, Android): the footer pins to the bottom while
content scrolls **behind** it, the last row clears it at full scroll with no authored reservation,
and on a short screen it sits flush to the physical bottom. What the device *changed* versus the
preview is exactly one thing, and it is rule 0.

Five rules follow. The first is a hard requirement and the local render cannot see it:

0. **A `footer` requires `scrollable: true`. Never pair one with `scrollable: false`.**
   Device-confirmed 2026-08-26 (Adapty mobile app): with the scroll off the footer **does not
   render at all** — not misplaced, absent, and every child inside it goes with it, so a CTA
   living in the footer takes the screen's only navigation with it. The preview draws it
   identically in both modes, so this is invisible to `config preview`, to the schema check and
   to `flows config validate`. `flowkit.screen()` now refuses the pair and `verify-config.py`
   errors on it. If a screen must not scroll, it cannot have a footer — use the root's own
   [`space-between`](#putting-a-short-screens-content-and-bar-apart-the-roots-own-distribution)
   instead. That gives a clean split with no judgement in it: **`scrollable: true` -> `footer`;
   `scrollable: false` -> a spread distribution.**

1. **One `footer` per screen.** A second one is silently dropped, so a CTA and a legal row go
   inside the *same* footer as children, never as two footers.
2. **Put it anywhere in the hierarchy** — last child is the readable choice, but position carries
   no meaning.
   **Set no `padding.bottom` to reserve it, and no offsets.** Both are docking habits; here they
   only add dead space.
3. **Give it an opaque `fill`.** The footer overlays scrolling content, so without a fill the
   content passes visibly behind the CTA. This is the defect that gets misread as "the docked
   pattern is broken", and it is a property of the footer, not a reason for a backing plate.
4. **Never build a lookalike.** An empty `fixed` stack with a `fill`, sitting behind separately
   docked elements, is a *fake footer*: it reproduces the fill and the position and none of the
   pinning, and every local gate passes it. `verify-config.py` now warns on that shape.

**No gate but `verify-config.py` sees any of this.** Measured the same day: `flows config
validate` returned `valid: true, issues: []` for the correct footer *and* for two footers, for the
fake footer, and for the unfilled footer whose content shows through — and the shipped schema check
passes them too, because `IFooterElementProps` is the **same property set** as
`IStackElementProps`. So the schema cannot tell you a footer behaves differently from a stack, and
the publish gate will not tell you that you should have used one. Read the catalog template and
look at the render.

### Putting a *short* screen's content and bar apart: the root's own distribution

Different job, and still the right tool for it. A `footer` pins the bar and leaves the void
**above** it; when a short screen should instead spread its content out to fill the height, that
is the root's `distribution`. Give the screen root exactly two children — a content stack and a
bar stack — and set:

```json
"props": {"scrollable": false,
          "layout": {"direction": "vertical", "alignH": "center", "alignV": "start",
                     "distribution": {"type": "space-between"}}}
```

The free space lands between the two, with **no** `fixed` positioning, no `padding.bottom`
reservation, and no arithmetic to get wrong. Measured across four screens (2026-08-24) this
removed both of the failure modes the `fixed` alternatives carry: a footnote that had slid under a
docked CTA, and the dead void an in-flow bar leaves on a tall device.
`flowkit.screen(..., distribution='space-between', scrollable=False)`.

**Choose per screen, because the cost is real:** a spread mode needs a definite-height container,
so it wants `scrollable: false`, and that **clips** content taller than the viewport. So: a bar
that content must scroll past is a `footer`; a short screen whose content should breathe is a
spread; a screen that needs both is a `footer` plus a spread on the content above it. See
[flow-schema.md trap 10b](flow-schema.md) for the vocabulary and
[preview.md](preview.md) for why you cannot check the clipping locally.

### A bottom-docked button

**Reach for this only once `footer` is ruled out.** Docking a bar was the old answer to "keep it
at the bottom while content scrolls", and `footer` does that natively, opaquely, and with no
offsets to compute. What is left for `fixed` is a single overlay that is *not* a bar — a floating
close button, a corner badge — and the fallback if a device shows one of the two
[dated `footer` reports](#layout-discipline-the-support-channel-keeps-re-learning).

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

A row is `[chip, rail, text]` where **only the text is in flow**. The chip and the rail are
absolute overlays on the row, and the rail is anchored **top and bottom** so it stretches to
whatever the row turns out to be. That is the whole mechanism: the copy sets the row's height and
the rail follows it, so there is no number to compute and nothing for a rewrite or a longer locale
to break.

The skeleton is lifted from a real builder export and **verified by render**, including under
grown copy. The row, then its three children in this order:

```json
{ "id": "el_Row1", "type": "stack", "props": {
    "width": {"type": "fill"}, "height": {"type": "hug"},
    "layout": {"direction": "horizontal", "alignH": "start", "alignV": "start",
               "distribution": {"type": "gap", "gap": 16}},
    "position": {"type": "relative"} }, "states": [] }
```

```json
{ "id": "el_Chip1", "type": "stack", "caption": "Chip", "props": {
    "fill": [{"type": "color", "color": {"type": "hex", "hex": "#E9910B", "opacity": 100}}],
    "width": {"type": "hug"}, "height": {"type": "hug"},
    "layout": {"direction": "horizontal", "alignH": "start", "alignV": "start",
               "distribution": {"type": "gap", "gap": 16}},
    "padding": {"top": 4, "left": 4, "right": 4, "bottom": 4},
    "borderRadius": {"tl": 100, "tr": 100, "bl": 100, "br": 100},
    "position": {"type": "absolute", "top": 0, "left": 0} }, "states": [] }
```

```json
{ "id": "el_Rail1", "type": "stack", "caption": "Connector", "props": {
    "fill": [{"type": "gradient", "angle": 180, "stops": [
        {"position": 0, "color": {"type": "hex", "hex": "#E9910B", "opacity": 100}},
        {"position": 1, "color": {"type": "hex", "hex": "#E9910B", "opacity": 26}}]}],
    "width": {"type": "fixed", "value": 8}, "height": {"type": "auto"},
    "position": {"type": "absolute", "top": 10, "left": 12, "bottom": -18, "zIndex": -10},
    "visibility": {"type": "visible"} }, "states": [] }
```

```json
{ "id": "el_Text1", "type": "stack", "props": {
    "width": {"type": "fill"}, "height": {"type": "hug"},
    "layout": {"direction": "vertical", "alignH": "start", "alignV": "start",
               "distribution": {"type": "gap", "gap": 8}},
    "padding": {"left": 40}, "position": {"type": "relative"} }, "states": [] }
```

The chip holds one 24pt `icon`; the text column holds a title and a description. **The last row
carries no rail.**

**Three parts of the rail are load-bearing, each measured by removing it** from a rendered row
whose description had been grown from two lines to four — the exact copy growth that used to
reopen the gap:

| Change | Result |
| :--- | :--- |
| as above | rail runs continuously into the next chip and under it |
| drop `bottom` | rail collapses to nothing — **108px of white** below the chip |
| `height: fill` instead of `auto` | rail stretches but stops **2px short** — a hairline break |
| drop `zIndex: -10` | rail paints **over** the chip, erasing the icon inside it |

So: `bottom` is what gives the element height, `auto` is what makes the anchors authoritative, and
the negative `zIndex` is what keeps the rail behind the chips it runs under. `flowkit.absolute()`
emits the position object and refuses the two broken pairings; `verify-config.py` warns on both if
you hand-write them.

Derive the offsets rather than copying the numbers, since they follow from the chip:

- **chip** = icon + 2 × padding (24 + 8 = **32** above).
- **rail `left`** = (chip − rail width) ÷ 2, to centre it under the chip — (32 − 8) ÷ 2 = 12.
- **text `padding-left`** = chip + clearance (32 + 8 = 40).
- **rail `top`** = any value smaller than the chip's height, so the rail's head starts behind the
  chip rather than below it.
- **rail `bottom`** = −(the list's row gap + a few px of overlap), so the tail passes *under* the
  next chip instead of stopping at its edge — −18 against a `gap: 12` list.

**Fade the rail on alpha, not toward the page colour.** The gradient above runs one hex from
`opacity: 100` to `26`; a fade whose last stop *is* the background renders the tail invisible and
costs you 14px per row — trap 12 in `flow-schema.md`, and it reads as "the connectors are too
short" while the config is right.

Verify by measurement, never by eye: walk the painted runs down the rail column and assert **zero
gaps** (`references/render-measure.py --column`). A rail that stops one pixel short looks like a
design choice in a screenshot.

> Superseded, and recorded so it is not rebuilt: this used to be an in-flow rail sized by
> arithmetic, so that `chip + rail` exceeded the tallest text and the rail set the row pitch. It
> works until the copy grows — a description going from two lines to four reopened a **49px** gap —
> and every fix is another guess at a number a translator can invalidate. The absolute form has no
> such number. The old note that `absolute` "cannot fix a layout-flow problem" was drawn from a
> probe that never tried a `bottom` anchor.

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

**This paragraph was read past and the defect shipped again (2026-08-28), so it is now checked
rather than only stated**: `flowkit.on_selected()` emits the `states` + `propsByState.selected`
pair — on the member, on any descendant whose colour follows, or both — and `verify-config.py`
**errors** when a group's members differ in their base props with no `propsByState.selected`
anywhere in them. It is worth knowing why prose lost: the failure mode is *copying a reference
screenshot*, which can only ever show one card selected, so a literal transcription bakes that
frame in. No other gate sees it — validate passes, the schema passes, and the render draws one
frame in which the baked look and the state-driven look are identical.

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

### A side-by-side pair of docked buttons

Two buttons on one row at the bottom, each with its own action. **If the row should stay put while
content scrolls, put both buttons inside one
[`footer`](#a-bar-that-stays-at-the-bottom-use-footer) as a horizontal stack and skip the
arithmetic below entirely** — that is the case this section used to be written for, under the
title "a side-by-side docked footer". What follows is for genuinely free-floating buttons.

The trap is treating them as one fixed container holding two relative children: the container
swallows the taps (same failure as [a bottom-docked button](#a-bottom-docked-button)). Each button
is **its own `fixed` element**, one anchored left and one right, and their widths have to add up:

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
[`render-measure.py`](render-measure.py).

### A back button, and authoring an icon that does not exist yet

`navigateBack` needs no target — it pops the stack:

```json
{"id": "el_…", "type": "stack", "caption": "Back",
 "props": {"width": {"type":"fixed","value":40}, "height": {"type":"fixed","value":40}, …},
 "interactions": [{"id":"int_…","trigger":"tap","actions":[{"id":"act_…","type":"navigateBack"}]}]}
```

There is no `header` shortcut for this: `header` is a plain container with a stack's props and no
built-in navigation. (`footer` shares that prop set but **not** that inertness — it is pinned out
of the flow; see [`footer`](#a-bar-that-stays-at-the-bottom-use-footer).)

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


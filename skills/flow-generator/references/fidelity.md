# The fidelity pass

`SKILL.md` phase 4 owns the trigger and the exit condition. This file owns the pass itself: what to
inventory, and what to do with each gap you find.

**Run it whenever a reference was given** — an image, a screen to copy, a layout spelled out. Not
when you chose the design yourself; that case is graded by a teardown skill instead —
`paywall-teardown` for a screen that sells, `onboarding-teardown` for a sequence.

## Why it is a written list and not a look

"Nothing jumped out" is not a result. A side-by-side glance passes screens the user rejects on
sight, because "close" is a claim about *structure* and fidelity lives in everything else — colour,
weight, glyph style, the proportion between two blocks.

Measured on a real build with the skill loaded: the agent satisfied "look at it against the
reference" with a gestalt comparison and shipped emoji standing in for designed line icons, colours
named from memory, a gradient flattened to a solid, eyeballed proportions and an undisclosed font
downgrade. Every one of those was reachable.

The follow-up micro-test is the reason the *list* is the mechanism rather than the looking:
baseline agents shipped the substitutions **3/3 while disclosing them** — the disclosure machinery
worked, the defect frame was missing — and with the pass they produced the inventory and fixed
everything reachable **3/3**. Agents fix gaps they can see; the gestalt look never produces the
list. (The first version of that test handed the control arm the gaps pre-enumerated and both arms
complied, which measured nothing — the enumeration *is* the treatment.)

## 1. Inventory the reference

Per element, record what your render has — **match, gap, or unreachable**:

- colours, sampled from the image rather than named from memory
- typeface feel: weight, width, whether it is a system face
- icon style: line vs filled, corner radius, stroke weight
- photographs, illustrations, and backgrounds — gradient, glow, texture
- the proportions between blocks, not their absolute pixel sizes

A reference with a device frame needs its screen bounds located before any measurement, and
`render-measure.py` measures either image — both in
[preview.md → Comparing against a reference image](preview.md#comparing-against-a-reference-image).

## 2. Close every gap the format can reach

- **Colour** — sample it; never name it from memory.
- **Size and spacing** — match the reference's *proportions* with relative layout
  (`fill`/`hug`/`relative`). Never hardcode fixed container widths or heights to match image
  pixels; fixed geometry breaks across devices (ADP-7117).
- **Layout** — reach for the layout props before padding or docking. A bar the content scrolls
  past is the `footer` element, not something you position ([patterns.md](patterns.md));
  `distribution` has four modes, and `space-between` on the screen root spreads a short screen's
  content away from its bar ([flow-schema.md trap 10b](flow-schema.md)). A screen assembled from
  gaps plus reserved padding is the shape that reads as "broken everywhere": a dead void under the
  content on a tall device, or a bar sitting on top of it.
- **Glyphs**, in this order: author a **monochrome SVG** icon and render-verify it
  ([patterns.md](patterns.md)); if the graphic is **multicolour, gradient or illustrative** and no
  element can express it, **draw it, rasterize it on a transparent background, upload it, and say
  you drew it** ([media.md](media.md#when-a-graphic-cannot-be-an-element-draw-it-and-upload-it)) —
  never with text in it, never selectable, never a baked background; if you cannot draw it
  faithfully, ship a **styled empty placeholder**. **Never an emoji**: a placeholder asks to be
  filled, an emoji looks finished and ships a different design
  ([flow-schema.md trap 5](flow-schema.md)).
- **Gradients and glows** — rebuild them; do not flatten to a solid.

## 3. Turn what the format cannot reach into named user asks

In the handoff, never as a silent downgrade:

- a font the account lacks (still a manual Flow Builder upload)
- an image nobody has a file for, and any SVG asset (upload rejects it)
- an image you *were* given a file for is **not** on this list — upload it in phase 2

**Ship every remaining placeholder fully styled** — `borderRadius`, `objectFit`, a fixed size, on
the `image` element itself — so the upload lands styled instead of handing the user styling work
([flow-schema.md trap 5](flow-schema.md)).

## 4. Re-render and walk the pair again

Done means **every remaining difference is on the ask list**. A user who declines previews waives
the deliverable, not this pass.

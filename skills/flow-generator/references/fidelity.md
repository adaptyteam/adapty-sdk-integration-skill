# The fidelity pass

`SKILL.md` owns the triggers and the exit condition. This file owns the pass itself: what to
inventory, and what to do with each gap you find.

**It runs at two moments, not one.** The **asset half** belongs to phase 2, before you author
anything — deciding which of the reference's graphics the format can reach at all. The
**comparison half** belongs to phase 4, against the render. Doing the first one late is how a
lookalike gets built and then graded against the reference by the agent that built it.

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

## 1. Inventory the reference — and do the ASSET half in phase 2

Two passes over the same list, at two different moments, because one of them is useless late.

**In phase 2, before you author anything: which of these is an element, and which is an asset?**
The format reaches a **solid or gradient `fill`, a monochrome glyph, a rounded rectangle, and text
in a face you have**. Everything else in the reference is an **asset** — a photographic or
textured background, lettering filled with a gradient or a texture, an illustration, a glow, a
mesh, a chart, and any shape that is not a rounded rectangle.

Run every asset through phase 2's three states. **Never resolve one to the nearest element**: a
flat fill where the reference has a texture, a `text` where it has a designed lockup, a rounded
pill where it has an angled ribbon. Each of those renders perfectly, passes every gate, and is a
different design — the fake-footer and fake-carousel mistake with the reference standing in for
the missing element.

Doing this at phase 2 rather than phase 4 is the whole point. By phase 4 the lookalike is built
and you are grading your own lookalike against the reference, where "close" reads as a pass.

**In phase 4, per element, against the re-opened file:** match, gap, or unreachable —

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
- **Gradients and glows** — rebuild them as a `fill` with `stops`; do not flatten to a solid.

### Where each kind of graphic goes

One row per thing that is not plain text on a plain surface. The ladder underneath every row is
[media.md](media.md#when-a-graphic-cannot-be-an-element-draw-it-and-upload-it) — element, then a
file you were given, then **a styled placeholder and an ask**, and only when the ask cannot be
answered, a crop from the reference or a drawing. Asking outranks cropping because it gets their
real full-resolution asset where a crop gets a 1x copy of their mockup.

| In the reference | Where it goes |
| :--- | :--- |
| a monochrome glyph | an `icon` with `raw` SVG in `_meta.icons`, render-verified. Never rasterize this one, and **never an emoji** — a placeholder asks to be filled, an emoji looks finished and ships a different design ([flow-schema.md trap 5](flow-schema.md)) |
| a multicolour or gradient glyph, an illustration | no element expresses it → styled placeholder and an ask. Only if the ask cannot be answered: crop it out of the reference if its backdrop is flat ([crop.py](crop.py)), else draw and rasterize it and **say you drew it** |
| a textured or photographic background, a glow, a mesh, a chart | an asset. Their file if they have one — and note you **cannot** rebuild a texture from the reference, because the content occludes it and `objectFit` has no tile mode. Measured on a real paywall screenshot: the largest clean band was 352×50, and covering the screen with it stretched the texture 15× into vertical smears. A radial glow is not a `fill` with stops |
| **lettering whose treatment is unreachable** — gradient- or texture-filled, a display face the account lacks, outlined, distorted | an **asset**, not a downgraded `text`. A `text` element carries `color` and no `fill` — measured across all 7 real exports — so the treatment is genuinely out of reach. Ship a styled empty `image` at the measured box and ask for the lockup. **Unless it carries a variable or a price**, which an image cannot: then it stays `text`, and an unreachable treatment is a disclosed solid-colour downgrade |
| a shape that is not a rounded rectangle — a ribbon, a burst, a badge with angled ends | an asset. Its **backing** goes down the ladder; a label on top stays a `text`, so ask for the backing alone whenever the label has to translate |

## 3. Turn what the format cannot reach into named user asks

Never a silent downgrade, and never one line buried in a paragraph — collect them into the
missing-assets block `SKILL.md` describes, so the user sees the whole list and can answer it in
one go. Batch it with the phase-2 asks, because a path they hand over turns a placeholder into a
finished screen.

**Ship every placeholder fully styled** — `borderRadius`, `objectFit`, and a **fixed size taken
from the reference** — on the `image` element itself, so the upload lands styled instead of
handing the user styling work ([flow-schema.md trap 5](flow-schema.md)). A styled placeholder at
the right box also keeps the layout honest: an empty `values` map does not occupy the space the
real asset will, which is measured at 95px on a 932px screen.

The routes are **not symmetric**, so say which one applies rather than offering both everywhere:

| Asset | You can upload it for them | Builder only |
| :--- | :--- | :--- |
| PNG / JPEG / WEBP / GIF, ≤ ~2.5 MB | yes — `flows media upload` | also fine |
| SVG | no — `http_500`, reproducible | yes |
| a font | no — not an image; `validation_error` | **yes, and only here.** Then they must tell you the family name, because the upload mints the id you point `theme.typography` at |
| video | no path at all | yes |
| an image over ~2.5 MB | no — bare `http_400` | yes, or a smaller export |

**A font gets a substitute in the meantime, and the substitution is disclosed** — name the face you
used and how it differs. An undisclosed font downgrade is one of the five original failures that
put this pass in the skill.

### "Design around it" — the third route, and the one rule that makes it safe

The block offers a third answer beside the two upload routes: *replace that region with something
the format can build*. It exists because a placeholder has no exit when the reference is **someone
else's screen** — the user is never going to supply a competitor's photograph, so today's
checkerboard is permanent.

Notice what that route is: it is **substituting a reachable element for an unreachable graphic**,
which is the exact defect this whole pass exists to prevent. The only thing separating them is
consent, so the rules are about consent and nothing else:

1. **Never take it unasked.** The default is always the styled placeholder. An agent that decides
   for itself that a graphic is "probably a competitor's" and swaps in a gradient card has
   reproduced the original failure with a better excuse.
2. **A substitute is named, not just made** — what it replaced, and what you chose instead. It then
   goes through this pass like anything else, because a replacement you designed is a design you
   are now responsible for.
3. **One region you handle; a whole selling composition you do not.** If replacing the asset means
   redesigning what the screen sells — a hero that carried the proof, a card that carried the
   offer — that is a conversion decision and belongs to
   the **`paywall-teardown`** skill, which already owns that call. Swapping a
   decorative graphic for a gradient is not.

## 4. Re-render and walk the pair again

Done means **every remaining difference is on the ask list**. A user who declines previews waives
the deliverable, not this pass.

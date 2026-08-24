# Rendering a config, and what a render cannot tell you

`SKILL.md` phase 4 owns the loop. This file owns the evidence: why each rule exists, what the
render is blind to, and what to do when it fails. Read it when a render surprises you.

## Why the URL is not for reading

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

## What the screenshot is evidence of

**What this catches, precisely.** It catches the class no structural check can see: wrong
spacing, a magic-number indent, a detached element, a state that is silently wrong. It does
**not** subsume [Verify](#verify) — both defects in trap 10 were injected into a known-good
config and measured, and both still rendered. They lost a selected-tab highlight and nothing
else, which is visible to someone who knows what the screen should look like and invisible to
any "did anything draw" test. The structural rows catch them for free; keep walking them.

## Comparing against a reference image

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

## What a render cannot show you

Six things to know before a screenshot becomes an overclaim — five it cannot show you, and
one it shows that is not there:

- **A stranded variable.** The render prints an unresolved reference as its literal token, so a
  screen reading `{{name.value}}` looks *pixel-identical* whether its producer still exists or was
  deleted three screens ago — measured, two renders with the same MD5. Whether a consumer still
  has a producer is a Verify question (invariant 12) and preview will never answer it.
- **A `states[].condition` — but *not* a `visibility` one.** The two behave oppositely and the
  difference is easy to get backwards. A **`visibility: {"type": "conditional", …}`** condition
  **is** evaluated: a conditionally-shown button correctly appears or hides in the render, which
  makes the empty-field state of a form gate genuinely checkable here. A **`states[].condition`**
  is **not**: every element draws in its base props, measured on the disable-until-filled probe
  where four buttons carrying `disabled`-state conditions all drew in base teal. That asymmetry is
  survivable only because a conditional `disabled` state is not a real mechanism anyway — see
  [flow-schema.md](references/flow-schema.md#making-a-field-mandatory-show-the-button-conditionally).
  What the render still cannot tell you about a `visibility` condition: **an unresolvable variable
  is silently treated as empty**, so `empty` over a typo'd id renders exactly like `empty` over a
  real empty field. Only the *flip* — filling the field and watching the element appear — proves a
  reference resolves, and that needs the Adapty app. A wrong *operator* name, by contrast, fails
  closed and the element just vanishes.
- **It can draw something the device will not — the blindnesses are not all one-directional.**
  `old-price` renders a struck-through price in this preview and renders **nothing** in the Adapty
  app (measured, same config). Every other item in this list is preview showing you *less* than
  reality; this one shows you *more*, which is worse, because a layout built around a phantom
  element looks correct here and ships broken. Treat an element you have only ever seen in this
  renderer as unproven no matter how right it looks — see
  [flow-schema.md](references/flow-schema.md#old-price-a-real-element-that-does-not-draw-on-device).
- **Selection in any group that is not a product group.** The render simulates a
  `product`-type group's `default` — the chosen plan card shows its selected styling — but
  **ignores a `toggle` group entirely**: measured, flipping `default` between `true` and `false`
  on a toggle row produced byte-identical screenshots, while the product card on the same flow
  rendered as selected. So a switch, a checkbox or a pre-ticked consent row always draws in its
  off state here, and neither its `propsByState` nor its default can be checked visually. Send the
  user to the Adapty app for those.
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

- **Navigation, so the flow cannot be walked.** The page renders the screen named by `--screen`
  and stops there: measured on a two-screen config, a button carrying a `navigate` action left the
  page unchanged across two real clicks and a synthetic one. Every screen therefore needs its own
  render, and **branching cannot be checked here at all** — a `conditional` fires on a tap that
  never resolves. Route coverage is an Adapty-app check, or a reading of the config.

- **Text metrics that are not the device's — and a colour emoji is where it shows.** An emoji in a
  **hug**-width text box renders correctly here and is **clipped on iOS**: reported from a device
  screenshot of a flow whose preview was clean. The glyph's ink is wider than the advance width the
  layout engine measures, and a hug box leaves no slack. Give an emoji a **fixed box** — a fixed
  `width` and `height` with `align: center` and `verticalAlign: middle` (`middle`, not `center`,
  which the schema check rejects) — and the same rule applies to any glyph you are hugging tightly.
  Team-confirmed independently in the support channel: the transformer measures a size-24 emoji as
  17px, and their recipe is the same — a fixed width (theirs: 28). This is the one blindness on the
  list with **no** preview-side symptom at all, so it cannot be found by iterating here: it is
  found on a device, or by a user.

- **Any device but the frames the page knows, so a short-phone check is not available here.**
  `--device` defaults to `iphone-14`; `ipad-pro` appears in the CLI's own example. **The valid set
  is not enumerable** — it is not in the CLI package (`grep`ped) and not in the render page's
  entry bundle, and an id the page does not know renders `Unknown device "iphone-se".` as a
  **page**, with exit 0, which passes any "did something draw" check. So a layout whose safety
  depends on viewport height — `scrollable: false`, fixed heights, a tall content column
  ([flow-schema.md trap 10b](flow-schema.md)) — cannot be validated against a small phone from
  here. Reason about it structurally instead, and name it in the handoff. Note `--window-size` is
  **not** a substitute: the page draws its own device frame, so a smaller window crops the
  screenshot rather than re-laying-out the screen (measured 2026-08-24 — a 375×667 window returned
  the same 390pt-wide screen with its right edge cut off, which reads exactly like an overflow bug
  that is not there).

- **The device's own chrome — a notch, a Dynamic Island, a home indicator — because the render
  draws none of it.** A screen authored with `safeArea: false` put its back chevron and title into
  the island zone on a real phone (user-reported, 2026-08-24, from a device screenshot of a flow
  whose preview was clean) — the preview canvas starts at a bare top edge, so the collision has no
  preview-side tell. Author new screens with `safeArea: true` unless the design genuinely paints
  under the status bar. The same missing viewport frame hides the bottom half of the problem: an
  in-flow CTA that ends mid-canvas reads fine in a PNG and as a half-empty screen on a device —
  when the reference pins its CTA to the bottom, that is a `fixed` dock
  ([patterns.md → a bottom-docked button](patterns.md)), not a flow item, and docked-over-scrolling
  content then needs a look at *both* ends: measured in the same session, a docked footnote
  collided with the last content row at one viewport height and cleared it at another.

- **Invisible text defects.** Copy-pasted text carries empty paragraph lines and trailing spaces
  the preview does not show and the device does — one stray Enter produced a device-only vertical
  gap that took the support team days to find. Deliberate gaps are separate Text and Spacing
  elements, never blank lines inside a rich-text value.
- **Prices are hardcoded stubs, everywhere short of a real app.** The builder preview's "3.99" is
  a literal number in the page's code, and the Adapty preview app's prices are mocks too
  (team-stated) — so no preview surface proves a price, an offer, or trial eligibility; only the
  client's own app does. An offer configured as a free trial resolves to 0 where it resolves at
  all.

## An element that fails to paint is not automatically yours to fix

**An element that fails to paint is not automatically yours to fix.** A `position: fixed` CTA
rendering as an empty band — laid out, occupying its height, painting nothing — is a *reported
renderer defect* on this page, isolated by bisection to `props.position.type == "fixed"` on a
`schemaVersion` 9 flow. It did **not** reproduce here: on a v10 config, both docked forms
(`left`/`right` + `width: auto`, and `bottom` alone + a fixed width) paint correctly. So treat a
missing element as a question, not a verdict — render the *source* config and compare before you
restyle anything. Deleting a working `position` to make a screenshot look right is how a correct
config gets broken.

## The mismatch class is systemic, in both directions

The support channel treats preview-vs-device disagreement as a standing class, not an anomaly, and
it runs **both ways**: a carousel that renders correctly in the builder preview and breaks on
device, and a deliberately device-correct config that "looks broken in the builder" — the team's
own workaround author could not make one config look right on both. Standing team guidance since
May 2026: margins, padding and borders "can differ between preview and real device, so do the
final check on the device." Which is what phase 5's callout hands to the user.

## Four surfaces, and they do not agree

**A clean preview does not prove the builder will open the flow.** The preview page and the
Flow Builder's editor are different renderers, and the two configs that broke the builder in
this project's history both render here. So report a good screenshot as "this looked right at
this size", never as "the flow works".

**There are four surfaces and they do not agree.** Know which one you are quoting:

| Surface | What it tells you |
| :--- | :--- |
| `config preview` + a screenshot | fast, scriptable, and a *different renderer* — layout and spacing only |
| the **Adapty mobile app** | also the strictest *validator* you can reach: it runs the transform service, which `config update` does not. On a newly authored flow it returns 422 for a missing `flowProductId` until the flow has been published once |
| the Flow Builder editor | whether the authoring tool can open it; where the user reviews and publishes |
| the **Adapty mobile app** | the real **SDK** renderer — the only preview that reflects what a user gets, and therefore the one that would surface an `unsupported_…_setting` the transform service warned about |
| published and live | the truth, and the only state your users ever see |

You can reach the first. Everything below it belongs to the user, which is why the callout in phase 5
asks for the mobile-app preview explicitly rather than treating a screenshot as sign-off.

## When the render fails: the file input, not a smaller config

**Do not decide whether to preview from the file size.** The command's own help calls it a
quick-look escape hatch and mentions ~32KB of pretty-printed JSON as the point where the render page
gets slow. That is a symptom to watch for, **not a budget to check a config against** — and two
agents used it as grounds to skip previewing entirely, on configs that render fine. Measured:
a 171KB config renders, and so does a 143KB one; gzip in the fragment is very effective, so 56KB of
config yields a 6,349-character URL. Always try the preview. If the render comes back slow,
truncated or blank, *then* fall back to the dashboard.

**When the URL render fails, switch to the file input — do not shrink the config.** `preview` packs
the whole config into the URL fragment, and on a large flow the failure is not an Adapty limit: the
page's third-party analytics beacons put `location.href` into their own query strings, so a 113K
hash becomes a 113K beacon request, the beacon host answers **414**, and the app's own assets die
as collateral on the torn-down connection — the bundle never boots and you screenshot an error
page. Reported for a 668KB flow; loads at a 32K fragment, hangs at 64K.

The escape hatch is [`preview-with-playwright.mjs`](references/preview-with-playwright.mjs), which
opens the render page on a **short** URL and hands the config to its file input
(`[data-testid="preview-config-input"]`) instead. Same page, same renderer, no fragment. The same
668KB flow that fails through the URL renders that way in 6-8 seconds.

**`--device` is not validated — a wrong value renders a page, not an error.** The flag accepts any
string, exits 0, and the render page answers an unrecognized id with the words
`Unknown device "…"` on a blank background. That screenshot carries a few hundred distinct colours
from text antialiasing, so it survives a naive "did anything draw" check and looks like a successful
preview. `iphone-14` (the default) and `iphone-13-mini` are confirmed to work; `iphone-se`,
`iphone-12-mini`, `iphone-8` and `pixel-7` are not recognized, and there is no published list. So
stay on the default unless you have a reason to change it, and if you do pass `--device`, confirm
the image shows the frame you asked for rather than that message.

**Check that you screenshotted the flow at all.** The page answers a bad `--device` with
`Unknown device "…"` as a *page*, a broken fragment with an error page, and a wrong host with a
login screen — all of which are PNGs that pass a "did anything draw" test. Before you reason about
a render, confirm it shows the screen you asked for.

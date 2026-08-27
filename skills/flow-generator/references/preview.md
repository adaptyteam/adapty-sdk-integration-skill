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

Comparing means *measuring*, not glancing. [`render-measure.py`](render-measure.py) does it for either image —
`--row Y` for widths, `--column X0:X1` for painted runs and the gaps between them, and
`--scale <image-width>:<device-points>` to convert a reference's pixels into the numbers you put in
a config.
That is how the rail was confirmed correct at 46/38 while the eye kept insisting it was too narrow,
and how the real defect — a 14px break between connector and chip — was found.

**A mockup that shows a device frame needs its screen bounds located before any of that**, and
fractional coordinates read off the picture are worthless until you have them. Find them from
**row means across the phone's width**, not from a single column: a column through the artwork
hits dark glyphs and dark pixels in a hero image, which truncates the run and yields a band that
is confidently wrong — it took three attempts on one mockup, each producing a different "screen
height", before the row-mean scan gave the real 393×875. With true bounds, sampling the palette
becomes exact: three independent samples of the same accent returned the identical hex.

## What a render costs, and which knobs do nothing

The screenshot is the most expensive step in the whole workflow, so it is worth knowing what
actually drives it. Measured on one config, same machine:

| | |
|---|---|
| One headless screenshot | **17-20 s** |
| `flows config preview` (the URL) | **0.08-0.11 s** — and a 187 KB config is no slower than a 57 KB one |
| `--virtual-time-budget` 5000 vs 9000 ms | **byte-identical output**, 20.2 s vs 17.1 s |
| `--virtual-time-budget` 1500 ms | **no file at all**, and the wait runs to your timeout |
| 3 Chrome instances at once | did **not** finish in 120 s, when one alone takes 18 s |

So *when the host is fast* the cost is Chrome's **cold start** — not the page, not the config size,
and not the budget.

**Corrected the same day, and the correction matters more than the table:** when the render host
is *slow*, the budget is the only thing that decides whether you get a file at all. Measured on a
slow afternoon — an 8 s budget produced nothing for a config that had rendered fine hours earlier,
Playwright timed out at 30 s on `domcontentloaded`, and **a 60 s budget produced a correct
screenshot ~72 s later**. The same page loaded normally in a real (non-headless) browser
throughout. So **"no file" is far more often a slow host than a broken config**: escalate the
budget, then check the URL in a real browser, and only then suspect your work.
[`shoot.sh`](shoot.sh) retries at 60 s automatically.

Three consequences:

- **The number of renders is the cost of phase 4.** Render the screens you changed, not every
  screen. A seven-screen re-render to check one edit is six launches of pure waste.
- **Do not tune the budget *down*.** Lowering it buys nothing on a fast host and yields no file at
  all below a threshold, and the failure looks exactly like a hung render rather than a bad flag.
  Raising it is the correct response to an empty shot — see the correction above.
- **Do not parallelise.** Instances contend; `--user-data-dir` (the obvious fix for that) makes
  the launch fail outright, which is a second way to lose a minute.

**Join the screenshots into one strip before looking**, with
[`montage.py`](montage.py) — `montage.py strip.png a.png b.png c.png`. It is pure stdlib, so
there is nothing to install. That turns N inspections into one, and a before/after pair only reads
as a *difference* when the halves are adjacent; `--gutter 0` butts them together when you are
comparing pixel positions rather than eyeballing.

## Two things a render equates that the config does not

- **An identical screenshot is not an identical config.** Measured: deleting an entire
  `bottom-sheet` element gave a **byte-identical** render, because the sheet was hidden in the
  state that draws. So a before/after pair that looks the same is not evidence the change was
  cosmetic — it may be evidence the change is invisible *in this state*. Structural summaries are
  what cover the gap, which is why the phase-5 approval ask has a second list for changes with
  nothing to see.
- **The page renders one screen and does not walk the flow.** Measured: a button carrying a
  `navigate` action left the page where it was, across two real clicks and a synthetic dispatch.
  So a multi-screen change is N separate renders, and opening N tabs buys noise rather than a
  walkthrough; branching cannot be exercised here at all.

## What a render cannot show you

What to know before a screenshot becomes an overclaim — mostly things it cannot show you, and
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
  [flow-schema.md](flow-schema.md#making-a-field-mandatory-show-the-button-conditionally).
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
  [flow-schema.md](flow-schema.md#old-price-a-real-element-that-does-not-draw-on-device).
- **Selection in a `toggle` or a `multi_choice` group — but `single_choice` and `product` DO
  draw.** The boundary is per group type, and it is narrower than "not a product group". Measured:
  a `product` group's `default` renders selected (the chosen plan card shows its selected
  styling), and so does a **`single_choice`** row — `propsByState.selected` fires, accent border
  and swapped tick included. A **`toggle`** is ignored entirely: flipping `default` between `true`
  and `false` on a toggle row produced byte-identical screenshots. A **`multi_choice`** is ignored
  too: measured 2026-08-24 on a 7-row market picker whose first row carried `default: true`, the
  render drew every row unselected while a `single_choice` screen in the same config drew its
  default row selected.
  **You can borrow the renderer to see a toggle's on-state.** Since `single_choice` selection
  *does* draw, temporarily retype the group `"type": "toggle"` → `"single_choice"` in a throwaway
  copy, render that, look at the on-state, and revert. Used on a real build to confirm a trial
  card's selected styling — the coral border, the swapped check indicator and a strip of copy that
  only exists when selected — none of which the toggle form will ever show you. Keep it in a
  separate file so the shipped config is never the retyped one.

  **So a `multi_choice` row drawing unselected is not a defect to chase** — confirm `default` in
  the config and move on; "fixing" a correct config here is the trap. A switch, a checkbox and a
  pre-ticked consent row always draw in their off state, and neither their `propsByState` nor
  their default can be checked visually. Send the user to the Adapty app for those.
- **A `spinner`, layout-dependently.** Measured 2026-08-26: the same `spinner` element drew in an
  isolated probe and drew **nothing** inside a centred loading screen, while `validate` returned
  `valid: true` and the device drew the screen's other elements fine. Which layouts suppress it is
  **not isolated**, so a blank where a spinner should be is *unproven, not broken* — and the
  rotation is a device check either way, since a still PNG could not show it even if the glyph
  drew. What this blindness must never license is a repair: swapping the `spinner` for a static
  ring `icon` makes the screenshot look complete and ships something that does not animate
  ([patterns.md → a loading screen](patterns.md#a-loading-screen--fill-the-loader-spinner-label-template-never-fake-the-spinner)).
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

  **A screen that advances itself is therefore 100% unverifiable here, and that changes how you
  hand it over.** Measured 2026-08-25 on a timed loading screen: after 15 s of
  `--virtual-time-budget` the dumped DOM was still the same screen. That result is *worthless as
  evidence* — the page never navigates for any reason, so a broken `timer-end` and a working one
  produce the identical observation. The consequence is a process one: when the only surface that
  can exercise a mechanism is the user's device, **build the diagnostic in before the first ask,
  not after the fourth.** A timed screen handed over bare yields one bit ("still spinning"); the
  same screen handed over with its countdown temporarily made visible — a child `text` carrying
  the `timer_minutes`/`timer_seconds` tokens — splits the failure in two at no extra cost to the
  user: *digits never appear or freeze* is the element not mounting, *digits reach zero and
  nothing happens* is the trigger not firing. Say it is temporary and remove it after. Paid for
  the hard way: four blind config tweaks were shipped to a user's device one at a time before
  anyone thought to make the timer visible, and the instrumentation cost exactly one cycle.

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

## The mobile-app link, and why it is not the render URL

**You can hand the user a link straight into surface 2 instead of describing it.** The Flow
Builder's "Test on Device" button is a QR over a plain URL, and that URL is pure string
construction — no network, no auth, nothing from Adapty's servers:

```
https://mobile-app.adapty.io/flow-preview?app_id=<uuid>&flow_id=<uuid>&current_locale=en&locales=en,uk&cluster=us
```

[`mobile-preview.mjs`](mobile-preview.mjs) builds it and renders the QR. Everything it needs is
already in your hands by phase 5: the two ids, and `locales`/`defaultLocale` off the config.

**It previews what is SAVED, not your local file — the exact opposite of `config preview`.** The app
opens the link and fetches the flow's current draft from Adapty. So it is a phase-5 tool that runs
*after* `config update`; built before the write, it shows the previous version and reads as "the
agent's edit did nothing". The upside of that fetch: one link stays valid across later writes, so
hand it over once rather than regenerating it per change.

**Print this URL freely.** At ~170 characters it is the opposite of the render URL above — every
part of it is meaningful and a human may well need to read it aloud or retype it.

Three details worth not rediscovering:

- **`defaultLocale` holds a locale *id*, and the link wants a *code*.** The builder resolves id→code
  before building the URL. They are equal in every config seen so far, which is exactly why passing
  the id through would go unnoticed until the first flow where they differ.
- **The `locales` separator must be a literal comma.** Building the query with `URLSearchParams`
  percent-encodes it to `%2C`, and the app is only *known* to accept the builder's spelling. The
  script assembles the string by hand for that reason; a rendered QR has been decoded back to
  confirm the comma survives.
- **`cluster` is hardcoded `us`, and that is a real limitation, not an oversight.** The builder
  hardcodes it too, carrying a TODO to derive it from app config, and nothing on the developer API
  exposes an app's cluster. An EU or CN app therefore gets a US link from the dashboard and from
  this script alike. `--cluster` overrides it if you know better.

**What the link does not fix: the app is still the strictest validator you can reach.** On a newly
authored flow it returns 422 for a missing `flowProductId` until the flow has been published once —
see the surfaces table above. A link that opens to an error is the transform service talking, not a
broken link.

### The QR is a file, and character art was tried and rejected

`--qr` writes a 456x456 PNG and prints a `file://` URL for it, which is what belongs in the
callout — the reader clicks it and their image viewer opens something that scans.

**It writes beside the `--config` file, and that placement is the point.** A viewer refuses to open a
path outside the working directory ("This file is outside the working directory"), so an image
written anywhere else is unopenable and the file form buys nothing. Anchoring to the config also
dodges the cache-dir trap: the documented invocation runs from `~/.cache/adapty-flow-qr`, so a
relative `--out` would land there. The name carries the flow id (`flow-preview-qr-<flowid8>.png`) so
two flows in one session do not overwrite each other, and it is a throwaway — regenerate rather than
keep it, and keep it out of commits.

**Do not render a QR as characters.** Both half-block forms were built, measured and removed:

| Form | Size | Why it lost |
| :--- | :--- | :--- |
| ANSI terminal | 29 rows x 55 cols | 29 rows of noise in an answer, and the escapes do not survive a markdown renderer |
| plain half-blocks | 31 rows x 61 cols | same bulk, plus **inverted on a dark terminal** |

The second one is the instructive failure. A glyph there is a **dark** module and takes the
*foreground* colour — measured, the glyph count equals the matrix's dark-module count exactly — so
on a dark theme the code renders inverted. Phone cameras often read an inverted code, which is
worse than never reading it: it works on your machine and fails on the user's. It also has to sit
in a fenced block or the rows lose alignment and it stops being a QR at all. A file has none of
these properties, so there is no reason to reach for character art.

**A QR of any kind is useless to a reader on a phone**, who cannot point their only camera at their
own screen. Always print the bare link beside the image link, and outside backticks so terminals
linkify it. That reader is disproportionately the one who wants the device preview.

**Verified end to end**: the PNG was decoded back to the exact URL by an independent decoder, then
scanned off a screen with a real phone, which opened the flow in the Adapty app.

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

The escape hatch is [`preview-with-playwright.mjs`](preview-with-playwright.mjs), which
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

# Media assets: uploading an image and binding it into a config

`flows media upload` puts a local image file on Adapty's CDN and prints the URL to reference from
a flow config. It is the only asset path an agent has, and it closes the gap that used to make
every image in an authored flow a user ask.

Everything below was measured against **production** with `adapty` 0.8.0 on 2026-08-24, in
`app_finance`. Where a claim rests on a render rather than on the endpoint, it says so.

## The call

```bash
$ADAPTY flows media upload --app <APP_UUID> ./hero.png
```

```
Image uploaded!
ID: 516395
Name: hero-600x400.png
URL: https://public-media.adapty.io/public/1e/5b/1e5bbbb4-.../hero-600x400.png
```

The file argument is positional and required; `--app` is the only flag that matters. The printed
URL is **live immediately** — a `curl` against it returned `200 image/png` in the same second as
the upload, so there is no propagation wait to build into the workflow.

**Capture the URL from the human output, never with `--json`.** The JSON body carries a fourth
key, `preview_base64` — a WEBP thumbnail inlined as base64, **8,232 characters for a 5 KB source
PNG**. It is pure context burn with no use to an agent, and on a real hero image it is far worse.

A config needs **both** the id and the URL, so capture both from the *one* invocation — the
upload does not deduplicate, so running it again just to read the other field leaves a second
identical asset behind that no CLI command can remove:

```bash
eval "$($ADAPTY flows media upload --app "$APP" ./hero.png \
        | sed -n 's/^ID: /MEDIA_ID=/p; s/^URL: /MEDIA_URL=/p')"
```

## Getting the file: the upload needs a PATH, not a picture

The command reads a file off disk. **An image you can only *see* is not an image you have** — a
screenshot or hero the user pasted or attached into the conversation reaches you as pixels in your
context, and there is no path for it and no way to write one: you cannot re-emit the bytes you were
shown. Checked on a Claude Code install, pasted images are not persisted to disk (`~/.claude/paste-cache`
held text only), and this has to hold across harnesses anyway — this skill runs on four CLIs whose
attachment handling differs.

So resolve every asset to a path, in this order:

1. **A path the user gave you** — typed (`./assets/hero.png`), or dragged into the terminal, which
   most terminals insert as a path. Confirm it reads before you build around it.
2. **A file already in the project** — look for it (`assets/`, `public/`, `design/`) and name what
   you found, so a wrong guess is the user's to catch rather than yours to hide.
3. **A URL the user pointed at** — downloadable, but a download is a side effect: say what you are
   fetching and from where, and get a yes before you fetch. Then upload the downloaded file.
4. **Pasted or attached only, with no path** — **ask for one.** "I can see the hero but I can't
   upload what I can't read from disk — save it anywhere and give me the path." One ask, batched
   with your other asks; until it arrives the element is an empty `values` map, exactly as if no
   asset existed.

**Never guess a path, and never substitute a file that merely looks right.** A guess that misses
fails loudly and safely — exit 2, `Cannot read file: ./hero.png`. The damaging version is the guess
that *hits*: uploading `assets/hero.png` because the name matched, when the user meant the image
they pasted, produces a screen that renders perfectly with the wrong picture in it, and no check in
this skill can tell. If you searched for the file rather than being handed it, say which file you
used.

## What it accepts

| Input | Result |
|---|---|
| PNG, JPEG, WEBP, GIF | uploads |
| **SVG** | **`ApiError: http_500`, reproducible** — see below |
| Anything not an image | `validation_error`: `target_format: value is not a valid enumeration member; permitted: 'JPEG', 'JPEG2000', 'WEBP', 'PNG', 'SVG'` |
| ~2.6 MB file | uploads |
| ~2.95 MB file | bare `http_400`, no message, no `fieldErrors` |

**The size cap is on file bytes, not on dimensions.** Measured both ways: a **3000×2000** PNG at
22 KB uploaded fine, while a **1150×900** PNG at 3.1 MB was refused. The boundary sits between
2,599,724 bytes (accepted) and 2,950,946 bytes (refused), so treat **~2.5 MB as the working
ceiling**. A bare `http_400` with an empty `fieldErrors` on this command means *too large* — the
endpoint says nothing else, so do not go hunting for a config problem.

**SVG is rejected in practice even though both sides claim to support it.** `.svg` is in the CLI's
own MIME map and `SVG` is in the server's permitted-format list, and it still returns `http_500`
on every attempt. So the upload path does **not** replace authored icon SVG: a **monochrome** glyph
stays inline in `_meta.icons` with real `raw` markup, needs no upload at all, and is strictly
better there — see the next section for why. Rasterizing a monochrome glyph to get it past this
endpoint is a downgrade, not a workaround.

**Exit codes:** `0` on success, `1` on any API refusal, `2` on an unreadable local file
(`Cannot read file: ./nope.png`). Read the exit code, not the presence of output.

**The upload is not idempotent and does not deduplicate.** The same bytes uploaded twice produced
two different ids and two different URLs (516395 and 516396). So **upload once per asset and reuse
the URL** through the whole preview loop; re-running the upload each iteration silently litters the
app's media library with duplicates that nobody will be able to tell apart.

## When a graphic cannot be an element, draw it and upload it

The format cannot express every graphic. A multicolour or gradient glyph, an illustration, a radial
glow, a chart, a mesh — none of these is a `text`, a `fill`, an `icon` or a stack of them. **Draw it,
rasterize it, upload it.** That is a real capability now, and leaving a hole in the screen or
substituting a lookalike is worse.

It is a **last** resort, not a first one, because everything an element does an image stops doing.
Work down this ladder and take the first rung that fits:

1. **A monochrome glyph → an `icon` element with `raw` SVG in `_meta.icons`.** Real exports write
   these with `fill="currentColor"`, so the glyph takes its colour from the element's `colorId` —
   which is what makes it follow the theme. Never rasterize this rung.
2. **A flat or linear-gradient surface → a `fill`** (with `stops`), on a stack you already have.
3. **A composition → stacks**, using the layout vocabulary before padding or docking.
4. **Only then: draw it, rasterize it, upload it.**

### Three things never become an image

**Text.** Not "text in a font the account lacks" — *any* text. Baked words cannot be translated
(a locale run rewrites fields, not pixels), cannot carry a price variable, and are invisible to the
locale parity check, so a rasterized price is the exact "renders perfectly, ships a lie" failure
this skill has already produced once. A missing typeface is a named ask to the user; it is never a
reason to bake the sentence into a bitmap.

**Anything selectable.** A group member must be a `product`, a `selectable` or a `tab-item`; an
`image` carrying a `groupId` is inert. So plan cards, toggles and tab bars cannot be pictures of
themselves, however much easier the picture looks.

**Anything whose colour must follow the theme.** An image has **no** appearance variant — the
`values` map is keyed by *locale*, and `IImageElement` has no light/dark hook anywhere. A themed
colour does (`light`/`dark` per entry in `theme.colors`), and this is not hypothetical: two of the
four corpus fixtures define a dark variant for **every** colour they declare (14/14 and 11/11). A
bitmap with a baked-in background is the thing that breaks, which is why:

### If you do rasterize

- **Transparent background, no baked surface.** Measured: alpha survives the upload — the CDN
  re-encodes the file but the served PNG is still RGBA — and it composites cleanly over a dark
  screen with no matte or white box. A transparent glyph is the only bitmap that is theme-safe,
  because the screen's own background shows through it.
- **Draw at 2–3× the box** and size the element in points; the box is in points and the asset
  scales to it (measured), so the source resolution is free. *Not* device-measured — the preview
  renderer is not a retina device — so treat crispness on hardware as something the device check
  confirms.
- **Say that you drew it.** A rasterized graphic looks finished, which is the emoji hazard one
  level up: nothing downstream flags an agent-drawn illustration, so name it as yours and as
  replaceable, or the user ships your sketch believing a designer made it.

## Binding the URL: two different shapes

An uploaded URL has two consumers, and they take **different shapes**. Getting this wrong is a
silent defect — no gate catches it (see below).

**An `image` element** wraps the value in the per-locale localizable map:

```json
{"id": "el_PSJTQ6QeQt", "type": "image", "props": {
  "image": {"_localizable": true, "values": {"en": {"id": "516395", "url": "https://…/hero.png"}}},
  "width": {"type": "fixed", "value": 242}, "height": {"type": "hug"},
  "objectFit": "cover", "borderRadius": {"tl": 20, "tr": 20, "bl": 20, "br": 20}}}
```

**A background fill** on a screen's or stack's `props.fill` takes the image **flat**, with no
`values` map and no `_localizable`:

```json
"fill": {"type": "image", "image": {"id": "516395", "url": "https://…/hero.png"},
         "color": {"type": "hex", "hex": "#FFFFFF"}}
```

Because the element form is localizable, **a different asset per locale is expressible** — the
`values` map is keyed by locale code exactly like copy. A fill is not localizable, so a background
that must change per language has to be an element.

**Write the `id` as a string.** The command prints a number and `--json` returns a JSON integer
(`"id": 516395`), while the schema's `IImage` declares `id` as a required `string` and every real
builder export carries it quoted. Stringify it as you bind it.

## No gate catches an image defect. Only the render does.

Measured on one config, four ways — real URL with a string `id`, with a numeric `id`, with no `id`
at all, and with an empty `values` map:

- **`flows config validate` returned `valid: true` for all four.** An image is not part of the
  publish gate, so **a flow whose hero is still an empty placeholder publishes cleanly** and ships
  an "Upload Image" checkerboard to real users.
- **The schema check passed all four too**, including the missing required `id`. The reason is
  structural and worth knowing: `ILocalizable.values` is typed
  `additionalProperties: {"$comment": "unhandled type: T"}`, i.e. completely unconstrained — so
  anything inside a localizable wrapper is invisible to the schema, `IImage`'s `required` included.
- **The render is the only check that sees any of it**, and only once a real URL is in place.

That is the whole argument for the ordering in the workflow: the image is verified by looking at a
screenshot, so the asset has to be in the config **before** the preview loop, not after it.

## Geometry: what changes when the asset lands

`objectFit` has exactly **two** legal values, `fit` and `cover` — not the CSS set. Measured render
boxes for one 600×400 (1.5:1) asset in a 242-wide slot:

| `height` | `objectFit` | drawn box | what happens |
|---|---|---|---|
| `hug` | either | **242×161** | height derived from the **asset's** aspect; `objectFit` has no visible effect, and a `value` left on the `hug` size is dead |
| `fixed: 300` | `cover` | 242×300 | the box wins, the asset is cropped to fill it |
| `fixed: 300` | `fit` | 242×161, centred | the box wins, the asset letterboxes inside it, leaving **139 px of dead band** |
| *empty `values`* | — | **242×256** | the placeholder checkerboard, near-square whatever the real asset's aspect is |

Two consequences an author acts on:

**A placeholder does not occupy the space the real asset will.** The empty map drew **95 px taller**
than the same element with the real 3:2 image — on a 932 px screen, a tenth of the height, and
everything below it moves. A layout previewed with placeholders is a layout that has not been
checked. Upload first.

**Crop transparent margins off before you upload: the BOX is the asset, so padding baked into a
PNG becomes layout.** An `image` box is filled by the whole canvas, alpha included, so a glyph
centred in a generously-padded export draws smaller than its box and pushes its neighbours away by
the difference. Measured 2026-08-25 across a six-asset set exported from a design file: the opaque
ink was **65–87%** of the canvas height (`ink/canvas` of 0.649, 0.706, 0.707, 0.724, 0.735, 0.870),
so a 302 px box drew a 196 px illustration and spent **106 px on nothing**. Sizing the box to the
*visible* artwork then requires dividing by that ratio per asset, which is guesswork; cropping to
the alpha bounding box first makes the box the artwork and the arithmetic disappear.

```bash
python3 -c "from PIL import Image; im=Image.open('in.png').convert('RGBA'); \
im.crop(im.getchannel('A').getbbox()).save('out.png')"
```

Two riders. **Crop before the first upload, not after** — the upload does not deduplicate and
`flows media` has no delete, so a re-crop leaves the uncropped copies in the user's library
permanently (this cost six orphans on the build that produced this note; disclose them). And
because the box is in **points** while the asset scales to it, upsample the crop 2–3× on the way
out: it costs bytes well inside the ~2.5 MB cap and keeps the artwork crisp on a retina device,
which no preview render can confirm.

**`hug` reflows and `fixed` does not.** With `hug`, the element's height is a function of the file
you upload, so swapping a 3:2 asset for a 4:5 one silently rewrites the screen. With `fixed`, the
box holds and the asset absorbs the mismatch — `cover` by cropping (choose it when the subject is
centred and the edges are expendable) and `fit` by leaving bands (which on a dark screen read as a
spacing bug rather than as an image, so prefer `cover` unless the whole asset must be visible).

## Still out of reach

- **SVG upload** — `http_500` (above). Icons stay authored inline in `_meta.icons`.
- **Video.** No CLI path.
- **Fonts.** Still a manual Flow Builder upload; a typeface the account lacks is a named ask, not a
  silent substitution.
- **Deleting or listing uploaded media.** `flows media` has only `upload`, so an upload cannot be
  undone from the CLI — one more reason not to re-upload per iteration.

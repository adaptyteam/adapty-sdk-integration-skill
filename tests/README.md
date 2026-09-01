# tests/

Not a test suite for the skills — a fixture corpus for `flow-generator` plus the tools that
check it. The skills themselves are prose; testing those means running agents against them
(see `docs/superpowers/plans/` for that design, which is local-only).

## The corpus

`fixtures/` holds four sanitized flow configs plus two shape fixtures, all tracked. The raw exports
stay gitignored in `fixtures-raw/` because they carry real product UUIDs and real
`public-media.adapty.io` URLs.

| Fixture | What it exercises |
| :--- | :--- |
| `onboarding-quiz-paywall.json` | 5 screens, branching, a component, cross-screen variables, 42 localizable fields |
| `comparison-paywall.json` | comparison table, custom typography preset, one product |
| `vpn-timer-draft.json` | countdown timer, four uploaded custom fonts, no products |
| `tabs-paywall.json` | the five-element tabs composite, three `const` product purchases — **confirmed to render** |
| `timeline-anchored.json` | the stretch-between-anchors form — `absolute` with `top`+`bottom`, `height: auto`, negative `zIndex` — **confirmed to render**, and the calibration target for the two checks that guard it |
| `reviews-carousel.json` | the real `carousel` — three slides, adjacent-slide peek, indicator dots from `props.dots` — **confirmed to render**, and the fixture that exercises the fake-carousel check's exemption branch |

**`timeline-anchored.json` is a hybrid and is excluded from the census.** Its screen is a real
builder export (element ids and all), but the theme comes from `onboarding-quiz-paywall.json`, the
copy was replaced with English, and the `_meta.icons` SVG was hand-authored so it would draw. It
earns a place because it is the only tracked artifact carrying that position form — the four census
exports have none of it, and both `verify-config.py` warnings about it were calibrated against this
file and two deliberately broken copies of it. Do **not** fold it into the counted claims in
`flow-schema.md` ("234 of 246 positions are relative" and the rest): those are over the four
exports, and a hybrid would quietly move numbers the skill presents as measurements of real
builder output.

**`reviews-carousel.json` is hand-authored and is excluded from the census too.** It was written
with `flowkit.carousel()` rather than exported from the builder, so it is weaker evidence than
every other fixture here — tier 3 on the skill's own ordering (a rendering flow > a real export > a
minimized fixture). **If a real carousel export can be sanitized, it should replace this file.**
What it is good for in the meantime is narrow and real: it is the only tracked artifact containing
a `carousel` at all, so it is what proves the element's `props.dots` draws the indicator row
(confirmed in `config preview` — the dots are visible under the slides, and no dot `stack` exists
anywhere in the file), and it is the only fixture that reaches the `carousel` exemption inside
`verify-config.py`'s fake-carousel check. That branch was calibrated against it in both directions:
adding three dot-like sibling stacks to this screen stays **silent** (the real `carousel` exempts
it), and downgrading that one element's `type` to `stack` makes the same file **fire**. Its dot
colours are theme colour ids, not the real export's hardcoded white — white dots are invisible on a
light screen and the preview draws light mode only, which is how that was noticed.

**Why these are tracked and not gitignored.** The shipped skill never reads them at runtime — its
references cite them only as provenance for a claim, never as a file to open or a script to run —
so they are not skill content and a runtime agent never depends on one being there.
They are tracked for two reasons that outlive any single session:

1. **They are the regression corpus for the tooling.** Every check in `verify-config.py` was added
   after a real defect and then run against all four to confirm it does not false-positive. That
   caught a wrong rule once already: a hex-fill check, added in the belief that a raw hex in a `fill`
   is ignored, **fired on two of these fixtures** — which is how the real cause (opacity is a 0-100
   percentage) was found instead of shipping a rule that contradicts real builder output.
2. **They are the evidence for the skill's counted claims.** `flow-schema.md` asserts things like
   "257 hierarchy nodes, 126 carrying children", "37 localizable `content` fields, 42 in total" and
   "234 of 246 positions are relative". Those are only falsifiable while the corpus is present, and
   the skill's entire voice depends on being measured rather than assumed.

`tabs-paywall.json` is the one with unusual standing: it is the artifact that resolved the tabs
crash, so it is evidence rather than just coverage. Sanitizing it does **not** change its render
(verified), because remapped product UUIDs only reach purchase payloads, not layout.

## The tools

```bash
python3 tests/sanitize-fixture.py fixtures-raw/x.json fixtures/x.json   # regenerate a fixture
python3 skills/flow-generator/references/verify-config.py tests/fixtures/*.json                   # structural checks
python3 skills/flow-generator/references/diff-config.py old.json new.json                           # what the newer one destroys
python3 tests/render-check.py                                           # does it draw?
python3 tests/render-check.py --baseline                                # record references
python3 tests/render-check.py --keep                                    # keep PNGs to look at
python3 skills/flow-generator/references/render-measure.py shot.png --column 23:68                 # is a column continuous?
python3 skills/flow-generator/references/render-measure.py shot.png --row 343                       # how wide is it, really?
python3 tests/test-flowkit.py                                            # the authoring helpers
python3 tests/test-diff-config.py                                        # the diff's two directions
python3 tests/test-snippet.py                                            # extract/plan/graft
python3 tests/test-audit-flow.py                                         # the audit's checks, both directions
python3 tests/test-unmapped-elements.py                                  # x-supported: the guarded set vs the corpus
python3 tests/test-legibility.py                                         # text-vs-background, both appearance variants
python3 tests/test-price-literals.py                                     # placeholder + baseline-relative price literals
python3 tests/test-product-fields.py                                     # the closed product-variable field set
python3 tests/mobile-preview-check.py                                    # the device-preview link, over the corpus
```

Exit codes match the repo's lint convention: `0` clean, `1` findings, `2` infrastructure
problem (CLI or Chrome missing — fix the tooling, not the fixture). `diff-config.py` is the one
whose `1` is not a finding about the document: it means *this write removes something*, which may
be exactly what was asked for. Its calibration table lives in
[merge.md](../skills/flow-generator/references/merge.md).

`render-check.py` needs `adapty@beta` (for `flows config preview`, which is local-only and needs
no auth) and Chrome or Chromium.

### Which tool catches what

Measured 2026-08-20 by injecting the two defects from `flow-schema.md` trap 10 into
`tabs-paywall.json`, the config confirmed to render:

| Defect | `verify-config` | `render-check` blank test | `render-check` baseline diff |
| :--- | :--- | :--- | :--- |
| 108 elements missing `states` | **caught** | passed | caught — 1.2% |
| group typed `tabs` not `single_choice` | **caught** | passed | caught — 1.2% |
| every screen emptied | caught | **caught** | — |

Two things follow, and both are easy to get backwards:

**The structural checks are the trap-10 defense, not the render.** Both broken configs draw
pixels; they just lose a selected-tab highlight. "Did anything render" is blind to that.

**The baseline diff works but is not portable.** The control — an unmodified config against its
own baseline — is 0.00%, so there is no false-positive floor to tune around, which is what makes
1.2% a signal. But font rasterization differs across machines, so a macOS baseline will not match
one taken in Linux CI. `render-baseline/` is gitignored deliberately: it is a local gate for
"I changed a skeleton, did the render move?", and calling it a CI gate would be false.

**And a preview is not the builder.** The preview page and the Flow Builder's editor are
different renderers. Both configs that broke the builder render fine here, so a clean render
means "this looked right at this size", never "the flow opens".


## `render-measure.py` — measure a render instead of eyeballing it

*(Lives in `skills/flow-generator/references/` so it ships with the skill; the skill instructs agents to run it.)*

`render-check.py` answers *did it draw*. This answers *where and how big*, which is the question
you actually have when matching a screenshot.

It earns its place from a concrete failure: a timeline connector "looked too narrow", and several
rounds of edits went at its width. Measured, the width was already correct — 38 against a 46 chip,
matching the reference to the pixel — and the real defect was a **14px break** before the next chip,
caused by a gradient fading out onto the page colour. `--column` reports that as a gap; the eye
reported it as "too narrow" and sent the work in the wrong direction.

- `--column X0:X1` — painted vertical runs down a strip, **and the gaps between them**. Zero gaps
  is what "connected" means. Gaps ≤ 2px are called out as probable antialiasing.
- `--row Y` — painted horizontal runs on one scanline, i.e. widths.
- `--scale IMGW:PTS` — also print device points. A reference screenshot is almost never at 1×:
  divide by (image width ÷ device points), e.g. `--scale 602:390` for a 602px-wide shot of a 390pt
  phone. This is how a reference's pixel sizes become numbers you can put in a config.
- `--bg X,Y` — where to sample the background (default: top-centre). Sample the *page*, not a card.
- `--threshold N` — channel-sum distance from the background that counts as painted (default 10).
  Raise it when a fill is nearly background-coloured; lower it to catch a faint fade.

One thing to expect: it decides "painted" by distance from the background, so **content the same
colour as the background reads as a gap**. White label text on a blue button splits that button
into several runs; take the extent (first start to last end) rather than the longest run. The same
property is what makes it useful — it is how a connector fading out onto the page colour was caught.

Stdlib only, 8-bit non-interlaced PNG — what headless Chrome writes. It reads any PNG, so point it
at the user's reference screenshot as readily as at your own render, and compare the two.


## `test-audit-flow.py` — the calibration suite for `flow-audit`

Runs `skills/flow-audit/references/audit-flow.py` as a **subprocess**, never as an import, so
nothing writes a `__pycache__` into `references/` — the copy-install path would ship it.

Every case asserts a direction, because a check that only ever stays quiet is not a check:

    FIRES   — an injected defect must be reported, at the stated severity
    SILENT  — a real shipped export must produce nothing for that check

The corpus is the six flow configs in `fixtures/`. `catalog-fixture.json` is the product
catalog the audit compares them against, and it lives **beside** this README rather than in
`fixtures/` on purpose: `fixtures/` is flow-configs only, and four separate consumers walk it
assuming that. Putting the catalog there broke three of them.

Calibration state per check — including which are proven to fire on real data and which are
only proven silent — lives in
[checks.md](../skills/flow-audit/references/checks.md), along with every false-positive trap
the checks were written against.

## `test-flowkit.py` — the guardrail on the authoring helpers

`skills/flow-generator/references/flowkit.py` is shipped skill content: the mechanical half of
authoring a config. A shape helper that has drifted from the format is worse than no helper,
because it is confidently wrong at scale — so it does not ship without this.

164 checks, in four groups:

- **The invariant it exists for.** `hierarchy` and `map` hold the same id set, no id twice, no
  leftover `_children`, and `flatten` *raises* on a duplicate id rather than silently dropping an
  element.
- **The traps, as assertions.** Fills are arrays (v10), `_meta.screens` stays empty because it is
  builder-owned, a purchase buys `<group>.selectedProduct` rather than a const, a product carries
  the system `selected` state, and `opacity` is a percentage.
- **The capability gaps, as assertions.** Every helper added because its absence *was* the missing
  capability — an author reaches for what the module exposes. `switch_rich()` is the newest and the
  one with a service measurement behind it: it emits conditional text (the copy a personalization
  payoff is made of) in the export-verified shape, and `config()` refuses a predicate naming
  nothing, because that half is compiled and fatal while a `variable` span in the same prop merely
  renders its token. Also asserted: `spinner()` fixes `icon.type` to `custom` (a phosphor spinner
  is a 422), `footer()` refuses a `position`, `screen()` refuses two footers and a
  `footer` + `scrollable: false` pair, and a theme hex outside `#RRGGBB` raises.
- **The bug it was built to kill.** Three build scripts once had three `runs()` helpers that agreed
  on the name and disagreed on what a tuple meant — one read `('var', id)` as a variable node, one
  read `(text, colorId)` as a coloured span, one crashed. Copying a call between them produced the
  wrong node type silently and still published. So the test asserts `Var` becomes a variable node,
  `Span` becomes a text node, and a **bare tuple raises**.

Then it puts the whole document through `schema-check.py`, and skips rather than fails if that
gate is unavailable. Beyond this test, flowkit's output has been rendered through
`flows config preview` and looked at — a schema pass is not proof that anything draws.

## `test-snippet.py` — the guardrail on save/reuse

`skills/flow-generator/references/snippet.py` (`extract`/`plan`/`graft`) is shipped skill
content, same standing as `flowkit.py`. 187 cases, mostly run against the script as a
subprocess (a few object-identity properties are unobservable across a subprocess boundary and
are checked in-process instead, guarded the way `test-flowkit.py` guards its own import).

What it calibrates: the three-way dependency resolution (reuse / adopt / carry) for colours,
typography presets, fonts, icons and custom variables; the path-keyed-not-value-keyed rewrite
(`tabs-paywall.json`'s group named `tabs` next to an element *typed* `tabs`); id collision
re-minting; and all four snippet kinds. The last case in the suite is the graft's actual oracle:
it runs a real `graft` output through `skills/flow-generator/references/verify-config.py` as a
subprocess and asserts the result is verify-clean, or every remaining `ERROR` was already named
in the plan's `NEEDS YOU`. Red means either a resolution rule regressed, or a graft introduced
breakage `plan` did not predict.

```bash
python3 tests/test-snippet.py
```

## `schema-check.py` — validating against the published schema

```bash
python3 tests/schema-check.py tests/fixtures/*.json                    # summary per file
python3 tests/schema-check.py --baseline live.json edited.json         # only what YOUR edit caused
python3 tests/schema-check.py --verbose --refresh config.json          # every error, re-fetch schema
```

Fetches the schema from `https://schemastore.adaptybuilder.com/latest.json` and caches it for a day
at `$TMPDIR/adapty-flow.schema.json` — the same path and lifetime the official
`validate-with-schema.mjs` uses, so both share one download. Needs `jsonschema`. (A default
`Python-urllib` User-Agent gets a 403 from that host, hence the explicit one.)

**Pass `--baseline` whenever you are checking an edit.** The schema tracks the newest
`schemaVersion` and most live flows are older, so an unbaselined run on a v9 flow reports every
pre-existing mismatch. Measured on `onboarding-quiz-paywall.json`: **28 errors unbaselined, 0
baselined against itself**, and a single deliberately broken `width.type` surfaces as exactly one
finding. Without the baseline that finding would have been one line in twenty-nine.

**Two checks, not one.** `flows config validate` (stable from `adapty` 0.8.0, endpoint live in
production) answers *is this publishable* — it runs the real transform service, so it sees stranded
references — and skips most prop shapes: it accepts `fill: "banana"`. This answers *are the props
well-formed* and knows nothing about publishability. Neither is evidence about the other. Coverage
both ways: [validate.md](../skills/flow-generator/references/validate.md).

It suppresses one class of error the schema creates by construction: expression nodes
(`JSONVariable` / `JSONConstant`) are a `oneOf` over two **identical** permissive branches, commented
*"shape intentionally opaque, validated by the transformer"*, so every value matches both and `oneOf`
always fails. That fires on every `purchase` payload in real builder exports too. The count is still
reported.

## `mobile-preview-check.py` — the device-preview link

Runs [`mobile-preview.mjs`](../skills/flow-generator/references/mobile-preview.mjs) over every
fixture and asserts the URL the Adapty app receives. The link is pure string construction, so
unlike the rest of phase 5 it is completely checkable locally — no network, no auth, no device.

It runs without `--qr`, so `qrcode` is not required; the image path is exercised only when the
dependency happens to be installed at `~/.cache/adapty-flow-qr`.

It also guards the output shape. The markdown image path must be **relative** to `--md-base` — an
absolute one is what a client refuses to render — and **no path may print half-block characters**,
with `--terminal` staying rejected. A character-art QR was built twice and removed twice; the
findings that settled it are in
[preview.md](../skills/flow-generator/references/preview.md#why-there-is-no-terminal-qr-after-two-attempts-at-one).

Two regressions are the reason it exists, both invisible against real data:

- **A percent-encoded `locales` separator.** Rebuilding the query with `URLSearchParams` turns the
  comma into `%2C`, and the Adapty app is only known to accept the builder's literal comma.
- **`defaultLocale` passed through as `current_locale`.** It holds a locale *id*; the link carries
  a *code*. Every fixture in the corpus and every live flow checked has `id == code`, so the
  synthetic case in this file is the only coverage that distinction has.

Both were injected and confirmed to turn the check red before it was committed.

## `preserve-builder-state.py` — do not clobber the builder's own work

```bash
adapty flows config get --app $APP $FLOW --json > live.json
python3 tests/preserve-builder-state.py live.json regenerated.json
```

`config update` replaces the whole config. A script that rebuilds a config from source emits
`_meta.screens: {}`, which silently destroys product attachments made in the Flow Builder — and
`flowProductId` cannot be recomputed, so the next publish 422s and the user redoes the pass.

Run this between building and writing whenever the config was *regenerated* rather than *patched*.
It carries `_meta.screens` per surviving screen id (and uploaded `_meta.fonts` if the new config has
none), and reports what it carried, what was already authored, and what it dropped because the screen
no longer exists — the last one being legitimate but worth seeing.


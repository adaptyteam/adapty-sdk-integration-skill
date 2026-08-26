# Adapty Flow config — schema, invariants, traps

Everything here is a fact about the flow config JSON, verified against three real
`schemaVersion` 9 exports. Facts that hold in only some of them name which. Nothing here is
a procedure — the structure is visible in the file you are holding, so read it there.

Three exports are the corpus, referred to by short name throughout:

| Name | What it is |
| :--- | :--- |
| `quiz` | 5 screens — welcome → single-choice quiz → two genre branches → paywall. One reusable component, one declared custom variable, stock theme, two products. |
| `timer` | 3 screens, a countdown timer, four uploaded custom fonts, `status: "draft"`, no products. |
| `comparison` | 1 screen, comparison-table paywall, one custom typography preset, one product. |

`timer` and `comparison` carry the **same** `id` and differ in `status`. They are the draft
and the published version of one flow — see [Flow status](https://adapty.io/docs/builder-save-publish.md).
That is the evidence that `id` names the flow, not the document — which is also why the CLI
takes the flow id as an argument and not from the file. See
[Browser export versus CLI config](#browser-export-versus-cli-config) below.

All three carry exactly one locale (`en`). A `values` map with two or more keys is therefore
inferred from the field's shape, not observed.

## The envelope

Ten top-level keys. All ten are present in all three exports, and no eleventh key was
observed.

| Key | Shape | Notes |
| :--- | :--- | :--- |
| `id` | UUID | Identifies the **flow**, not the document. Two exports in the corpus share one. The CLI takes the flow id as a command argument, so this is not what routes a write. |
| `status` | `"draft"` \| `"dirty"` \| `"publication_failed"` \| `"published"` | **Present in a browser export, and not part of the CLI config document — see below.** Four values observed on the envelope: `draft`, `dirty` (a save over a flow that already has a published version — the draft has diverged from what users see), `publication_failed` (a publish attempt that the transform service rejected), and `published`. The dashboard shows six statuses (Draft, Dirty, Publishing, Failed, Published, Archived); a saved-but-unpublished edit over a live flow is the "Dirty" state, not a third JSON value. |
| `schemaVersion` | `9` in every export here; **also seen absent, `2`, `6`, and `8.0`** | Not a constant, and not always an integer — the transformer's own front-format fixtures omit it in 21 of 30 files and carry `8.0` as a float in another. **Carry whatever the input has, unchanged, and do not add one if it is missing.** Never rewrite it: you cannot know what a different number changes, and a version you invented is worse than a version that was absent. |
| `components` | `{}` or `{"pb_XXXXXXXX": {map, hierarchy}}` | Reusable blocks with the same `{map, hierarchy}` shape as a screen's `elements`. Referenced from a screen hierarchy as `{"id": "pb_XXXXXXXX", "type": "global"}` — a hierarchy node with no entry in that screen's `map`. Empty object in `comparison`. May be present and referenced by nobody. |
| `screens` | `[{id, props, caption, elements: {map, hierarchy}, selectableGroups}]` | Array order is flow order; `screens[0]` is the entry screen. All five keys present on every screen in all three exports. `selectableGroups` is `[]` on screens with no groups, never omitted. `hierarchy` is a single rooted node — see below. |
| `locales` | `[{id, code, name}]` | e.g. `{"id": "en", "code": "en", "name": "English"}`. The `id` is the key used in every `values` map. |
| `defaultLocale` | a locale `id` | Must name an entry in `locales`. |
| `variables` | `[{id, name, valueType}]` | **Custom, app-supplied variables only** — `{"id": "var_ddvg4jeg", "name": "app.permission.location.allowed", "valueType": "boolean"}`. Built-ins are never declared here. `[]` in `timer` and `comparison`. |
| `theme` | `{typography: [{id, name, settings}], colors: [{id, name, light, dark?}]}` | Per-project design system. **Not a fixed vocabulary** — see [Shape traps](#shape-traps). `colors[].dark` is present only where dark mode was configured (`quiz` only). |
| `_meta` | `{icons, fonts, screens}` | `icons`: `[{name, weight, raw}]`, `raw` being literal SVG markup. `fonts`: `[{id, name, url, iosName, androidName}]`, `[]` in `quiz`. `screens`: an object keyed by screen id, holding that screen's declared products — `{"<screen-id>": {"products": [{"id": "<product-uuid>", "flowProductId": "<flow-product-uuid>"}]}}`. Screens with no products have no entry at all. **`screens[].products[]` is builder-owned: carry it through untouched or not at all.** [`products.md`](products.md) owns the rules and the reasoning. |

`elements.hierarchy` — and a component's `hierarchy` — is **one node, always
`{"id": "root", "children": [...]}`**, and `root` has no entry in `map`. True of 9 of 9
screens and 2 of 2 components. Nesting is arbitrarily deep, and a node takes one of **three**
key-sets across the corpus's 257 hierarchy nodes:

| Node | Count | Notes |
| :--- | :-- | :--- |
| `{"id": "el_…", "children": [...]}` | 126 | Includes all 11 `root` nodes. **7 of the 126 carry `children: []`** — an empty collection, not a missing key: 6 in `timer`'s screens and 1 in its component. |
| `{"id": "el_…"}` | 130 | Childless, `children` omitted entirely. |
| `{"id": "pb_…", "type": "global"}` | 1 | The component reference. Carries no `children` key. |

So childless is written both ways in real exports, and neither is canonical — see trap 6. A new
screen that omits the `root` wrapper, or that makes `hierarchy` an array of nodes, does not
render.

An element inside `elements.map` has at most seven keys: `id`, `type`, `props` always;
`states` on every screen element in all three exports and on no element inside `components`;
and `caption`, `interactions`, `propsByState` optionally. `props` content varies by `type`.

`flowProductId` is a UUIDv5 — the version nibble is `5` in both exports that declare products
(`timer` declares none, so the evidence is 2 of 3) — so it is **derived** from something, not
random. Never invent one: carry the pair through from the source export, and if a product must
be added, the user attaches it in the Flow Builder.

## Browser export versus CLI config

The corpus above is three **browser exports**. What `adapty flows config get` returns is an
envelope around the same document:

```json
{"config": { … the ten keys above … }, "remote_configs": …, "status": …, "updated_at": …}
```

Three differences, each measured on a live round trip:

- **`status` and `updated_at` belong to the envelope, and the API owns both.** `status` put
  inside `config` is **discarded** on save; `updated_at` is an epoch integer and doubles as the
  optimistic lock. So the two envelope keys a browser export shows top-level are not yours to
  write — `SKILL.md` owns what to do instead.
- **Unknown keys survive when nested and are dropped at the top level of `config`.** A key the
  API does not recognize anywhere inside `screens`, `props`, `theme` or `_meta` comes back
  byte-identical; the same key added beside `screens` does not come back at all. Preserve
  unrecognized nested keys as a rule, and never park scratch data at the top level.
- **A round trip is otherwise faithful.** 108 of 108 elements, `selectableGroups`, the `fill`
  array form, every element `id` and all six actions returned unchanged from a 108-element
  screen. Fidelity is not the risk; what the builder will *render* is (trap 10).

## Invariants

Twelve referential invariants, verified to hold in all three exports. Each is a place an edit
silently produces a file that parses cleanly and is wrong. One exception to "verified":
invariant 11 is **vacuously** true at one locale, since the corpus is single-locale — it is
the one invariant on this list that a real multi-locale export has never exercised.

| # | Invariant | Broken by | If violated |
| :-- | :--- | :--- | :--- |
| 1 | Every key in `elements.map` equals that element's own `id` | copying or duplicating an element | The Flow Builder resolves elements by map key; a mismatch makes the element unaddressable. |
| 2 | On a **screen**, `hierarchy` references only ids present in `map`, and every id in `map` appears exactly once in `hierarchy` | adding or removing an element | A hierarchy id absent from `map` renders nothing. **Two hierarchy ids legitimately have no `map` entry, and both must be excluded before you check anything:** `root`, the mandatory wrapper node, on every screen and every component; and any `{"id": "pb_…", "type": "global"}` node, which points into `components` instead. Counting either as a violation reports false corruption — `root` on all 9 screens, `global` once in the corpus. The bijection itself holds for every screen but **not inside `components`**: `timer`'s component has a `progress-bar-loader` in its `map` that no hierarchy node references. A `map` entry the hierarchy never reaches is therefore not proof of corruption and is not yours to prune. |
| 3 | Every `navigate` action's `payload.screen` names an existing screen — **including targets nested inside a `conditional`'s `cases` and `default`**, which is where a dangling one hides, since the branch that reaches it may never be the one you looked at | **screen deletion** | **Publish blocker.** A Navigate action with a destination that no longer exists is an incomplete interaction, and [Common issues](https://adapty.io/docs/flow-common-issues.md) names it explicitly: it "also occurs when the destination screen is deleted after the action is set up." The flow will neither preview nor publish. |
| 4 | Every `product` element's `props.product.id` is declared in `_meta.screens.<thatScreenId>.products[]` | moving a product element to another screen | **Publish blocker** — a product element with no product attached. Declaration is per screen, so a moved element arrives **unattached on its new screen**, and no edit you can make to the JSON clears that. There is no re-keying fix: see [`transforms.md`](transforms.md#decisions-you-must-disclose) decision 2 for the exits, and [`products.md`](products.md) for why binding is not yours to write. |
| 5 | A price variable resolves by **one of two forms**, and which one decides what it must name. Product-relative — `<productUUID>.prod_price_per_*`, head is a product id declared in `_meta.screens` (in the corpus, always on the same screen that reads it). Group-relative — `<groupId>.selectedProduct.<field>`, head is a `product`-typed `selectableGroups` id, **not** a product id | copy rewrite, moving a screen or element | The price renders empty. Nothing fails loudly. **Validate the head against the form, or you generate a false positive:** checking the first segment of a group-relative variable against the product list rejects a valid file and invites an agent to "repair" correct work. Provenance, precisely: the product-relative form is the only one in the corpus. The **field names are documented** — [Element variables](https://adapty.io/docs/onboarding-variables.md) lists `prod_price` alongside `prod_price_per_{day,week,month,year}`. What is unverified is the group-relative **reference syntax** `<groupId>.selectedProduct.<field>`: it appears in no export and on no docs page, only in a live Flow Builder screen. **That syntax is now device-verified and safe to author:** on a real device a root-level line reading `<groupId>.selectedProduct.prod_price` resolved to a real price and **changed as each card was tapped**, so it tracks the live selection rather than resolving once. `prod_price_per_month` on an **annual** product likewise resolved to a real derived figure, so a per-month field does not require a monthly product. Preserve it verbatim where you find it, and authoring it is fine. [`products.md`](products.md) owns the handling rules. |
| 6 | Every `selectableGroups[].id` has at least one member element carrying that `groupId`, and every `groupId` in use has a declared group | branching edits | A group with no members and a member with no group are both broken selection state. Groups are per screen and typed (`single_choice`, `product`). Two team-stated naming rules: a `groupId` must **not start with a digit** (`1a` generated invalid JavaScript and blocked publish), and should be **unique across the flow**, not merely its screen — two screens sharing `"products"` broke selection rendering. |
| 7 | Every `const` compared against `<groupId>.selectedOptionId` matches some member's `customId` | branching edits, renaming an option | The case never matches, so every user takes the `default` branch. Silent — the flow still routes somewhere. |
| 8 | Every `colorId` and every `font.preset` resolves in **that file's own** `theme` | pasting a screen from another flow | **A hard 422, confirmed.** A screen pasted in from another flow kept `font.preset: "button-label"`, a preset the destination theme does not define; device preview returned `unknown_font_preset` as **severity `error`**, once per text element, blocking the whole flow. `config update` had saved it without complaint. So this is a publish blocker, not a cosmetic drift — and `references/verify-config.py` catches it, which is the check earning its place. Fix by repointing to a preset the destination theme has, not by adding the source's name to the theme. Never validate these against a remembered list of built-in names — see [Shape traps](#shape-traps). |
| 9 | Every `family.id` resolves in `_meta.fonts` — via **both** reference paths: an element's `props.font.family.id`, and `theme.typography[].settings.family.id` | pasting a screen from another flow, editing or deleting a typography preset | Unresolvable font reference. **Check both paths or you check nothing**: element-level refs number 7 in `timer` and 0 in both `quiz` and `comparison`, so in `comparison` all three declared fonts are reached only through theme presets, and in `timer` the two paths together are what reach all four. A check that reads only element props would find `comparison`'s `_meta.fonts` entirely unreferenced and could license deleting them. Resolving here also does not mean the font ships — trap 7. |
| 10 | Every `(name, weight)` icon pair used by an `icon` element appears in `_meta.icons` | adding an icon | `_meta.icons[].raw` carries the literal SVG markup the renderer draws, so an unlisted pair has nothing to draw. `raw` cannot be synthesized. |
| 11 | Every locale in `locales[]` has an entry in every `_localizable` `values` map | adding a locale | The field falls back or renders empty for that locale. There are three localizable families, not one — trap 1. |
| 12 | Every variable **consumer** still has a **producer**, and *which* producer depends on the form: `<inputCustomId>.value` needs the `text-input` carrying that `customId`; `<groupId>.selectedOptionId` needs a group with that id; `<productUUID>.prod_*` needs that product declared; `<groupId>.selectedProduct.<field>` needs a `product`-typed **group** — resolve it against `selectableGroups`, never against the product list, or you repeat invariant 5's false positive | **screen deletion**, moving an element between screens | Breaks the **opposite way** from invariant 3: the reference survives and its producer dies, so nothing on the screen you edited looks wrong. In `quiz`, the `text-input` with `customId: "name"` lives on the Quiz screen while `name.value` is read on three *other* screens (both genre branches and the paywall) — deleting Quiz strands all three, and none of them is the screen that was touched. |

Invariants 3 and 4 are the two whose violation blocks publishing. The other publish
blockers in [Common issues](https://adapty.io/docs/flow-common-issues.md) are not
referential and so are not invariants: any incomplete interaction (a `purchase` with no
product, a `conditional` with no operator or value), a screen with no elements, and invalid
remote-config JSON — which blocks even saving the draft.

A `const` compared against `products.selectedProduct` is **not** covered by invariant 4 and
is not referentially checked. `quiz` carries one such predicate whose product UUID is
declared on no screen; its branches both resolve to `{"type": "nothing"}`, so it is inert.
Report it and move on. Repairing it changes routing that nothing asked you to change.

### Three warnings, not errors

All three appear in the real corpus. Do not "fix" any of them — report and move on.

- **A component defined in `components` and never referenced as `global`.** `timer` carries
  `pb_GgGITFkb`, referenced by no screen.
- **A declared-but-unreferenced entry in `variables[]`.** `quiz` declares
  `app.permission.location.allowed` and reads it nowhere.
- **A declared-but-unreferenced `theme` entry.** `timer` leaves 4 typography presets
  (`button-label`, `caption`, `h2`, `small-label`) and 8 colors unreferenced; `quiz` leaves 4
  colors unreferenced. A *custom* preset reaches the same state when an edit removes its last
  use — one live flow outside this corpus carries an unreferenced `typ_MgNum`. Invariant 8 runs
  one way only: every reference must resolve into the theme, never the reverse. A spare theme
  entry is not dead code you may prune.

## Shape traps

Each of these is a place where an edit produces a file that parses, validates against the
invariants above, and is still wrong.

### 1b. `_localizable` does NOT mean one value shape — a placeholder takes a plain string

Two fields both marked `"_localizable": true`, two different value shapes:

```json
"content":     {"values": {"en": [{"type": "paragraph", "content": [ … ]}]}, "_localizable": true}
"placeholder": {"values": {"en": "Age"}, "_localizable": true}
```

`text.props.content` holds an **array of paragraph blocks**. An input's `placeholder` —
`text-input`, `number-input` and the rest of that family — holds a **bare string per locale**.
The schema allows `anyOf: [string, rich-node array, ILocalizable]`, which reads as permissive
and is not: handing paragraph blocks to a placeholder **kills the entire screen**, which renders
as `Preview failed to render.` and takes every other element on it down.

Measured by bisection, holding everything else constant:

| `placeholder` | result |
| :--- | :--- |
| `{"values": {"en": [{"type":"paragraph", …}]}}` | **whole screen fails to render** |
| `{"values": {"en": "Age"}}` | renders |
| `"Age"` | renders |

Neither `verify-config.py` nor the official v10 schema catches it — both pass the broken config.
Only the render does, which is trap 10's lesson with a louder failure: **one wrong value shape on
one prop is a screen-level outage**, not a local defect. So a helper that builds rich text is the
wrong tool for a placeholder, and reusing one across both families is how this project broke two
screens at once.

### 1. `text.props.content` has two shapes, and there are three localizable families

A bare string, or a localizable object. Both are legal. `quiz` has 6 bare and 37 localized;
`timer` and `comparison` have none bare.

```json
"content": "Next"
```
```json
"content": {"values": {"en": [{"type": "paragraph", "content": [ … ]}]}, "_localizable": true}
```

A bare string has no locale and cannot be translated in place. Preserve whichever shape you
found. Both shapes exist in real exports and `flows config update` saves either, but whether the
builder **renders** a field converted from bare to localizable is unverified — nobody has opened
one. So a conversion is a decision to disclose, not to make quietly.

Localizable fields are marked by `"_localizable": true`, and the marked key is not always
`content`:

| Family | Key | `values.<locale>` holds | Count in `quiz` |
| :--- | :--- | :--- | :-- |
| `text` | `props.content` | an array of block nodes | 37 |
| `image` | `props.image` | `{"id": "…", "url": "<asset-url>"}` | 4 |
| `text-input` | `props.placeholder` | a plain string | 1 |

42 localizable fields in `quiz`, of which 5 are not text. Note that `image` also appears as a
**non-localizable** key: a `fill` of `"type": "image"` carries a bare
`"image": {"id": …, "url": …}` with no `values` and no `_localizable`. Same key name,
different position, different shape.

### 2. Rich text is two levels of node, and two of the three inline types carry no text

`values.<locale>` for a `text` element is an array of **block** nodes. Only `paragraph` was
observed (38 in `quiz`, 18 in `timer`, 22 in `comparison`). Each block's `content` is an
array of **inline** nodes, of which exactly three types exist:

```json
{"type": "text",     "text": "…", "attrs": {"bold": false, "italic": false, "underline": false, "strikethrough": false}}
{"type": "variable", "attrs": {"variableId": "<productUUID>.prod_price_per_year"}}
{"type": "token",    "attrs": {"token": "timer_minutes"}}
```

**A `variable` span takes no formatting of its own** — you cannot strike or bold the price
without styling the whole line (team-stated). The device-verified strikethrough recipe is a
*separate* `text` element holding the other product's price variable, with strikethrough and colour
applied at the **element** level, not in rich text — its known costs: the hidden donor product adds
invisible scroll, and deleting it takes the visible price down with it.

`variable` carries prices and user input; `token` carries countdown digits. Neither has a
`text` key, and per
[Style variables](https://adapty.io/docs/onboarding-variables.md) formatting cannot be
applied to a variable at all — which is why they carry no `attrs` marks.

A paragraph rebuilt from its rendered plain text still renders and still looks right in the
export — but a flattened `variable` node is a hardcoded price that has stopped tracking the
product, the locale, and the store's currency, and a flattened `token` is a frozen number
where a live countdown was.

### 3. `theme` is per-file, and `font` overrides may carry no preset at all

`theme.typography[].id` and `theme.colors[].id` are the only valid values for `font.preset`
and `colorId` in that file. Built-in names (`h1`, `h2`, `h3`, `button-label`, `body`,
`caption`, `small-label`; `white`, `gray-100`…`gray-900`, `accent`) coexist with custom ids
prefixed `typ_` and `clr_`, and **the built-ins can be deleted**: `comparison` has no `h3`
and adds `typ_RPXzQ8BE` in its place, and replaces every stock color with `clr_` ids plus
`accent`. Validate against the file. A hardcoded list of built-in names is already wrong for
one of the three exports in this corpus.

**Four** key-sets occur for a color, in the same positions:

```json
{"type": "color-style", "colorId": "gray-800"}
{"type": "color-style", "colorId": "white", "hex": "", "opacity": 100}
{"type": "hex", "hex": "#FFFFFF"}
{"type": "hex", "hex": "#FFFFFF", "opacity": 100}
```

The second is the trap: a `color-style` carrying an **empty** `hex` alongside its `colorId`.
It occurs 25 times in `quiz`, every one of them on a `text` element's `props.color`. `type`
is what selects which field is authoritative, so `"hex": ""` is not dead weight to tidy away
— deleting it, or filling it in from the resolved `colorId`, is the same class of unrequested
edit as trap 6. Leave all four shapes exactly as found.

And an element-level `font` is either a preset reference or a full override with **no
`preset` key**:

```json
"font": {"preset": "h1"}
"font": {"family": {"id": "<font-uuid>", "type": "user"}, "size": 32, "weight": "semibold"}
```

Do not add a `preset` to the second form to make it look like the first.

### 4. Built-in variables are referenced but never declared

`variables[]` holds custom app-supplied variables only. These four families are used by
`variableId` and appear in no declaration anywhere in the file:

| Reference | Produced by |
| :--- | :--- |
| `<groupId>.selectedOptionId` | a `selectableGroups` entry plus its member `customId`s |
| `<groupId>.selectedProduct` | the `product`-typed selectable group of that id |
| `<groupId>.selectedProduct.<field>` | the same group, extended by a product field — resolve the head against `selectableGroups`, **not** against the product list |
| `<productUUID>.prod_price_per_{day,week,month,year}`, and the rest of the product set | a product declared in `_meta.screens` |
| `<inputCustomId>.value` | a `text-input`'s `customId` |

Adding any of them to `variables[]` is wrong.

The group id is not fixed at `products` — it is whatever that screen's `selectableGroups`
declares. The corpus uses `products`; a live builder screen used `products2`. Read it from the
file.

**Unknown:** how a *custom* `variables[]` entry is referenced from a `variableId` — by its `id`
(`var_ddvg4jeg`) or by its `name` (`app.permission.location.allowed`). The corpus cannot
settle it: the one declared custom variable is read nowhere — that is the second warning under
[Invariants](#invariants), and it is why this is unobservable. Do
not introduce a reference to a custom variable on a guess; if a transform needs one, say the
form is unverified and let the user wire it in the Flow Builder.

The JSON's names are not the dashboard's names. [Element
variables](https://adapty.io/docs/onboarding-variables.md) documents the UI as offering
`selected_id` and `selected_title`; the JSON writes `selectedOptionId`. Take the string from
the file, never from a docs table.

### 5. An asset you have no FILE for is an EMPTY values map, never a made-up URL

**If you were given a file, upload it** — `flows media upload` returns a live CDN URL to bind, and
the shapes it binds into (per-locale `values` map on an element, flat inside a `fill`) plus the
`id`-is-a-string rule live in [media.md](media.md). This trap governs what is left after that: an
image nobody has a file for, an SVG (upload returns `http_500`), or a video (no path at all).

You still cannot *create* media. An `image` whose asset does not exist is written with the
localizable wrapper intact and **nothing in it**:

```json
"image": {"_localizable": true, "values": {}}
```

Not a placeholder URL, not `example.com`, not a plausible-looking
`public-media.adapty.io` path — and that last one matters more now that real uploads live on
exactly that host: a `public-media.adapty.io` URL is legitimate **only** if `flows media upload`
printed it in this session. Copying one from another flow, from a fixture, or from the shape of
one you saw is an invented URL wearing the right costume. An invented URL is worse than an empty map three ways: it looks
resolved so nobody uploads anything, it silently fails at runtime rather than showing as
unset in the builder, and a fabricated `id` collides with the real asset namespace.

The same holds for the asset `id` — omit the whole entry rather than inventing a number.
Report every element left with an empty `values` map in your handover, so the user knows
exactly what to upload.

**A styled placeholder beats a lookalike substitute — never stand an emoji in for a designed
glyph.** When the reference uses icons you cannot author faithfully, the ladder is: author a
monochrome SVG and render-verify it ([patterns.md](patterns.md)); if the glyph is **multicolour or
gradient**, which `fill="currentColor"` cannot express, **draw it, rasterize it on a transparent
background and upload it** ([media.md → When a graphic cannot be an element](media.md)) — and say
you drew it; failing both, ship an **empty styled `image` element**; never an emoji or a text
glyph. Nothing with **text** in it, nothing **selectable**, and nothing that must follow the
**theme** may become a bitmap — those three are the exclusions media.md owns. The reason is what each one tells the
person who opens the flow: a placeholder is visibly unfinished and asks to be filled, while an
emoji looks finished and quietly ships a different design — and nothing downstream flags it,
because a substitute is structurally valid. This was the user's own call on a build where four
emoji had passed every check (2026-08-24). Emoji carry a second cost too: they are the one defect
class with no preview-side tell at all (see [preview.md](preview.md)).

**Style the placeholder element completely, so the upload lands styled.** The empty values map
is only the *content* half; `IImageElementProps` carries the presentation — `borderRadius`,
`objectFit` (`"fit"` | `"cover"`), `_aspect`, `border`, fixed `width`/`height` — and those are
yours to author now, on the `image` element itself, not on a wrapper. A circular avatar is a
92×92 image with `borderRadius` 46 and `objectFit: "cover"`; leave those off and the user who
uploads the photo gets an unstyled square they have to fix by hand, which quietly hands your
layout work back to them (user-required rule, 2026-08-24). A parent stack's radius is not a
substitute — style the element the asset will actually fill.

### 6. Optional keys are inconsistently present and must not be normalized

Real exports disagree with each other on every one of these, so a "missing" key is not
missing:

| Key | Observed |
| :--- | :--- |
| `border.style` | present on all 24 `border` objects in `quiz`, absent from all 24 in `comparison` (`timer` has none) |
| `color.opacity` | inconsistent within a single file: in `quiz`, 44 colors carry neither `hex` nor `opacity`, 40 carry `hex` without `opacity`, 22 carry both, and 25 carry `colorId` + empty `hex` + `opacity` |
| `color.hex` on a `color-style` | present-but-empty 25 times in `quiz`, absent everywhere else — see trap 3 |
| `children` on a childless hierarchy node | present-but-empty (`children: []`) on 7 nodes — 6 in `timer`'s screens, 1 in its component — and omitted on the other 130. Stripping the empty array is the same edit as stripping an empty `padding: {}` |
| `interactions` | omitted on most elements, `[]` on many, populated on a few — all three states in every export |
| `padding` / `margin` | sometimes `{}`; `timer` has 2 empty `padding` and 3 empty `margin` |
| `statusBarTheme` vs `statusBar` | two distinct screen keys. `statusBarTheme` is `"system"` or `"light"` and is on every screen; `statusBar` is a boolean and appears on 1 screen of `timer` and 1 of `comparison` |
| `progressBar` | screen prop, present on 1 of 5 screens in `quiz`, all 3 in `timer`, absent from `comparison` |
| `caption` | on every screen; on only some elements (22 of 120 in `quiz`) |
| `propsByState` | absent from `timer` entirely |
| `theme.colors[].dark` | only where dark mode was configured — `quiz` only |

Adding a key to make two elements match, or dropping an empty `{}` because it looks
redundant, is an unrequested edit to a document you will hand back to a human.

### 7. Both screen id forms are legal

A bare UUID and `scr_XXXXXXXX` both occur, sometimes in the same file: the first screen of
`quiz` is `a4895438-…` while its other four are `scr_…`; `comparison`'s single screen is a
bare UUID. Element ids are `el_`, components `pb_`, interactions `int_`, actions `act_`,
custom variables `var_`.

**Never rewrite an existing screen id.** `navigate` payloads point at them, and so does
`_meta.screens`. A new screen takes the `scr_` form.

### 8. Custom fonts do not ship with the flow

Per [Save & publish](https://adapty.io/docs/builder-save-publish.md), a custom font file must
be in the app bundle or users see the system fallback. `_meta.fonts[].url` records the
uploaded file; its presence in the export is not what makes the font available on device.

**And a font cannot be added from here at all — uploading one is a manual Flow Builder action.**
There is no CLI command for it (`flows media upload` is media-only and not live in production
anyway), and hand-authoring a `_meta.fonts` entry fabricates an asset `id`/`url` pair, which is
trap 5 with a typeface. So when a design needs a font the account does not have, the ask is
two-step and both halves are the user's: upload the font in the builder, then tell the agent —
who can then point `theme.typography` presets or element `font.family` at the real id the
upload minted.

Introducing a custom-font reference is therefore a **runtime** footgun, not a publish error:
the flow publishes, and the text renders in the wrong typeface on devices whose bundle lacks
the file. Report it; do not block on it.

A reference can enter by either of invariant 9's two paths, and the second is the quiet one:
an element's `props.font.family`, or a **typography preset** whose
`settings.family.id` points at an uploaded font. `quiz` declares no fonts at all
(`_meta.fonts: []`) and styles everything through presets that carry no `family`;
`comparison` reaches all three of its uploaded families *only* through presets. So changing
an element's `font.preset` can silently introduce a custom font, and a screen moved into
`quiz` loses its typeface by either path. See [Custom
fonts](https://adapty.io/docs/using-custom-fonts-in-flow-builder.md).

### 9. Offsets must resolve against an axis something defines — the parent for `absolute`, the screen for `fixed`

`position` is nearly always `{"type": "relative"}` — 234 of 246 elements. Every one of the
9 non-`relative` positions in the corpus is one of three patterns, and the pattern is what
carries the meaning:

| Pattern | Uses | Where |
| :--- | :-- | :--- |
| `absolute` with a **horizontal** offset only (`{right: 16}`) | 5 | Inside a **horizontal container whose vertical extent is already settled** — `alignV: "center"` in all 5, with `height: {"type": "fixed"}` in 4 (`quiz`) and `height: hug` plus symmetric vertical `padding` in 1 (`comparison`). Trailing icons and close controls in a sized bar. |
| `absolute` with a **vertical** offset only (`{top: 146}`) | 1 | A direct child of `root` (`timer`). Legal — `absolute` at `root` is not the problem. |
| `fixed` with `{left, right, bottom}` | 3 | Direct children of `root` (`timer`), each paired with `width: {"type": "auto"}`. The bottom-pinned CTA pattern. |

The generalization, for `absolute`: **supply an offset for the axis the parent does not
determine.** An
`absolute` element whose only offset is horizontal, in a parent that settles nothing
vertically, has no vertical anchor and falls back into flow order — it detaches from where you
meant to put it and lands wherever the flow carries it. That combination — horizontal offset
only, at `root`, no vertical offset — occurs nowhere in the corpus.

`absolute` and `fixed` are **not** interchangeable. `fixed` pins to the screen, and is what a
bottom-docked CTA uses; the three `fixed` uses all sit at `root` with all three of
`left`/`right`/`bottom`. Do not substitute one for the other to make an offset resolve.

**A fourth form exists, outside this corpus: both vertical offsets plus `height: {"type":
"auto"}`, which stretches the element between its anchors.** Provenance is one real builder export
(2 uses, both timeline rails) plus a render of it here, kept as `tests/fixtures/timeline-anchored.json`
— none of the four census exports carries the form, so it sits below the three patterns above but
above anything inferred. It is the only shape that follows a parent whose
height the *content* decides, and a **negative** `bottom` overshoots past the parent's edge, which
is how a rail reaches into the next row rather than stopping at its own.

All three parts are load-bearing, each isolated by removing it from one rendered row:

| Shape | Drawn |
| :--- | :--- |
| `{top: 10, bottom: -18, zIndex: -10}` + `height: auto` | stretches with the row, overshoots under the next element |
| the same, minus `bottom` | **collapses to nothing** — 108px of white where the element was |
| the same, with `height: fill` | stretches but stops **2px short** of its anchor |
| the same, minus `zIndex` | correct geometry, but paints **over** its siblings instead of behind |

`height: auto` therefore means nothing on its own — it is half of a pair, and the other half is the
anchors. `zIndex` lives *inside* `position`, not at the top level of props, and negative values
work. (An earlier note here said `zIndex` appeared in no real export; that export now exists.)
`flowkit.absolute()` emits the position object and raises on either broken pairing, and
`verify-config.py` warns on both, since neither the schema nor `validate` has any opinion on
layout and both misreadings render as "the line is too short".

Two further facts about the key itself: 4 `relative` positions in `timer` carry `left`/`top`
offsets, so an offset is not evidence of `absolute` (trap 6); and 3 elements — all inside
`components` — carry no `position` key at all, so its absence is not corruption either.

### 10. A config the API accepts can still be one the builder cannot open

The save endpoint validates the document, not the render. Two configs in this session passed
every invariant above, saved cleanly, round-tripped byte-intact — and left the builder unable
to open the flow. Both causes are invisible to every referential check:

| Cause | What it looked like | The rule |
| :--- | :--- | :--- |
| Six elements had no `states` key | A screen assembled the way `components` elements are written, where `states` legitimately never appears (see the seven-key element note above) | **Every element under a screen's `elements.map` carries `states`; `[]` is correct.** The absence is only legal inside `components`. |
| A tab group was declared `{"type": "tabs"}` | `tabs` is a real string in the builder transformer's source — a *source-level* constant, not a group type | Group `type` is one of the four in the vocabulary table. A tab group is `single_choice`. |

Neither is caught by `flows config validate` — re-measured against `adapty/0.8.0` in production:
that endpoint answers *publishable*, which both of these configs were. And neither is caught by `flows config preview`: both defects were
re-injected into a config known to render, and both still rendered, losing only a selected-tab
highlight. **The two well-formedness rows in `SKILL.md`'s Verify list are what catch these**, and
`references/verify-config.py` in this repo checks both mechanically. Preview earns its place on the
class these two are not: layout and spacing defects that are structurally perfect.

Both mistakes came from trusting the wrong kind of evidence. Order sources by what they prove:
a **rendering flow** proves a shape works; a **real export** proves it is written that way; a
**minimized test fixture** proves only what that one test needed — stripping props down to match
one broke the tabs render a second time; and a **string constant in source** proves nothing
about the format at all. When two sources disagree, the one that rendered wins.

### 10b. `layout.distribution` has FOUR modes, and only knowing one of them deforms every screen

`ILayout` is `{alignH, alignV, direction, distribution}`, all four **required**. The trap is not
the shape, it is the vocabulary:

| Key | Values |
| :--- | :--- |
| `distribution` | `{"type": "gap", "gap": N}` **or** `{"type": "space-between"}` / `"space-around"` / `"space-evenly"` — the spread forms carry **no** `gap` key |
| `alignH` / `alignV` | `start`, `center`, `end` |
| `direction` | `vertical`, `horizontal`, **`free`** |
| `clipContent`, `rtl` | booleans, optional |

**`space-between` on a screen root spreads a SHORT screen's content away from its bottom bar** —
give the root two children and the free space lands between them. It does **not** pin anything: a
bar that has to stay at the bottom while content scrolls past it is the `footer` element, whose
pinning is its own behaviour (measured 2026-08-26; the same props as a `stack` land below the
fold — [patterns.md](patterns.md)). Knowing only the `gap` form is what makes an author reach for
the workarounds instead, and both have failure modes this project shipped: a **docked** (`fixed`)
bar needs the screen's `padding.bottom` to reserve its exact height, and getting that arithmetic
wrong put a footnote underneath a CTA; leaving the bar **in flow** on a tall device leaves a dead
void below it, which is what a user sees as "the layout is broken everywhere". Measured 2026-08-24
across four screens: replacing dock-plus-padding with one `space-between` root removed both
defects and deleted the padding arithmetic entirely.

**A spread mode needs free space, so the container must have a definite height.** On a screen that
means `props.scrollable: false`; a scrollable screen's root is content-height, and a spread there
behaves like `gap: 0`. That is a real trade, not a detail — `scrollable: false` **clips** content
taller than the viewport, and the CLI preview cannot show it to you, because `--device` ids are not
enumerable (see [preview.md](preview.md)). So: **spread the short screens, scroll the tall ones**,
and decide per screen by rendering rather than by preference.

`flowkit.layout()`/`stack()`/`screen()` take `distribution='space-between'`. The helper emitted
only the `gap` form for its first release, and that alone is why the other three modes went unused
in real builds — the author reaches for what the helper exposes.

### 11. `opacity` on a colour is a 0-100 percentage, not a 0-1 fraction

```json
"color": {"hex": "#E8553C", "type": "hex", "opacity": 20}   // a 20% tint
"color": {"hex": "#FFFFFFD9", "type": "hex"}                // omitted = fully opaque
```

Write `"opacity": 1` intending "fully opaque" and you get **1%** — a colour so faint it reads as
absent. Measured on an identical magenta fill: `opacity: 100` and an omitted key both paint 27,956
coloured pixels; `opacity: 1` paints **zero** at full strength and a barely-detectable 1% tint.

Evidence for the scale, from real exports rather than inference: `opacity: 20` on a tinted card
background, and `opacity: 0` on a border that is deliberately invisible. Both only make sense on
0-100.

Two things make this expensive to diagnose:

- **Every check passes.** The value is a legal number, the colour resolves, `config update` saves it,
  and referential integrity is untouched. Only the render shows it.
- **It looks like a different bug.** An element whose fill silently vanished reads as "my edit did
  nothing" — or, in `propsByState.selected`, as "selection isn't working". This trap was originally
  written up in this repo as *"a raw hex in a fill is silently ignored"*, which was wrong: the probe
  that produced it changed the colour form and the opacity at the same time, and `color-style` has no
  opacity field, so it appeared to fix a problem it had merely sidestepped.

**Also note the two colour forms are not interchangeable in what they accept.** A `color-style`
reference (`{"type": "color-style", "colorId": "clr_X"}`) carries no `opacity`; if you need
translucency you need the `hex` form, and then the percentage applies. And `hex` accepts an 8-digit
value (`#FFFFFFD9`) carrying its own alpha, seen in a real export with no `opacity` key beside it.

### 12. A gradient that ends on the page colour shortens the element

A fade-out gradient whose last stop *is* the background makes the element's tail invisible, so it
renders shorter than it is. Measured: timeline connectors specified at the correct length ended
**14px short** of the next chip, once per row, because the gradient closed on the page's own
`#F1F1F4`. The config was right and every structural check passed; only the render disagreed, and
only under measurement — by eye it read as "the connectors are too short", which sends you off
resizing an element that was never the wrong size.

Ending a fade one step short of the background (`#EDE9F0` against a `#F1F1F4` page) restores it.
When something must *connect* two elements, verify by walking the painted runs down that column and
asserting **zero gaps** — never by looking.

### 13. `height: {type: "fill"}` collapses inside a hug-height parent

`fill` resolves against a parent with a definite height. Give it a `hug` parent and it collapses to
roughly zero rather than expanding to the sibling content's height. Measured on the same timeline:
switching a connector from `fixed` to `fill` — to make it stretch to whatever the row needed —
shrank it from 62 to a ~16px stub and crushed the row spacing. Inside a hug-height row, a stretch
has to be an explicit number.

**The better exit is to leave the flow entirely.** An `absolute` child of that row, anchored `top`
**and** `bottom` with `height: {"type": "auto"}`, stretches to the row's own height without any
number at all — trap 9's fourth form. That is what a timeline rail should be, and it is why
`patterns.md` no longer sizes one by arithmetic. `fill` is still wrong there: with both anchors
present it stretches but stops 2px short.

### 14. `visibility: hidden` collapses the space, it does not reserve it

`props.visibility` is an object, not a boolean, and it has a third form:

```json
"visibility": {"type": "hidden"}       // or "visible", or
"visibility": {"type": "conditional", "condition": { … }}
```

Hiding an element removes it from layout entirely rather than leaving a hole where it was.
Measured: two plan cards identical but for a tick badge shown only on the selected one came out
**25pt different in height**, because the hidden card's badge contributed nothing. If two
state-varying siblings have to stay the same size, put the toggled element inside a wrapper with
a **fixed** height and hide the element rather than the wrapper.

It round-trips through `config update` unchanged, including inside `propsByState`.

## The transform service is the authoritative validator

Publishing runs the config through a **transform service**, and that is the only checker in this
system whose verdict is binding. It answers with a request id, a single fatal `error`, and an
`issues` array:

```json
{"error": "Unsupported flow input: flow._meta.screens[\"scr_duoPay\"].products is missing
           flowProductId for product \"68c96b3c-…\" (screens[\"scr_duoPay\"].elements.map
           [\"el_Pay022S\"].props.product)",
 "issues": [{"severity": "warning",
             "code": "unsupported_text_typography_setting",
             "path": "screens[\"scr_duoWelcome\"].elements.map[\"el_Duo003T\"].props.verticalAlign",
             "message": "Text verticalAlign is not supported by the SDK transformer and will be ignored"}]}
```

Three things to take from that, all observed on a real 422:

- **It fails with HTTP 422 and names the exact element.** The `error` string carries both the
  `_meta` path that is incomplete *and* the `props.product` path that demanded it. When a publish
  is rejected, read the paths — they identify the element, not just the screen.
- **`severity` separates fatal from advisory.** A `warning` publishes fine. Only the top-level
  `error` blocks. Do not report warnings to the user as though they stopped anything.
- **This is a different and stricter gate than anything local.** `config update` saved this exact
  config happily; the transform service refused it. So "it saved" never means "it will publish",
  which is the same lesson trap 10 teaches about rendering, one layer further out.

### 15. Stale and degenerate sizing values persist, and the transformer believes them

The editor does not clear a numeric size when its mode changes, so a fetched config can carry
`{"type": "hug", "value": 8008}` — and the transformer turns that into `min: 8008` on device,
producing an 8008pt-minimum screen with the content invisibly far down (team-diagnosed, ADP-7308;
the recovery on an already-poisoned screen was *recreating* it, not re-saving). `width.fixed: 0`
also saves, and kills the element on device. Rules:

- **Authoring:** never emit a `value` under `hug`/`fill` (flowkit does not), never a fixed `0`.
- **Transforming:** real exports carry small stale values routinely — 16 of them in one tracked
  fixture that renders — so a stale value is a **warning, scaled by magnitude**: strip it from any
  element you are editing anyway, report the rest, and treat a large one (bigger than a screen)
  as the likely cause of a "content vanished on device" complaint.

`references/verify-config.py` warns on both forms.

### 16. `purchase` hard-terminates the flow — nothing can be shown after it

Stated flatly by the builder team (2026-08-20): the `purchase` action compiles only into the SDK
purchase call, and flow continuation after it "simply was never built" — no success screen, no
post-purchase discount screen, unconditionally, whether the purchase succeeded or not. So **never
author a screen that is reachable only after a purchase**: it is dead content that every check here
accepts. A second (discount) paywall is reachable only via an explicit `navigate` on something the
user taps *instead* of buying — the close button is the standing pattern.

### 17. State overrides deep-merge manual values and replace referenced styles wholesale

A `propsByState` override written as **manual values** is deep-merged with the base state, and the
merge leaks: a selected border colour inherited the *default's* opacity and rendered invisible on
device while the preview showed it (ADP-6967); a manually-set selected font weight rendered wrong
the same way. A **reference** — a typography `preset` or a colour *style* — propagates wholesale
and overrides cleanly ("the Selected override contains its own preset and overwrites the Default",
team-verified, reporter-confirmed). Rule: **in `propsByState`, prefer preset and style references
over inline values**, and when an inline colour must be used, make sure the base state's colour is
opaque, because its opacity is what leaks.

### `props.verticalAlign` on text is emitted by the builder and ignored by the SDK

Real exports carry `"verticalAlign": "top"` on text elements, so copying it looks correct — and it
is inert twice over: the transform service reports
`unsupported_text_typography_setting … will be ignored`, and removing it from 93 text elements
produced a **byte-identical render**. Authoring it buys one warning per text element and nothing
else, so **do not add it to text you create**. Leave it where you found it — stripping a key you
did not add is an unrequested edit — but there is no reason to write a new one.

### `theme.colors` and `theme.typography` share ONE id namespace

Reuse an id across the two and the **device SDK fails to decode the flow at all**:
`DecodingError: dataCorrupted … Debug description: Duplicate Key`. The screen never opens — this
is not a cosmetic defect.

Nothing an agent can run locally catches it. Measured on the offending config: `flows config
validate` returned **`valid: true`**, the schema check passed, and `config preview` rendered the
screen perfectly, because the preview renderer resolves the two lookups separately while the SDK
builds one keyed container from `theme`. Reported from a real device after every gate was green.

Evidence that the namespace really is shared: **8 of 8 real exports** in the corpus (sanitized and
raw alike) have **zero** overlap between the two id sets, and the builder's own naming keeps them
apart — colours are `accent`, `gray-200`, `clr_RvBg`; presets are `body`, `caption`,
`button-label`. The single collision ever seen was authored here: a `footer` colour next to a
`footer` typography preset.

So **name presets and colours in separate spaces** (`legal` for the preset, `footer` for the
colour). `references/verify-config.py` is the only gate that will tell you, and it now covers the
whole class rather than this one instance: it **errors** on a repeated id in any id-keyed
collection — `theme.colors`, `theme.typography`, `locales[].code`/`.id`, `screens[].id`,
`variables[].id`, `_meta.fonts[].id`, `_meta.icons` by name+weight, a screen's
`selectableGroups`, an element's `states` and `interactions`, action ids within an element, and
`_meta.screens[].products` — plus the colour/preset cross-collision above. It **warns** where the
collision is plausible but unproven: the same icon *name* at two weights, which no real export
does (0 of 8) but which only collides if the consumer keys icons by name alone.

Calibrated both directions: silent on all 8 corpus files (sanitized and raw), and each check
fires on its own injected duplicate.

### The schema tells you which actions are supported: `x-supported`

Every `IAction*` definition carries an **`x-supported`** boolean. Checked across all 16:
**`selectProduct` is the only `false`** — everything else (`purchase`, `openUrl`,
`restorePurchases`, `navigate`, `conditional`, `showElement`/`hideElement`, `alert`, `custom`,
`setVariable`, `closeFlow`, `navigateBack`/`navigateNext`, `nothing`) is `true`. Read the flag
before authoring an action you have not used before; it is cheaper than a device round trip, and
it is the only place this is written down.

Same caution as everywhere else, though: the flag is *schema* metadata, so `validate` still
outranks it. Grep it with `jq`, never by reading the file.

### Which group types a conditional can read — and the one action that does not work

Measured 2026-08-25 against `flows config validate` on a real flow, one predicate per run. A
conditional whose predicate names an unreadable variable fails the publish gate with
**`Generated scripts failed validation`** — location-free, exactly like a malformed hex, because
the transformer compiles predicates into JavaScript and an unresolvable name yields invalid script.

| group `type` | predicate variable | `validate` |
|---|---|---|
| `product` | `<groupId>.selectedProduct` | **valid** |
| `single_choice` | `<groupId>.selectedOptionId` | **valid** |
| `multi_choice` | `<groupId>.selectedOptionId` | **fails** |
| `toggle` | `.selectedOptionId`, `.selected`, `.value` — all three tried | **fails** |

So **a `toggle` group exposes nothing a condition can read.** This corrects the support-channel
workaround recorded for driving plan selection from a switch: it cannot be keyed on the toggle.

**`selectProduct` is the one action the schema flags `"x-supported": false`** — every other action
type is `true` — and its payload takes `{element: <element id>}`, not a product id. Bisected: a
conditional containing only `nothing` actions failed too, so the gate was objecting to the
predicate rather than to `selectProduct`; but the flag plus the unreadable toggle variable mean
**a toggle cannot move a product group's selection**. Drive the visible difference with
`propsByState` on the toggle's own element, and put the conditional where it reads a product
group.

**Conditional rich text validates, and the `switch` nests INSIDE the locale value**, with each
branch a `const` holding that locale's paragraph array:

```json
"content": {"_localizable": true, "values": {"en": {
  "type": "switch",
  "cases": [[ {"type": "&&", "predicates": [
                {"left": {"type": "var", "variableId": "plans.selectedProduct"},
                 "type": "==", "right": {"type": "const", "value": "<product-uuid>"}}]},
              {"type": "const", "value": [ …paragraph runs… ]} ]],
  "default": {"type": "const", "value": [ …paragraph runs… ]}}}}
```

The render draws **one branch of one locale with no tell in the PNG**, so read it, do not look at
it.

## The schema, the catalog, and the two different validators

| File | What it is | How to use it |
| :--- | :--- | :--- |
| **the JSON Schema** — *not bundled* | draft-2020-12, 196 definitions, rooted at `$defs.IFlow`. **Published and versioned**, so fetch it rather than shipping a copy that rots. | `curl -sSfL -o "$SCHEMA" https://schemastore.adaptybuilder.com/latest.json` once per session, then `grep -n '"purchase"' "$SCHEMA"` or `jq '.["$defs"].IFillLayer' "$SCHEMA"`. **Never read it whole** — 239KB. |
| `component-catalog.json` | 36 ready-made component templates with named slots | `jq -r '.components[].id' component-catalog.json`, then `jq '.components[]\|select(.id=="footer")'` |
| `validate-with-schema.mjs` | schema-validates a config — the gap `flows config validate` leaves | see below |
| `preview-with-playwright.mjs` | headless screenshot via the render page's file input | `npx playwright install chromium` once; skip it if you already have a browser tool |

A snapshot used to ship here and no longer does. At the moment it was removed the bundled copy was
**byte-identical** to the published one, which is exactly the argument against bundling: it buys
nothing today and silently goes stale tomorrow.

### Shape and publishability are two different checks — run both

They do not overlap, and neither one subsumes the other:

- **`flows config validate` answers *is this publishable*** — it runs the real publish-time
  transform service, so it sees stranded references the schema cannot. It does **not** check the
  shape of most props: it accepts `fill: "banana"` and `schemaVersion: 999` without complaint.
- **The schema check answers *are these props well-formed*.** It knows nothing about
  publishability.

So a clean `validate` is not evidence your shapes are right, and a clean schema check is not
evidence the flow will publish. Run the schema check first (it needs no network round trip against
your flow), then `validate`, then look at a render. Full coverage both ways —
and why `validate` needs a loop rather than a single call — in [validate.md](validate.md).

```bash
npx --yes --package=ajv@8 node references/validate-with-schema.mjs \
  --config flow.working.json --baseline flow.backup.json
```

**Always pass `--baseline`.** The schema tracks the newest `schemaVersion` while most live flows are
older, so an unbaselined run on a v9 flow reports **hundreds** of pre-existing mismatches, none of
them yours. The baseline is the pristine copy from `get`, and diffing against it leaves only what
your edit caused. Without it, the output is background noise and will train you to ignore a real
finding.

It caches the schema at `$TMPDIR/adapty-flow.schema.json` for a day — the same file you grep.
`--refresh` re-downloads; `--schema <path|url>` points elsewhere. Exit 0 clean, 1 with a JSON path
per problem:

```
  /screens/0/elements/map/el_em3n23qPxZ/props/width/type
      must be equal to one of the allowed values (fixed, fill, hug, auto)
```

### Trust order: the live validator, then the config you fetched, then the schema

The schema is a **static snapshot and it is not the authority.** Three ways it misleads, all
documented by its own publishers:

- **It is v10; most live flows are v9.** Check `config.schemaVersion` first. A `config update`
  never migrates a flow, so a v9 flow stays v9 across any number of CLI writes. Use the schema for
  *what fields exist*, not *how they are shaped*.

  **But the Flow Builder does migrate, on save.** Measured: a flow written at `schemaVersion 9` came
  back as **10** after the user opened it in the builder and saved, with all of its fills rewritten
  from objects to arrays. So the version you fetched is only good until someone touches the editor —
  which has a sharp consequence for any local build you are holding: **re-`get` before every write,
  and apply your change to the config you just fetched.** Pushing a v9 file you generated earlier
  over a flow the builder has since migrated silently downgrades it and converts every fill back.
  This is the concrete reason the workflow re-fetches on a 409 instead of retrying the same body.

  **Authoring a config from nothing is the one case with no form to preserve — use the current
  one.** "Keep the input's shape" has no input to point at, so author at the newest
  `schemaVersion` with **array fills**, which is what the builder itself now writes. Measured:
  a new paywall authored at v9 out of habit collected 10 schema findings, every one of them the
  `fill` object-versus-array difference and none a real defect; re-authoring the same document at
  v10 came back clean. This is *not* licence to convert an existing flow — a flow you fetched
  stays at its own version.
- **Its `required` lists are unreliable.** It marks `defaultLocale` required and the validator
  accepts a config without it. **Never add a field just because the schema calls it required** —
  match the config you fetched. (Omitting `status` and `id` is separately safe: measured across many
  writes, not inferred from `required`.)
### Typography metrics: `lineHeight` and `letterSpacing` exist

`IFont` carries **`lineHeight`** and **`letterSpacing`** alongside `family`, `preset`, `size` and
`weight`. Both are absent from every real export and from all 36 catalog templates, so they are a
*grep-zero* shape — declare them knowing the device may ignore them, and note that they **fail
safe**: an ignored `lineHeight` gives looser leading, not a broken screen.

Worth stating because two agents in the same GREEN arm disagreed about whether `lineHeight`
exists, and the one who believed it did not **left a reachable fidelity gap** — shipping 52 pt
headline leading against a reference's 41 pt and filing it as unreachable. Line spacing is one of
the few reference properties that is otherwise genuinely out of reach, so getting this wrong turns
a fixable gap into an ask.

**Gradients cannot carry an appearance variant.** Gradient stops are literal hex in every real
export — there is no `color-style` reference and so no light/dark pair. On a screen whose
`theme.colors` all declare dark variants, the gradients stay light while everything around them
flips. Bake the appearance you want, or use a flat themed colour where the theme has to win.

### Before authoring a shape you have not seen produced: grep for it

**The schema tells you what is permitted; a real export tells you what is produced; only the
second predicts the device.** Three defects shipped from that gap — a two-layer fill, an id reused
across the two `theme` lists, and a predicate on a `toggle` group — and every local gate was green
for two of them. In both of those the disproof was already on disk and cost seconds to find.

So when you are about to author a construct you have not seen in a real document, **count it
first** in the two sources a run always has:

```bash
# 1. the config you fetched — the most authoritative thing you hold
jq '[.. | objects | select(has("fill")) | .fill | select(type=="array") | length] | group_by(.) |
    map({layers: .[0], n: length})' flow.working.json

# 2. component-catalog.json — 36 builder-authored templates, and it SHIPS with this skill
jq '[.. | objects | select(has("fill")) | .fill | select(type=="array") | length] | unique' \
   references/component-catalog.json      # -> [1].  105 fills, none with 2 layers
```

**A count of zero is a finding, not an absence.** Nothing produced the shape, so nothing
downstream is obliged to understand it — say so out loud and treat the device check as
load-bearing rather than ceremonial.

Know what each source cannot answer. The catalog carries elements and fills but **no `theme`
block at all**, so it can settle "does the builder emit multi-layer fills" and not "may a colour
and a preset share an id" — that one is `verify-config.py`'s job. And `tests/fixtures/` is
repo-only: it does not exist on an installed skill, so never write a check that depends on it.

- **Where the schema and `validate` disagree, `validate` wins** — in both directions. And a clean
  `validate` is still not proof: it passes plenty of malformed props without complaint.
- **It has at least one unsatisfiable definition, so some findings can never be cleared.**
  `IDynamicProductValue` is a `oneOf` over **two branches that are byte-identical** — both
  `{"type": "object", "properties": {"type": {"type": "string"}}, "required": ["type"]}`, one
  commented `JSONVariable` and one `JSONConstant`, both marked "shape intentionally opaque,
  validated by the transformer". Any value that matches one matches both, and `oneOf` demands
  exactly one, so **every `purchase` action fails the schema check** — that is, every paywall
  with a plan picker. Verified 2026-08-25 both ways: the reported errors vanish when the
  `purchase` action alone is swapped out of an otherwise-clean 343-element config, and
  `tests/fixtures/onboarding-quiz-paywall.json` — a real builder export that renders and sells —
  carries the identical `{"type": "var", "variableId": "<group>.selectedProduct"}` payload and
  fails the same way. **Do not "fix" this.** Recognise the signature: four findings clustered on
  one element id, on `type`, `interactions/0/actions/0/type`, `.../payload` and `props/layout` —
  the last two are ajv reporting sibling `oneOf` branches, not separate defects.

### The `fill` shapes are a version difference, with a live exception

v9 spells a fill as a single object; v10 as an **array** — but read the next section before you
put two things in that array. Measured across four real exports plus one hand-built config:

| Config | `schemaVersion` | fill form |
| :--- | :-- | :--- |
| `onboarding-quiz-paywall` / `comparison-paywall` / `vpn-timer-draft` | 9 | object (31 / 4 / 9) |
| `tabs-paywall` — a real builder export that renders | 9 | **array (15)** |

So the version rule is the explanation, not a law: a v9 flow carrying array fills exists and works.
Which is why the operating rule is unchanged and is the safe one either way — **read the form the
input uses and keep it.** Author the array form only in a config that already uses it.

#### One layer per fill: the array is a container, not proof of compositing

**A fill with two layers draws in `config preview` and is ignored on the device.** Measured the
hard way: a screen fill of `[{image}, {gradient}]` — an asset with a dark scrim over it — rendered
exactly as intended in the preview page, passed `flows config validate` (`valid: true`), passed
the schema check, and shipped to an iOS device **with the tint simply absent**. The extra layer
was dropped.

The corroboration was sitting in the corpus the whole time: **every array fill in every real
export has exactly one layer — 0 of 8 files contain a multi-layer fill**, and image fills and
gradient fills always live on separate elements. The builder never emits the shape, so nothing
downstream is obliged to composite it.

An earlier version of this section said the array is "composited bottom → top, which is how a tint
over an image is expressed". That sentence is what produced the bug; the array form is a container
the schema permits, not a compositing feature you can rely on.

**So express a tint one of two ways:** bake it into the asset and upload the result (one `image`
layer — see [media.md](media.md)), or put the second visual on its own element. **One visual
layer per fill.**

### `effects` renders — a drop shadow is available, and measured

`props.effects` is an **array** of effect objects, valid on stacks, products, text and most other
elements. A drop shadow requires every one of `type`, `enabled`, `x`, `y`, `blur`, `spread`,
`color`:

```json
"effects": [{"type": "drop-shadow", "enabled": true, "x": 0, "y": 2,
             "blur": 10, "spread": 0,
             "color": {"type": "hex", "hex": "#101828", "opacity": 6}}]
```

`opacity` here is the 0-100 percentage of trap 11, not a fraction — `6` is a 6% shadow.
`inner-shadow` is the other `type`; there is also an `IBlurEffect`.

Worth stating because the evidence order says otherwise at first glance: `effects` appears in the
schema but in **no** real export and **no** catalog template, which normally means treat it as
unproven. It was confirmed by a control render instead — a card's painted edge measured **7px**
with the shadow and **2px** with it stripped, everything else identical. It also round-trips
through `config update` unchanged. **And it draws on a real device — confirmed in the Adapty app**
on a drop-shadow of `y: 6, blur: 18, #000000 at 8% opacity`, so this one is not a CLI-preview
artifact the way `old-price` turned out to be. So it is usable; it just has no precedent to copy
from, which means keeping a border underneath it is still the conservative choice.

### A localizable value can be a `switch`, not just blocks — and the switch is INSIDE each locale

From a real builder export. A `content` value is normally an array of paragraph blocks per locale.
It may instead be a **`switch` expression** whose every branch yields its own block array:

```json
"content": {"_localizable": true, "values": {
  "en": {"type": "switch",
         "cases": [[{"type": "&&", "predicates": [
                      {"type": "==",
                       "left":  {"type": "var",   "variableId": "plans.selectedProduct"},
                       "right": {"type": "const", "value": "<product-uuid>"}}]},
                    {"type": "const", "value": [ …blocks… ]}]],
         "default": {"type": "const", "value": [ …blocks… ]}},
  "ru": {"type": "switch", "cases": [[ …the same predicate… ]], "default": { … }}}}
```

Four consequences, and the nesting order is the reason for all of them:

- **The conditional sits inside the locale, not outside it.** Every locale carries its own complete
  copy of the switch — the same predicates, duplicated. Adding a locale to a conditional text is
  not translating a string, it is **replicating the whole expression** and translating each branch.
  Editing a predicate means editing it in every locale, and a config where `en` and `ru` disagree
  about a product id is silently two different screens.
- **Locale parity is per branch, not per field.** A field that "has a `ru` value" can still be
  half-translated: the case in Russian, the default in English. Whoever sees it is the user who
  picked the *other* plan. `references/verify-config.py` compares branch counts across locales for
  exactly this, and crashed on this shape until it was taught about it.
- **`<groupId>.selectedProduct` compares against a product UUID**, the product-group analogue of
  `<groupId>.selectedOptionId == "<customId>"`. Invariant 5's rule applies from the other
  direction: check the `const` against the form of the head. A product id here must be one **bound
  on that screen**, or the case never fires and the default quietly wins.
- **The schema accepts it and the render draws it.** Measured: a baselined schema check reports no
  new problems, and `config preview` draws one branch of one locale with no way to tell which from
  the PNG. A conditional localized string sits at the intersection of two blindnesses, which makes
  it the least verifiable thing in the format — read it, do not look at it.

### `old-price`: a real element that does not draw on device

A dedicated element type for a struck-through original price. Built and rendered:

```json
{"id": "el_…", "type": "old-price", "states": [],
 "props": {"font": {"preset": "h3"}, "color": {"type": "color-style", "colorId": "clr_Muted"},
           "width": {"type": "hug"}, "height": {"type": "hug"}, "layout": "auto-height",
           "multiplier": 2, "position": {"type": "relative"}}}
```

- **The strikethrough is inherent.** There is no `decoration` prop on it at all — striking through
  is the element's whole job, not a style you set. Confirmed in a render.
- **No `content`, no product reference.** It takes its value from the product context it sits in,
  so place it inside the `product` element whose price it discounts. The schema lists it under
  `IElement`, so it is not *structurally* confined there — but nothing else would give it a price.
- **Unattached, it renders the literal words "Old price"**, struck through. That is a far kinder
  placeholder than a `text` element holding a price variable, which renders its whole 45-character
  variableId and detonates the layout.
- **The official v10 schema accepts it** — checked with `tests/schema-check.py`.
- **Still unmeasured:** what `multiplier` actually multiplies, and whether it reads the enclosing
  product or the selected one. Preview has no store prices, so this needs a real attached product.

**`multiplier` is a pricing claim, not a layout value.** At `2` the screen asserts a 50% discount.
Nothing in the config derives or checks it, so a number pulled from nowhere is a fabricated
discount shown to real users — treat choosing it as the product owner's decision and say so, the
same way [products.md](products.md) treats a period that does not match its price field.

**It renders in `flows config preview` and NOT in the Adapty app — measured, and this reverses the
claim above.** On a real device, a card carrying this element showed only the current price; the
strikethrough was simply absent. The same config in the CLI preview draws it (a struck `$0.00`
before the live `$0.00`). Everything structural above still holds — the element exists, the
strikethrough is inherent, it takes no content — but **`multiplier` alone does not put a "was" price
on screen where users are.**

Do not author `old-price` expecting a visible strikethrough, and never lay out a price row around
one you have only seen in the CLI preview.

The likely reason, **untested**: the multiplier scales a prior price that has to exist independently,
and with no intro or offer price on the product there is nothing to scale. That would partially
reinstate an earlier conclusion recorded during this project — that a strikethrough needs either
`offer_price` or an annual-versus-monthly pair — but note the distinction that made that conclusion
wrong the first time: it was a claim about faking a strikethrough with a *`text` element and a price
variable*, not about this element. Binding a product that really has an offer price and re-checking
on device is what would settle it.

**The methodological lesson is the durable part.** This section said "measured" and "confirmed in a
render", and the render was `flows config preview` — the *weakest* of the four preview surfaces. A
single device check reversed it. A CLI render proves an element draws in the CLI renderer and
nothing more; for anything about whether users see it, that surface does not qualify as measurement.

### What the schema settles

- **34 element types**, not the handful these exports use: `bottom-sheet`, `carousel`,
  `date-picker`, `date-time-picker`, `divider`, `email-input`, `footer` (**pinned** — see
  [patterns.md](patterns.md); its props are the plain container set, so the schema cannot tell you
  it behaves differently from a `stack`), `header`, `icon`, `image`,
  `loader`, `number-input`, `old-price`, `password-input`, `phone-input`, `product`, `progress-bar`,
  `progress-bar-loader`, `progress-bar-segment`, `selectable`, `spinner`, `stack`, `tab-bar`,
  `tab-content`, `tab-content-wrapper`, `tab-item`, `tabs`, `text`, `text-input`, `time-picker`,
  `timer`, `video`.
- **15 action types**, adding `selectProduct` to the list below.
- **Group types are a closed enum**: `product`, `single_choice`, `multi_choice`, `toggle` — so trap
  10's rule is confirmed, not inferred.
- `_meta.screens[].products[]` requires `flowProductId`, matching the publish 422 from the other
  side. `webPaywallURL` also lives there.
- **Element and variable ids should stay simple identifiers** — letters, digits, underscore. Exotic
  characters are the one place a malformed value causes trouble.

### `verticalAlign`, precisely

Schema-legal on text props (`enum: ["top","middle","bottom"]`) and emitted by the builder — yet
reported `unsupported_text_typography_setting` by the transform service, and removing it from 93
elements rendered byte-identically. Legal, inert, one warning per element. Do not author it.

## Making a field mandatory: show the button conditionally

**You cannot disable a button.** There is no disable mechanism to drive: no input has a `required`
prop or an error-message prop, and an element's `disabled` *state* takes no condition — the builder
emits `states: [{"id": "disabled", "type": "system"}]` with no `condition` key, and the runtime
drives it. An earlier version of this section taught a conditional `disabled` state with a greyed
`propsByState`. **It does not work**: four such conditions produced a 422 from the transform
service, and no builder-emitted config contains one.

What actually exists is **conditional visibility on the button** — show it once the field has
content. Verified from a Flow Builder export of a working screen:

```json
"props": {
  "visibility": {
    "type": "conditional",
    "condition": {
      "type": "&&",
      "predicates": [
        {"type": "notEmpty", "left": {"type": "var", "variableId": "email_input.value"}}
      ]
    }
  }
}
```

The other builder-supported route is an **action**: keep the button hidden and attach a show-button
action to the input's `change` or `submit` interaction. Prefer conditional visibility — it is
declarative, needs no interaction wiring, and re-hides itself if the field is cleared.

**Mind the layout consequence.** A hidden element contributes nothing to layout rather than leaving
a gap (trap 14 above), so a conditionally-shown Continue button makes everything below it jump the
moment the field is filled. If the screen has anything under the button — a legal line, a "Skip"
link — put the button in a wrapper with a **fixed** height and condition the *button*, not the
wrapper.

### Small device facts from the support channel, each one sentence

- **Font sizes below 14 render at 14 on device** (preview shows the smaller size) — reported
  2026-08-17, acknowledged as a bug, unresolved; do not design a caption that depends on 11pt.
- **A `mailto:` `openUrl` crashes iOS unless "open in external browser" is set** — SDK-side fix
  landed, but the flag remains the safe pattern.
- **Dark theme works only through colour styles that define dark values** — a direct hex is one
  colour in both themes; theme-dependent *images or videos* are not buildable at all (the fallback
  is separate screens per theme, switched app-side).
- **Screen ids are analytics keys**: the dashboard's per-screen paywall rows key on `screen_id`,
  every republish mints a new row, and a rename only affects future versions — so mint stable,
  meaningful screen ids and set `caption`s, because both outlive the publish.
- **`type: number` inputs are coerced to text and numeric comparison operators do not exist** —
  which is the team-side confirmation of the "compare against strings" rule below.

### The expression facts, and how each was established

| Fact | Evidence |
|---|---|
| A unary predicate uses **`left`**, exactly like a binary one — there is no `value` or `operand` form | builder export; plus four `left`-shaped conditions passing shape validation into codegen |
| An input's value is **`<customId>.value`** | builder export (`email_input.value`, where `email_input` is the input's `customId`), then **confirmed on device across three input types** — `email-input`, `password-input` and `text-input` all gated their button correctly from `<customId>.value`. So the form is not specific to one input type, and nothing needs declaring in `config.variables` for an input to be in scope |
| The **`&&` wrapper around a single predicate is optional** | render: an unwrapped `empty` behaved identically to the wrapped control, and a garbage operator in the same slot failed closed, so the unwrapped form really was evaluated |
| `ExpressionType` is a closed set: `const`, `var`, `switch`, `&&`, `||`, `==`, `!=`, `has`, `notHas`, **`empty`**, **`notEmpty`**, `in`, `notIn`, `>`, `<`, `size`, `assign`, `concat` | schema |

**Emit the `&&` wrapper anyway.** It is optional but it is what the builder writes, and matching the
builder keeps a round trip clean.

**Multiple predicates work, and that is how you gate on a whole form.** Confirmed on device: a
Continue button with two predicates — `email.value` and `password.value`, both `notEmpty` — appeared
only once both fields had content. So one `&&` with one predicate per required field is the pattern
for a multi-field form; there is no need for nesting.

Structural shapes, from a rendering export:

```json
{"type": "var",    "variableId": "quiz.selectedOptionId"}
{"type": "const",  "value": "rock"}
{"type": "==",     "left": {…}, "right": {…}}
{"type": "&&",     "predicates": [{…}, {…}]}
{"type": "switch", "cases": [[<predicate>, <result>]], "default": <result>}
```

### Two failure modes, and they point opposite ways

Measured with deliberate controls in one render:

- **An unknown operator fails closed.** `{"type": "bogusop", …}` hid the element. So a typo in an
  operator name costs you the element, silently — no error, just an absence.
- **An unresolvable variable is silently treated as empty.** A condition over
  `no_such_input.value` — an id present nowhere in the config — rendered as though the value were
  an empty string: `empty` was *true*, `notEmpty` false. Nothing warns.

That second one has a sharp consequence for verification. **`empty` over a name that does not
resolve is indistinguishable from `empty` over a real, empty field**, so a screenshot of an
empty-state screen cannot confirm that your variable reference is correct. It is also why a bare
`customId` with no `.value` must not be used: it renders exactly like the working form while the
field is empty, and this project has no evidence it ever resolves. Use `<customId>.value`, the form
the builder emits.

The way to actually confirm a reference resolves is to observe the **flip** — the element appearing
or disappearing as the field is filled — which needs the Adapty app or the builder's own preview,
because `flows config preview` renders one static state.

### What `flows config preview` can and cannot check here

**A `visibility` condition *is* evaluated by the preview renderer** — this is the one kind of
condition it honours, and the empty-field state of a conditional button is genuinely checkable
locally. A `states[].condition` is **not** evaluated; see
[SKILL.md phase 4](../SKILL.md).

Two things still cannot be checked locally, per the failure modes above: whether a variable
reference resolves, and anything about the filled state.

**The schema cannot check a condition at all.** `IDynamicProductValue` is a `oneOf` over two
branches that both accept any `{"type": <string>}` and carry the comment *"shape intentionally
opaque, validated by the transformer"*. Every real expression matches **both**, so `oneOf` always
fails. `tests/schema-check.py` suppresses this class — and had to be widened to look for the
opaque `oneOf` anywhere in the error tree, because a condition nested inside a state's own union
pushes the real cause off the deepest path and reported four errors for one schema limitation.
Never reshape a condition to satisfy the schema; it has no opinion worth having here.

`flows config validate` reaches the transform service from `adapty/0.8.0` and does check the
*references* inside a condition — a `const` compared against an undeclared product, or a `groupId`
naming no group, comes back as an `Unsupported flow input` error ([validate.md](validate.md)). It
still says nothing about whether the condition expresses what you meant. So the gates on a
condition's *logic* are: the preview render (visibility only, empty state only), device preview,
and a human.

### The transform service compiles conditions to TypeScript

Worth knowing because it shapes the error you get. A malformed reference comes back not as a schema
complaint but as a compiler diagnostic:

```
{"error": "Generated scripts failed validation",
 "issues": [{"severity": "error", "code": "script_type_violation", "path": "scripts",
             "message": "TS2304: Cannot find name 'email'. (line 22, col 21)"}, …]}
```

`code` is `script_type_violation`, `path` is the useless constant `"scripts"`, and the real
information is a **TS error code plus a line/col into a generated file you cannot see**. Read the
identifier out of the message and find it in your config; do not try to map the line number.

**Count nothing from the number of issues.** Codegen emits *more than one* diagnostic per authored
reference — measured, **one** state condition referencing `email` produced **two** TS2304 errors, at
different line/col pairs. So the issue count tells you nothing about how many places you have to fix.

**Codegen validates the whole flow, not the screen you are previewing.** Measured: previewing
`?screen=scr_probe` failed on an identifier that existed only on a *different, unlinked* screen in
the same flow. Combined with `path: "scripts"` carrying no screen id, the only reliable move is to
search the entire config for the identifier in the message — not the screen you were looking at.
A single broken screen anywhere blocks preview and publish for every screen.

**The builder's duplicate-screen action copies a broken condition faithfully.** That is how the
screen above came to exist: an earlier draft of this project's own probe was duplicated in the
editor, and the copy carried a conditional `disabled` state — the mechanism that does not work —
into a flow whose visible screens were all correct. Deleting the copy fixed the flow. When a 422
names an identifier you thought you had removed, look for a duplicate screen before you doubt the
error, and do **not** write it off as a stale cache: nothing here is cached, and the diagnostic was
accurate about a screen that really was still in the config.


## Conditions cannot compare numbers — enumerate equality instead

**`ExpressionType` lists `<` and `>`. They do not work.** A gate written as

```json
{"left": {"type":"var","variableId":"age.value"}, "type": "<", "right": {"type":"const","value":18}}
```

passes the official schema, saves, and renders — and the runtime does not honour it. There is no
numeric comparison available to a condition, so any threshold has to be spelled out as equality
cases:

```json
"cases": [
  [{"type":"&&","predicates":[{"left":{"type":"var","variableId":"age.value"},
                               "type":"==","right":{"type":"const","value":"0"}}]},
   {"type":"const","value":[{"id":"","type":"navigate",
                             "payload":{"type":"screen","screen":"scr_blocked"}}]}],
  … one case per value: "1", "2", … "17" …
],
"default": {"type":"const","value":[{"id":"","type":"navigate",
                                     "payload":{"type":"screen","screen":"scr_ok"}}]}
```

Three things that follow:

- **Compare against strings.** `"17"`, not `17` — matching the one verified conditional, which
  compares `quiz.selectedOptionId == "rock"`.
- **Decide which way the gate fails, and say so.** Enumerating the *blocked* values means anything
  unenumerated — `"07"`, `" 17"`, an empty field, letters — lands in `default` and is **let
  through**. For an age gate that is failing *open*. Enumerating the *allowed* values and defaulting
  to blocked fails closed, at the cost of one case per permitted value. Neither is wrong; picking
  silently is.
- **A picker is one condition instead of many, but it is not automatically better.** A
  `single_choice` group turns the whole problem into a single `selectedOptionId` comparison — the
  shape conditions actually support — and removes every free-text edge case, because there is no way
  to type `" 17"` into a choice. The cost is precision and feel: bands are the wrong control when the
  exact value matters to the product (an age shown on a dating profile, a headcount, a budget), and
  a five-option list where a keypad belongs reads as clunky. Offer the trade rather than assuming
  the cheaper condition wins — a real user rejected bands for exactly this reason.

This is the clearest instance of the trust order in this file: the schema said the operator existed,
the schema was right about the *vocabulary* and wrong about the *behaviour*, and only the runtime
settled it. When a condition silently routes everyone to `default`, suspect the operator before the
wiring.

## Vocabulary

The union observed across the three exports, with provenance so a later reader can tell an
observed value from an assumed one.

**This list is a floor, not a closed set.** It is what three flows happened to use, and the
Flow Builder ships more elements than these — see
[Elements](https://adapty.io/docs/builder-elements.md). An unrecognized `type` is
**preserved verbatim**: never reject it, never normalize it to something on this list, and
never treat its absence here as evidence the file is invalid.

| Field | Values | Provenance |
| :--- | :--- | :--- |
| element `type` (on screens) | `stack`, `text`, `icon`, `image`, `product`, `selectable`, `text-input`, `timer` | `stack`, `text`, `icon` in all three; `image` in `quiz` + `timer`; `product` in `quiz` + `comparison`; `selectable` and `text-input` in `quiz` only; `timer` in `timer` only |
| element `type` (in `components`) | `progress-bar`, `progress-bar-segment`, `progress-bar-loader` | `progress-bar` and `progress-bar-loader` in `quiz` + `timer`; `progress-bar-segment` in `quiz` only. All three observed *only* inside `components`, never directly on a screen |
| element `type` (**not in these exports**, present in the transformer's front-format fixtures) | `divider`; the tabs family `tabs`, `tab-bar`, `tab-item`, `tab-content-wrapper`, `tab-content`; the input family `email-input`, `password-input`, `number-input`, `phone-input`, `date-picker`, `time-picker`, `date-time-picker` | Absence from the three exports is absence of coverage, not evidence a type is invalid. These are real front-format inputs. `tabs` is a **composite**, not one element — see the request map below |
| action `type` | **14 types.** In these exports: `navigate`, `conditional`, `purchase`, `closeFlow`, `nothing`. Also valid, and none of them appear here: `navigateBack`, `navigateNext`, `restorePurchases`, `setVariable`, `openUrl`, `alert`, `custom`, `showElement`, `hideElement` | `closeFlow` in all three; `navigate` in `quiz` + `timer`; `purchase` in `quiz` + `comparison`; `conditional` and `nothing` in `quiz` only. `nothing` appears only as a `conditional` case value, never as a top-level action. The other nine come from the builder transformer's front-format fixtures — and `navigateBack`/`navigateNext` are the **two most common actions there**, more common than `navigate` itself, so a Next button does not need a named destination. Payload shapes below |
| action payloads | `navigate` → `{screen}` · `navigateBack` / `navigateNext` / `closeFlow` / `restorePurchases` / `nothing` → **no payload** · `openUrl` → `{url, external?}` · `alert` → `{title, message}` · `custom` → `{id}` (the "Action ID" whose absence is a publish blocker) · `showElement` / `hideElement` → `{element}` · `setVariable` → an array of `{type: "assign", left, right}` · `purchase` → `{product, type?}`, see below | Observed in the transformer's front fixtures. `purchase` is the one with two product forms — see the next row |
| `purchase` `payload.product` | `{"type": "var", "variableId": "<groupId>.selectedProduct"}` when the screen has a product group, **or** `{"type": "const", "value": {"id": "<productUUID>", "offerId"?}}` when it does not | The `const` form is what a paywall with a single implied plan uses — one CTA, no product cards, no `_meta.screens` entry needed. Do not add an empty product group to satisfy the `var` form. A `payload.type` of `"native"` also appears alongside `product`; it is optional in practice |
| interaction `trigger` | `tap` | the only trigger in all three |
| `conditional` `payload.type` | `switch` | `quiz` only. `cases` is an array of `[predicate, {type: "const", value: [actions]}]` pairs, plus a `default` in the same value shape. Actions nested inside a case carry `"id": ""`, not an `act_` id — including the `navigate` that a screen deletion has to repair, which is why a dangling target can sit two levels down inside a `default` branch |
| predicate operators | `&&` (grouping), `==` (comparison) | `quiz` only |
| `width` / `height` `type` | `fill`, `hug`, `fixed`, `auto` | first three in all; `auto` in `timer` only |
| `position.type` | `relative`, `absolute`, `fixed` | first two in all; `fixed` in `timer` only; `relative` on 234 of 246 elements. `type` is the only guaranteed key — offset keys (`top`, `right`, `bottom`, `left`) are added as needed, and **which** offsets a non-`relative` element needs is a constraint, not a style choice: see trap 9 |
| `fill` container | **object OR array.** The three exports carry `fill: {…}`; a current working config carries `fill: [{…}]` — an array of fill layers — on both screen `props.fill` and element `props.fill`. Read which form the input uses and keep it; do not convert between them |
| `fill.type` | `color`, `gradient`, `image` | `color` in all; `image` in `quiz` + `timer`; `gradient` in `quiz` only |
| block node `type` | `paragraph` | the only block type in all three |
| inline node `type` | `text`, `variable`, `token` | `text` in all; `variable` in `quiz`; `token` in `timer` |
| `token` names | `timer_minutes`, `timer_seconds` | `timer` only. See [Countdown timer](https://adapty.io/docs/flow-timer.md) |
| `selectableGroups[].type` | `single_choice`, `multi_choice`, `product`, `toggle` | `product` in `quiz` + `comparison`, `single_choice` in `quiz`; `multi_choice` and `toggle` from the transformer's front fixtures. **A tab group is declared `single_choice`, not `tabs`** — verified against a working tabs paywall, which pairs `{"id":"tabs","type":"single_choice"}` with a separate `{"id":"products","type":"product"}` on the same screen. `tabs` appears as a string constant in the transformer source but is **not** what a working config uses; emitting it produced a config the API accepted and the builder could not open. The group type, not the element type, is what makes a control a toggle or a multi-select: `toggle-selection` is a bare `stack` in a `{"type":"toggle"}` group. See [Selectable elements and groups](https://adapty.io/docs/flow-selectable-elements.md) |
| element `states[].id` | `selected`, `focused`, `invalid`, `disabled`, all with `"type": "system"` | 10 state entries in the corpus. `selected` on all 6 selectable-group members — `quiz`'s 3 `selectable`s and **all 3** `product` elements (2 in `quiz`, 1 in `comparison`); `disabled` twice, on `quiz`'s `text-input` **and** on one of its `selectable`s; `focused` and `invalid` on the `text-input` only. `states` is not per-`type` — two elements of the same type carry different sets. No non-`system` state observed |
| `icon.type` | `phosphor` | all three, with `viewBox="0 0 256 256"` in `_meta.icons[].raw`. [Common issues](https://adapty.io/docs/flow-common-issues.md) calls the library Tabler Icons; the exports say otherwise and the exports are ground truth here |
| `icon.weight` | `regular`, `fill` | `regular` in all; `fill` in `quiz` + `comparison` |
| typography `weight` | `regular`, `medium`, `semibold`, `bold` | `medium` in `comparison` only |
| `text.props.layout` | `auto-height` | the only value observed |
| `timer.props.behavior` | `start_at_every_appear` | `timer` only |
| locale `id` | `en` | the only locale in all three. A multi-locale export has not been observed; for how locales are added in the builder, see [Add locale](https://adapty.io/docs/add-paywall-locale-in-adapty-paywall-builder.md) |

### From what the user asks for to what the JSON calls it

The table above answers "what is this key". This one answers the question a transform
actually starts from — **the user named a thing; what do I build?** The two vocabularies do
not match, and four of these have no element of their own at all. Getting this wrong is not a
style error: you will search for an element type that does not exist, or invent one.

| The user says | What it is in the JSON |
| :--- | :--- |
| a button | **No `button` element exists.** A `stack` (or `selectable`/`product`) carrying `interactions: [{trigger: "tap", actions: [...]}]`. Every button in every export is this. |
| a toggle, a switch | **No `toggle` element exists.** Any element with a `groupId` whose `selectableGroups` entry is `{"type": "toggle"}`, styled via `propsByState.selected`. |
| pick one / pick several | The same shape with group `type` `single_choice` or `multi_choice`. The element type does not change; the group type does. |
| a plan picker, plan cards | `product` elements sharing a `groupId` whose group is `{"type": "product"}`, one with `default: true`. Prices come from variables — see [`products.md`](products.md). |
| radio buttons, a selected state | Not an element. `states: [{"id": "selected", "type": "system"}]` plus a `propsByState.selected` block. Style the same element twice; do not add a second one to hide. |
| tabs, a segmented control | A **five-element composite**: `tabs` → `tab-bar` → `tab-item`(s), and `tabs` → `tab-content-wrapper` → `tab-content`(s). Each `tab-item` carries `groupId` + `default`, group `type` `tabs`. |
| a countdown | A `timer` element with `duration`/`behavior`, plus rich-text `token` nodes (`timer_minutes`, `timer_seconds`) in a child `text`. |
| a loading screen, a spinner | Fill the **`loader-spinner-label` catalog component** — it is the canonical source and its wiring is already correct. The primitives are `spinner` (a rotating icon; `props.icon.type` must be `"custom"`, or the publish gate 422s), `loader` (a determinate bar), and an invisible auto-advance `timer` that moves the flow on. The `spinner` is **preview-blind in some layouts** — never hand-roll it from a static `icon` to satisfy a screenshot; keep the real element and verify on device ([`patterns.md`](patterns.md)). |
| a progress bar, step dots | A `components` entry (`progress-bar` → `progress-bar-segment` → `progress-bar-loader`), referenced from a screen's `hierarchy` as `{"id": "pb_…", "type": "global"}`, and switched on per screen via `props.progressBar: {enabled, segment}`. |
| a divider, a rule | A `divider` element exists. Both real exports instead use a `stack` with `height: {type: "fixed", value: 1}` and a `fill` — either is valid; prefer whichever the input already uses. |
| a text field, email, phone, a date picker | `text-input`, or one of `email-input`, `password-input`, `number-input`, `phone-input`, `date-picker`, `time-picker`, `date-time-picker`. Its `customId` becomes the variable `<customId>.value`. |
| a price | Never literal text. A rich-text `variable` node — see invariant 5 for the two forms. |
| a close button, "dismiss" | A tappable `stack` whose action is `{"type": "closeFlow"}` (no payload). |
| an image, a background | An `image` element for content; `props.fill` with `{"type": "image"}` for a screen or element background. **Different shapes** — see trap 1. |

Two rules that follow from the whole table: **the user's noun is rarely the element `type`**,
so resolve the request through this map before searching the file — and when a request maps to
something absent from the input, say so rather than substituting the nearest type you can see.

Full flow-docs index, for any page not linked above:
`https://adapty.io/docs/flows-llms.txt`. Do not assemble a docs URL from a topic name — open
only URLs written here or listed in that index.

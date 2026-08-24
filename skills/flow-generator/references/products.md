# Products — ids, binding, and the CLI

A flow references products by UUID and the Flow Builder binds them. Where a correct id comes
from, what the builder rewrites when the user attaches products by hand, and how to create a
product when none suitable exists.

Structure and the referential invariants live in [`flow-schema.md`](flow-schema.md) —
invariant 4 (`product` element declared in `_meta.screens.<screenId>.products[]`), invariant 5
(price variables name a declared product), trap 4 (product variables are referenced, never
declared in `variables[]`). Not re-derived here.

## Where product ids come from

A flow's `props.product.id` is the same Adapty product UUID that `adapty products list`
returns — **the same namespace, verified**: a UUID taken out of a real flow export resolved
through `adapty products get`, returning that product's title, period and store bindings.

```
$ADAPTY auth status                             # local only, no network
$ADAPTY apps list --json
$ADAPTY products list --app <UUID> --json       # --page-size max 100, default 20
$ADAPTY products get <PRODUCT_UUID> --app <UUID> --json
```

`--app` is required on everything except `apps list`. Never invent a product UUID and never
carry one over from another user's export — read it from `products list`, or ask.

**The selection is a dialogue, not a lookup.** SKILL.md phase 2 owns the order — list, ask which,
ask for store ids only if none fit, create last — and this page owns how to present the choice:
one line per product with **title, period, and which stores it binds** (`products get` for the
detail), because period and bindings are what the user needs to recognise their own product, and
period is what the price variables will be checked against. If they name a product that is not in
the list, that is the store-ids conversation, not a guess. **A silent pick from the catalog is the
same defect as an invented UUID with better odds** — measured on live runs: the agent choosing
"plausible" products worked only because the sandbox had one obvious set.

**Provenance — required reading before you trust a flag on this page.** The flags were verified
via `--help` on `adapty/0.3.0` and **re-verified unchanged on 0.6.0**. The two *runtime*
requirements below — at least one store binding, and `--android-base-plan-id` with
`--android-product-id` — were observed by running the command on 0.3.0 and have not been
re-tested since. Note also that `--help` is not a reliable command inventory: it omitted
`flows config validate` and `flows config preview` entirely on the version where both existed.
So on any newer CLI, re-check against each command's own `static flags` declaration — in
`adaptyteam/adapty-cli`, or in the installed package's `dist/commands/`. Do not treat this page
as ground truth for a version you have not checked.

And check *which* CLI you are invoking. A globally installed `adapty` is often old — 0.3.0 was
found on a real machine — so if a command or flag documented here is missing, try
`npx --yes adapty@latest` — then `@beta` — before concluding it does not exist.


## The builder owns product binding

From a real round-trip — the agent wrote a flow, the user attached products in the Flow
Builder, the flow was re-exported:

| Field | Written by the agent | Returned by the builder |
| :--- | :--- | :--- |
| `props.product.id` | the id the agent chose | **rewritten** to the attached product |
| price `variableId` | keyed to the agent's id | **rewritten** to match |
| `_meta.screens[].products[].flowProductId` | copied from another export | **regenerated** |
| element ids | the agent's own | **preserved byte-stable** |

Four consequences, and this file is the authority on all four:

- **NEVER hand-author or copy `_meta.screens[].products[]`.** It is builder-owned bookkeeping.
  Carry the block through untouched from the source export, or leave the screen without one and
  let the user attach.
- **`flowProductId` is assignment-scoped, not flow-scoped.** The same product in the same flow
  (`c599e7f6…`) carried `a00b5c50…` in one export and `6cc4fef1…` in a later one. It is a
  UUIDv5, so derived — but not from `(flow, product)`. It cannot be predicted, and it cannot be
  reused across exports of the same flow.
- **Price variables self-heal on attachment.** A wrong `product.id` is repaired by the human
  step rather than shipped as a broken paywall — the builder rewrites the id and every price
  `variableId` keyed to it. So worry less about id accuracy and more about the two failures the
  builder does *not* repair: a screen nobody attaches, and a period that disagrees with its
  price field (below).
- **A `product` element with no product attached is a documented publish blocker**:
  <https://adapty.io/docs/flow-common-issues.md>. Say in your report which screens need an
  attachment pass before the user tries to publish.
- **Builder-owned means do not OMIT it either, not just do not author it.** `config update`
  replaces the whole config, so a script that regenerates a config from source and emits
  `_meta.screens: {}` **destroys attachments the user made in the builder** — and the
  `flowProductId` values cannot be recomputed, so the next publish fails with a 422 and the user
  has to redo the pass. Measured in this project: a hand-built flow was regenerated and rewritten
  four times from a source whose `_meta.screens` was empty; it only escaped clobbering the
  attachment because the user happened to attach *after* the last write. **On every regeneration,
  re-read the live config and carry `_meta.screens` forward** for every screen that still exists
  (`tests/preserve-builder-state.py` does this). A screen you deleted legitimately loses its
  declarations — say so rather than dropping them silently.
- **And it is enforced, not merely documented.** Measured: a config with two `product` elements and
  an empty `_meta.screens` **saved without complaint** and then failed the publish transform with
  **HTTP 422** — `flow._meta.screens["scr_duoPay"].products is missing flowProductId for product
  "68c96b3c-…"`, naming both the `_meta` path and the `props.product` path that required it. So the
  missing `flowProductId` is a hard stop at publish time, which is exactly why you must not invent
  one and must hand the attachment pass to the user instead.

### VERIFIED ON DEVICE: a second price-variable form that tracks the selection

A second form exists — `<groupId>.selectedProduct.<field>`, e.g.
`products.selectedProduct.prod_price` — resolving against a `product`-typed selectable group
rather than a specific product.

**Confirmed in the Adapty app:** a root-level line reading `plans.selectedProduct.prod_price`,
placed *outside* both product cards, resolved to a real price and **changed as each card was
tapped**. So it re-resolves on selection rather than binding once, which makes it the correct way
to write a "then $X — cancel anytime" line under a set of plan cards. Authoring it is fine.

Still true: never convert a `<productUUID>.prod_price_per_*` reference into it, or the reverse.
They answer different questions — one names a fixed product, the other follows the user.

### A price variable REQUIRES a `product` element on the screen — even with no plan card

Buying and declaring are different things, and only declaring makes variables resolve.

The chain, end to end:

1. A price variable `<productUUID>.prod_price` resolves against **that screen's declared
   products** — nothing else.
2. Declarations live in `_meta.screens[<screenId>].products[]`, each with a `flowProductId`.
3. **Only the Flow Builder writes those**, and it writes them when a product is attached to a
   **`product` element**.
4. So a screen with no `product` element has nothing to attach a product *to* — which means no
   declaration is possible, which means the variable can never resolve. Not "needs an attachment
   pass": **unattachable**.

The failure is explicit once you publish:

```
Unknown Product Id
Rich-text variable "<uuid>.prod_price" references unknown product or product group "<uuid>"
```

**A `const` purchase payload does not help.** It buys the product perfectly well and needs no
declaration — see the section below, which is true and easy to over-read. It declares nothing, so a
screen whose CTA carries a `const` purchase still cannot resolve a price variable.

**So: if a screen shows a price, it needs a `product` element, whatever the design looks like.**
A single-plan paywall with no visible picker still wraps its price block in one — give it the
`groupId` of a `product`-typed group and `default: true`, and it renders exactly like the plain
stack it replaces while giving the builder something to attach. Evidence for the shape: in the one
verified export that uses price variables, **every** price-variable holder sits inside a `product`
element's subtree.

**Binding `product.id` on the element is enough — the builder declares it when it SAVES the
flow.** Not when it opens one. Measured across two flows: an edit in the builder (status → `dirty`)
declared the products, and so did publishing (status → `published`), each minting the
`flowProductId`s and leaving the bindings untouched with **nobody re-picking anything**. But merely
opening a flow and hitting *preview on device* saves nothing, so at that moment the declaration is
still absent and the preview fails.

So the division of labour is:

| | |
|---|---|
| An agent can | bind `product.id`, set `groupId`/`default`, wire `<group>.selectedProduct` |
| An agent cannot | write `_meta.screens[].products[]` — `config update` does not synthesize it |
| The builder does | mint `flowProductId` and declare the products, on open |

`flowProductId` is a UUIDv5 but **not over any input the config contains** — 2,944
namespace/name/version combinations tested against 5 real (screen, product, flowProductId)
triples, no match, and the same product on two screens gets two different ids. So do not try to
author one, and do not copy one between flows.

### Declare the products yourself, and a new flow previews on a device immediately

**This is the route to prefer for a flow you authored.** Write the `_meta.screens` declaration in
the config you send:

```json
"_meta": {"screens": {"scr_x": {"products": [
  {"id": "<product-uuid>", "flowProductId": "<any stable uuid>"}]}}}
```

Measured: a **draft** flow, never published and never opened in the builder, carrying two
fabricated `flowProductId`s, previewed on a real device with no errors. The transform service
checks that a declaration is **present and internally consistent** — not that the value is the one
the builder would have minted. `flowkit.predeclare(screen_id, product_ids)` generates one.

The value cannot be computed (19,776 namespace/name/version combinations over 4 triples with full
provenance — app, flow, screen, element and product ids all known — produce no match), so this is
a provisional handle, not the right answer. Two limits:

- **Never do this when rewriting an existing flow.** Carry the live `_meta.screens` forward
  instead; replacing a real declaration with a provisional one is a regression.
- `flowProductId` is a server-side handle and this project does not know what else it keys. Treat
  a provisional value as good for previewing, and expect the builder to replace it when it saves.

### Device preview fails on a freshly authored flow, and publishing fixes it

Tell the user this **before** they try it, because the error is alarming and self-healing:

> Transform service returned HTTP 422 — `missing_flow_product_id` (once per bound product) and
> `unknown_product_id` (once per price variable)

Measured sequence on a flow written entirely through the CLI with `_meta.screens: {}`: *preview on
device* → 422 with those four errors; **publish** → the builder writes the declaration and the
preview works. Nothing was broken; the declaration simply did not exist yet. An edit in the builder
does the same thing (status → `dirty`), so a publish is not required — but neither is needed at all
if you declare the products yourself, as above.

The reason is that **device preview is a stricter gate than `config update`.** The write endpoint
does not run the transform service, so a config with no declaration saves cleanly. Device preview
and publish both do run it, and it treats a missing `flowProductId` as an error rather than a
warning. Two consequences worth stating plainly:

- A clean `config update` says nothing about whether the flow will preview on a device.
- For a newly authored flow, the first successful device preview is *after* the first publish.

**Price variables authored before the declaration exists do resolve once it lands — verified.** The
round trip is exact: 51 of 51 element ids unchanged, and every price `variableId` preserved
verbatim, including `<productUUID>.prod_price`, `<productUUID>.prod_price_per_month` and the
group-relative `<groupId>.selectedProduct.prod_price`. So authoring a price variable is correct as
written, and the note elsewhere that the builder rewrites price `variableId`s applies to *changing*
a product on an element, not to declaring one.

Static price copy is therefore no longer the required default — it is the choice you make when the
flow must be publishable without a first publish, or when the price should not track the store.

This was learned by shipping the mistake — a trial paywall with a `const` purchase, no product
element, and two price variables that the builder rejected as unknown-product on publish.

### A purchase can bind a product with no `product` element

**Verified by render.** A three-tab paywall whose three CTAs each carried

```json
{"type": "purchase", "payload": {"product": {"type": "const", "value": {"id": "<product-uuid>"}}}}
```

rendered and worked with **no `product` element on the screen and no
`_meta.screens[].products[]` entry**. So the `const` form is self-sufficient *for binding*: the
action names the product directly, and no element has to stand behind it.

**But it is not self-sufficient for publishing, and an earlier version of this page said it was.**
Measured 2026-08-24 against `adapty/0.8.0` in production: `flows config validate` refuses that
exact fixture with `flow._meta.screens["scr_RvSel001"].products is missing flowProductId for
product "<uuid>" (…elements.map[…].purchase.product)`. The transform service harvests declarations
from `product` elements only, so a product reached *just* through a `const` purchase is invisible
to it — and the render says nothing, because the preview page does not run that service
([validate.md](validate.md)).

Three consequences, the third of which is a correction:

- **Do not manufacture a `product` element** to satisfy a purchase action. The `var` form
  (`{"type": "var", "variableId": "<groupId>.selectedProduct"}`) needs a `product`-typed
  selectable group behind it; the `const` form needs nothing. Choose by which one the screen
  already uses — never by which one you know how to build.
- **Prices are the reason to *attach* a product, not purchases.** A `prod_price_*` variable needs
  its product attached and resolvable; a `const` purchase does not.
- **Every product a screen names needs a `_meta.screens[<sid>].products[]` entry, however it is
  named** — element, `const` purchase, condition or price variable. On a flow you authored,
  `flowkit.predeclare()` writes it and a provisional `flowProductId` is accepted. A screen with
  hardcoded price copy and `const` purchases is complete for rendering and **still blocked for
  publishing** until those products are declared.

## The hidden-base-product pattern, and the Android ordering trap

The standing recipe for a fallback price (an offer the store may not return — eligibility, timing,
geography are the store's call and the config cannot force it) is a **duplicate of the product
without the offer, hidden on the screen**. It works, and it carries a measured trap:

**Android matches a price variable to a product by `vendorProductId` + `basePlanId` only —
`offerId` is ignored** (team-read from SDK source, `FlowStateFactory.kt`). Two Product elements for
the same store product therefore both resolve to whichever comes **first in the config's product
list**, and if the base product is first, `offer_price` silently renders empty or undiscounted.
Three facts that follow, all team-stated (2026-08-17, ADP-7541 tracks the real fix):

- **Order is the creation order of the Product elements.** Dragging elements in the Layers panel
  does not change it.
- **The offer-bearing product must come first.** To repair an inverted order: leave the offer
  Product untouched, delete the hidden base, recreate it (duplicate the offer Product, set
  "No offer", hide it) so it lands last.
- **A republish can reorder the list** — including across a schemaVersion migration — which is why
  this defect flip-flops between "works" and "broken" with no edit anyone made. If offer prices
  appear and vanish across publishes, check the order first.

Two more product-element facts from the same channel: **two visible cards bound to the same product
get the same `flowProductId` and selection breaks** — bind distinct products, one `default` — and a
product with **no store mapping for a platform renders no price at all** on that platform.

## Creating a product

Offer this only when no product in `products list` fits. Two commands:

```
$ADAPTY access-levels list --app <UUID> --json    # to get --access-level-id
$ADAPTY products create --app <UUID> --access-level-id <UUID> \
                       --period <value> --title <title> \
                       <AT LEAST ONE store binding>
```

`--period` takes exactly one of: `weekly`, `monthly`, `two_months`, `trimonthly`, `semiannual`,
`annual`, `lifetime`.

**At least one store binding is REQUIRED**, despite `--help` presenting them all as optional in
square brackets under a "STORE BINDINGS FLAGS" heading. Omit them all and the command fails with
`Error: At least one store binding is required (ios/android/stripe/paddle)` and exits 2. This was
found by running it, not by reading — treat it as one more instance of the repo-wide rule that
CLI prose contradicts CLI behaviour, and verify against behaviour or per-command source.

The bindings: `--ios-product-id`, `--android-product-id`, `--android-base-plan-id`, and the
**paired** `--stripe-product-id`/`--stripe-price-id` and
`--paddle-product-id`/`--paddle-price-id`. Each of those two pairs requires its partner — one
half alone is not a binding.

**`--android-product-id` additionally requires `--android-base-plan-id` for subscriptions**,
which `--help` also presents as optional: `Error: --android-base-plan-id is required with
--android-product-id for subscriptions`. So the minimum viable subscription create is
`--period` + `--title` + `--access-level-id` + `--app` + **either** `--ios-product-id` alone
**or** `--android-product-id` together with `--android-base-plan-id`.

**Never pass `--json` to a create you are debugging.** On failure it emits only
`{"error":{"oclif":{"exit":2}}}` and discards the message that tells you which flag is missing.
Run it plain, read the error, then re-run. Two required-flag rules above were invisible until
`--json` was dropped.

**You cannot invent a store product id.** It has to match a real entry in App Store Connect,
Play Console, Stripe or Paddle. A product bound to an id that exists in neither place is created
successfully and then carries no price, so `prod_price_*` renders empty and a purchase cannot
complete. So a `products create` is only ever offered with store ids the **user supplied** — ask
for them, and if the user has not got them yet, say the product cannot be created rather than
guessing from a naming convention.

### `products create` writes to a live dashboard — confirm first, in writing

Reads take **no** confirmation — run `apps list`, `access-levels list`, `products list` and
`products get` freely; they are how you fill the slots below.

`products create` is the one command here that changes the user's account. Before you run it,
the conversation must already contain, as a message you sent:

1. The full command with **every slot resolved to a literal value** — no `<UUID>`, no
   placeholder, no "the app id from above".
2. Each flag's meaning in one line: which app, which access level, which period, which store
   ids.

and after it, the user's explicit yes.

That check is textual, not a matter of intent. Scroll back: no message carrying the resolved
command, followed by a yes, means the gate has not been passed — whatever you planned to do.
Announcing that you will confirm and then running the command is exactly the failure this rule
catches. A slot you cannot fill from a read is one you ask about, not one you fill from memory.

If the user is going to run the command themselves, write it out with the resolved values and
stop. Their terminal is where it gets run.

### CHECKED: `--period` must agree with the price-variable field

A product created `--period monthly` and bound to `prod_price_per_year` renders **no price**
while every referential check passes. Neither validator catches it — `flow-schema.md`'s
invariants 4 and 5 and the publish blockers all check the product *reference*, never
period/field agreement.

This is not advice. Before you write a price variable, and again in the Verify step, check the
pair:

| Product `--period` | Price field | Renders? |
| :--- | :--- | :--- |
| `monthly` | `prod_price_per_month` | yes |
| `annual` | `prod_price_per_year` | yes |
| `annual` | `prod_price_per_month` | **yes** — a real derived figure, confirmed on device |
| `monthly` | `prod_price_per_year` | **no** — blank, and every referential check still passes |

**The rule is asymmetric, so "must agree" is too strong.** Measured in both directions: a field
*shorter* than the product's period is derived and renders (an annual product happily fills
`prod_price_per_month`, which is what "$X/month, billed annually" needs), while a field *longer*
than the period renders blank. Read that as: the runtime will divide a price down, never
extrapolate it up.

For any other period, read the field name out of the export you are transforming or out of
`products get` — do not extrapolate one from the period name.

This defect was committed by this skill's own author in a sample paywall: a card labelled
"Annual" bound `prod_price_per_year` to a product whose period was `monthly`. The card looked
right, the JSON validated, and the price was blank.

### A mismatch you cannot resolve is a STOP, not a disclosure

If the request needs a period the catalog does not have — a yearly card when `products list`
returns only `monthly` — you have no correct product to bind. **Do not write a placeholder
binding and disclose it.** Report what is missing, offer the `products create` command from
above, and stop before the write.

This is a hard stop rather than a judgement call, because the obvious reading is wrong. A
measured run bound the yearly card to a monthly product, disclosed the mismatch in detail, and
reasoned that the missing `_meta.screens` declaration is a publish blocker so the flow could not
go live in that state. **That reasoning fails.** The blocker is cleared by attaching the product
the config names — which is precisely what a user does next, and which is the exact action that
turns the blank price into a live one at the wrong period. The gate that looks like protection is
removed by the obvious remedy.

Its own report named the outcome: *"if it went live as-is, tapping Yearly then Subscribe would
charge the monthly price."* Nothing downstream reliably prevents that, so the write is where it
has to stop.

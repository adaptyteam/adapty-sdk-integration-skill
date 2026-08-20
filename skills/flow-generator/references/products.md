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
adapty auth status                              # local only, no network
adapty apps list --json
adapty products list --app <UUID> --json        # --page-size max 100, default 20
adapty products get <PRODUCT_UUID> --app <UUID> --json
```

`--app` is required on everything except `apps list`. Never invent a product UUID and never
carry one over from another user's export — read it from `products list`, or ask.

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
`npx adapty@beta` before concluding it does not exist.


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

### Unverified: a second price-variable form

A second form exists — `<groupId>.selectedProduct.<field>`, e.g.
`products.selectedProduct.prod_price` — resolving against a `product`-typed selectable group
rather than a specific product. Observed in a live Flow Builder screen and **in no export**, so
its exact field names are unverified: preserve it verbatim where found, never author one, never
convert a `<productUUID>.prod_price_per_*` reference into it.

### A purchase can bind a product with no `product` element

**Verified by render.** A three-tab paywall whose three CTAs each carried

```json
{"type": "purchase", "payload": {"product": {"type": "const", "value": {"id": "<product-uuid>"}}}}
```

rendered and worked with **no `product` element on the screen and no
`_meta.screens[].products[]` entry**. So the `const` form is self-sufficient: the action names
the product directly.

Two consequences worth stating, because getting them wrong is what happened first:

- **Do not manufacture a `product` element** to satisfy a purchase action. The `var` form
  (`{"type": "var", "variableId": "<groupId>.selectedProduct"}`) needs a `product`-typed
  selectable group behind it; the `const` form needs nothing. Choose by which one the screen
  already uses — never by which one you know how to build.
- **Prices are the reason to declare a product, not purchases.** A `prod_price_*` variable
  needs its product declared and attached; a `const` purchase does not. A screen with
  hardcoded price copy and `const` purchases is complete as written, and calling it a publish
  blocker would be wrong.

## Creating a product

Offer this only when no product in `products list` fits. Two commands:

```
adapty access-levels list --app <UUID> --json     # to get --access-level-id
adapty products create --app <UUID> --access-level-id <UUID> \
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

| Product `--period` | Price field that renders |
| :--- | :--- |
| `monthly` | `prod_price_per_month` |
| `annual` | `prod_price_per_year` |

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

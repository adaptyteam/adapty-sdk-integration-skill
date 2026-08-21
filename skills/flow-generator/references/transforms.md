# Flow transforms — what each one endangers

Nothing here tells you how to walk the JSON — measured runs already did that correctly, down
to a `navigate` buried two levels deep in a `conditional`'s `default`. What the JSON does not
contain is **Adapty's rules**: which edits stop a publish, and which choices are not yours to
make silently. That is all this file carries.

Structure, shapes, and the twelve referential invariants each row names below live in
[`flow-schema.md`](flow-schema.md), under `## Invariants`; positioning and layout are its
trap 9. Product ids and product binding live in [`products.md`](products.md), which is the
authority on both. Do not re-derive any of it here.

## Risk table

| Transform | What it endangers | Publish blocker it trips | What to check |
| :--- | :--- | :--- | :--- |
| **Add a locale** | Invariant 11, across **three** localizable families — `text.props.content`, `image.props.image`, `text-input.props.placeholder` — not text alone. A bare-string `content` has no locale slot and cannot hold the translation at all. | None. A locale missing from a `values` map falls back or renders empty: invisible at publish, visible to users. | Every bare-string `content` you met appears in your report under decision 1. **`defaultLocale` is unchanged** — adding a locale is additive, and flipping the default changes what every existing user sees with nothing failing. And every *declared* locale carries every localizable field: `tests/verify-fixture.py` checks parity and errors when a translated block's `variableId`s differ from the default locale's, which is the failure that silently costs a locale its prices. |
| **Rewrite copy** | Invariants 5 and 11, plus trap 2 — inline `variable` and `token` nodes survive a rewrite only if you edit around them, never through them. Field shape is per field and must survive the edit. | None — and that is the danger. A paragraph rebuilt from its rendered text publishes cleanly and passes every referential check; trap 2 in [`flow-schema.md`](flow-schema.md) states what it costs. | Every locale in `locales[]` got the same edit, or your report says which did not. No field changed shape (decision 1). |
| **Add / remove / reorder screens** | Invariants 3 and 12, which break in **opposite directions**. Invariant 3: the target dies and the reference survives. Invariant 12: **the consumer survives and the producer dies** — deleting a screen can strand a variable consumer on a screen you never opened. Verified in `quiz`: the `text-input` with `customId: "name"` lives on **Quiz**, and `name.value` is read on **Rock**, **Hip hop** and **Paywall After**. Delete Quiz and all three references stay intact with nothing to resolve against, so nothing on the edited screen looks wrong and three untouched screens render an empty name. Also: `screens[0]` is the entry screen, so a reorder silently moves where the flow starts; and `_meta.screens` is keyed by screen id, so a deleted screen's product declarations leave with it (invariant 4). | Three, all on the [Common issues](https://adapty.io/docs/flow-common-issues.md) list: a dangling `navigate` (invariant 3), a screen with no elements, and — on any screen you add that carries a `product` element — a product element with no product attached, which no edit of yours can clear (see [`products.md`](products.md)). A stranded variable consumer is **not** a blocker; it publishes and renders empty. | Every `<inputCustomId>.value`, `<groupId>.selectedOptionId` and `<productUUID>.prod_*` reference still has a producer. Search `screens` **and** `components`: no component in the corpus holds a reference, but a component is a screen-shaped `{map, hierarchy}` that can, so it is inside the search space. A new screen matches `flow-schema.md`'s `root`-wrapper and `scr_`-id rules. `screens[0]` is still the screen you mean. Orphans and widenings are in your report (decisions 2 and 3). |
| **Branching and conditions** | Also: **conditions cannot compare numbers.** `<` and `>` are in the schema's `ExpressionType` and are not honoured at runtime, so a threshold must be enumerated as `==` cases against **strings** — see [flow-schema.md](flow-schema.md). Invariants 6 and 7. Renaming a selectable option changes its `customId`; every `const` compared against `<groupId>.selectedOptionId` must change with it, or the case stops matching and **every user takes the `default` branch** — routing changes with nothing failing. | A `conditional` with no operator or value. A `const` that matches nothing is not a blocker; it silently reroutes everyone. | For each predicate `const`, a member of that group carries that `customId`. Each `selectableGroups[]` entry has at least one member, and each `groupId` in use is declared. You know where `default` sends users, because a mismatch sends everyone there. Read `default` as a live route, not a fallback: in `quiz` the switch has one case (`rock`) and `hiphop` is routed **only** by `default`. And a group member may legitimately carry no `customId` at all — `quiz`'s continue button is a `quiz` member and holds the conditional itself — so an absent `customId` is not a gap to fill. |

## Decisions you must disclose

Six of the seven items below are points where two answers are both defensible and Adapty has
not settled which is correct; item 4 has no choice in it, only a fact the user must hear before
they publish. The deliverable is not the JSON alone — it is the JSON **plus a report
that names what happened.** Four baseline locale runs reached decision 1, split 2–2 on it, and
zero mentioned it: a correct file with a silent choice inside it is an incomplete delivery.

For each item your transform encountered, your report states the trigger you hit, which option
you took, how many fields or screens it covered, and what the user will see because of it. If a
transform encountered none of them, say so — an absent disclosure and an unencountered decision
look identical to the user.

### 1. A bare-string `content` during a locale transform

**Trigger:** you are adding a locale, and a `text.props.content` you would otherwise translate
is a bare string — `"content": "Next"` — with no `values` map and no `_localizable`.

It cannot hold a translation as it stands. Both exits are legitimate:

- **Leave it bare.** The field keeps a shape real exports carry, and that label renders in
  the source language for **every** locale you added. In `quiz` there are 6 such fields:
  `"Next"` four times, plus `"Yearly"` and `"Monthly"` on the paywall — all user-visible.
- **Convert it to `{values, _localizable}`** and fill every locale. The label translates, and
  the field's shape has changed. Both shapes exist in real exports, and `flows config update`
  preserves nested shapes verbatim — so the save will succeed. The local **preview** also draws
  converted fields correctly (measured: six converted labels rendered pixel-identically to the
  bare-string source). What remains **UNVERIFIED** is whether the *Flow Builder's editor* renders
  them — nobody has opened one, and the preview page is a different renderer
  ([flow-schema.md trap 10](flow-schema.md)). So converting is defensible, but if you convert:
  say so, name the fields, and tell the user to check those labels first.

**Leaving it bare is safe at the transform service.** A Flow Builder screen carrying bare-string
`content` on both its text elements went through device preview, and the service's issue list named
only the font preset and `verticalAlign` — nothing about content shape. So a bare string is not a
publish blocker and there is no pressure to convert one for validity's sake; convert only when the
field genuinely needs to translate.

**Your report states** which option you took and how many fields it covered — and if you left
them bare, it lists the literal strings that stay in the source language.

The case to beat, verbatim from a baseline run that left them bare: it reported *"Spanish
translations for every remaining localizable field"* while `"Next"`, `"Yearly"` and
`"Monthly"` stayed English and it never said so. Literally true, materially misleading.
Listing those three strings is the whole difference.

### 2. Deleting a screen that other screens depend on

**Trigger:** the screen you are deleting produces something another screen consumes — a
`text-input` `customId` read as `.value`, a `selectableGroups` id read as
`.selectedOptionId`, or a product declared in its `_meta.screens` entry and read as
`<productUUID>.prod_*`.

Three exits, all defensible:

- **Repair the consumer.** Rewrite the consuming screens so they stop referencing the dead
  producer — drop the name from the greeting. The flow is self-consistent, and copy on
  screens the user never mentioned has changed.
- **Keep the producer.** Move the producing element onto a surviving screen: a `text-input`
  travels with its `customId`, but a `product` element has no `customId` and its declaration
  is builder-owned bookkeeping you do not hand-author — so relocating one leaves the product
  unattached on the destination screen and trips the publish blocker unless the user attaches
  it there. [`products.md`](products.md) is the rule. Either way, a screen the user never
  mentioned gained an element.
- **Report the break.** Leave the references dangling. Nothing blocks publishing; the
  consuming screens render an empty value until the user fixes them in the builder.

**Your report states** which producer died, the exact reference, every screen that reads it,
which of the three exits you took — and, for the third, that the flow still publishes in that
state.

In the baseline, one run rewrote the consumer and one left it dangling. Both were defensible.
The choice is invisible in the output file unless the report names it.

### 3. Widening a destructive request

**Trigger:** the deletion you were asked for makes other screens unreachable — no `navigate`,
in any branch, still points at them.

- **Delete the newly unreachable screens too.** No dead branches remain. You also deleted
  screens the user did not name; if they had work in progress on those branches, it is gone.
- **Delete only what was asked and name the orphans.** The requested change is exactly what
  happened. The flow carries screens no path reaches — legal, publishable, and the user
  decides their fate.

**Your report states** the screens you deleted, split into *asked for* and *deleted as a
consequence*, and every screen now unreachable that you left in place. Deleting a consequence
may well be the right call; it is still a widening of the request, and it is reported as one.

Measured: asked to "drop the quiz step", one baseline run deleted **three** screens — Quiz
plus both genre branches, which become unreachable once the branching conditional goes — and
another flagged the orphans and left them standing.

### 4. A `product` element the user still has to attach

**Trigger:** the transform leaves a screen carrying a `product` element that no
`_meta.screens` entry attaches — because you added the screen, or because the source's
declaration block did not travel with it.

No option and nothing to weigh: product binding belongs to the Flow Builder, and the flow will
not publish until the user does that pass in the dashboard. [`products.md`](products.md) is the
authority on why, and on everything else about product ids.

**Your report states** every screen that needs an attachment pass, and that publishing fails
until the user completes it.

### 5. A source config that names products which do not exist

**Trigger:** a `const` purchase payload, or a `_meta.screens` declaration, references a product
UUID that `adapty products get` answers with `Adapty product does not exist`. Real configs carry
these — a flow copied between apps, or one whose products were deleted, or a sanitized fixture.

Both exits are defensible, and two measured runs on the same seed split cleanly between them:

- **Carry the dead id through.** The transform stays a transform: you changed what was asked and
  nothing else, and the broken binding is a pre-existing defect you are reporting rather than
  quietly editing. The cost is that the CTA still cannot complete a purchase.
- **Rebind to a real product** from `products list`. The flow becomes usable, and you have made a
  content decision the user did not ask for — the mapping is inferred from titles, which is a
  guess about their catalog.

Neither is wrong. **What is wrong is doing either one silently**, because both leave the user with
a belief that does not match the flow: that the paywall works, or that you changed nothing.

**Your report states** which you did, the exact id-to-id mapping either way, that
`products get` is what established the ids are dead, and — if you carried them through — that
those CTAs cannot complete a purchase until someone swaps them. Say whether the defect is also
present in the source flow, because it usually is and fixing only the copy leaves it live.

### 6. Which way a threshold gate fails

**Trigger:** the transform builds a gate on a value that has no numeric comparison available — an
age check, a spend tier, anything with a cutoff — so the threshold is spelled out as equality cases.

Enumerating one side puts everything else in `default`, and that choice decides what happens to
input nobody anticipated:

- **Enumerate the blocked values** (`"0"`…`"17"` → blocked, default → allowed). Fewer cases, reads
  naturally. **Fails open**: `"07"`, `" 17"`, an empty field or letters are let through.
- **Enumerate the allowed values** (`"18"`…`"120"` → allowed, default → blocked). Many more cases.
  **Fails closed**: anything unexpected is stopped.

Neither is wrong and the skill does not pick for you — but on a gate that exists for a legal or
safety reason, failing open is a real consequence and the user is the one who gets to accept it.

**Your report states** which side you enumerated, which way it therefore fails, and one concrete
example of an input that slips through. If a picker would have avoided the problem entirely, say
that too.


### 7. Which script a digraphic language gets

"Add Serbian" does not name a script. Serbian is digraphic — `sr` conventionally means Cyrillic,
`sr-Latn` is Latin, and a consumer app in the region may want either or both. The same question
arrives with Uzbek, Kazakh, and Simplified versus Traditional Chinese. Picking one silently
decides what a whole market reads.

**Trigger:** the requested language is written in more than one script and the user named only the
language.

**Options:** one script, or both as separate locales. Say which code you used (`sr` versus
`sr-Latn`) rather than just "Serbian", because the code is what the SDK matches against.

**And when you ship both, derive the second by transliteration, not by translating twice.** The
scripts are a strict 1:1 mapping, so a transliteration cannot say something different from its
source, whereas two independent translations drift apart on the next copy edit. Three mechanics
make it correct: replace **digraphs before single letters** (`љ њ џ` → `lj nj dž`, or `л`/`н` eat
them first); map **only the source script's codepoints**, so Latin already in the copy survives
untouched — a brand name, `·` separators, an em dash; then **assert nothing from the source script
remains**, which is the one check that catches a letter missing from the table.

**Report:** the language, the locale codes you added, which is the source and which is derived,
and — if derived — that it is a transliteration, so the user knows a copy edit must be re-derived
rather than re-translated.

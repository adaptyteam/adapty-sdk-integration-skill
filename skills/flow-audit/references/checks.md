# `flow-audit` check reference

Per-check evidence for `audit-flow.py`: what it looks at, its severity and why, its
calibration result, and the false-positive (or false-negative) trap that would have
shipped if the check had not been run against real data first. **Read this before
changing a check** — every rule below was wrong on first contact with real data, and
the traps recorded here are exactly the mistakes that first contact caught.

Calibration corpus: six tracked flow fixtures under `tests/fixtures/` (five from
`flow-generator`'s corpus plus one added for this skill, `onboarding-multilocale.json`)
plus `tests/catalog-fixture.json` (a product catalog, not a flow config, so it lives
outside `fixtures/`) plus five real flows in `app_finance` measured while this
skill was written. `vpn-timer-draft.json` is this skill's **negative control** — it
produces **zero** findings across all six families. `timeline-anchored.json` is
**not** a full negative control: it carries **zero actions anywhere** — no purchase,
no `closeFlow`/`navigateBack`, nothing tappable at all — so `no-escape-in-flow` fires
on it, correctly, as a `question`. That is a true positive, not a blind spot: a flow
with genuinely no way out is exactly the case this check exists to name (see
`no-escape-in-flow`'s row below). It stays a negative control for every other family.
`tabs-paywall.json` is the compliance control specifically: it carries a
real `openUrl` × 2 to `/terms` and `/privacy`, a real `restorePurchases`, and a
`closeFlow`, so every store-compliance check has a real passing case to stay silent
on, not just an absence of selling screens. It is **not** a negative control for the
products family: it binds three products through `const` purchase actions, none of
which exist in the catalog fixture, and the products family correctly fires
`product-not-in-catalog` × 3 on it — a blind spot in an earlier version of
`bound_products`, not a pass, and the fixture never earned that claim.

Every table below states **status** as either a real fixture it is silent on, or a real
fixture/live flow it fires on, or both — a check with only one half proven is marked
**untested in the other direction** and is not a closed claim.

## Triggers

| Check | Severity | Why | Calibration |
| :--- | :--- | :--- | :--- |
| `dead-affordance` — copy names an action (`restore`, `terms`, `eula`, `privacy`, `skip`, `manage subscription`, `unsubscribe`) on an element where **neither the element nor any ancestor** carries an interaction | blocker | the row renders exactly like a working control and does nothing | **fires**: `comparison-paywall.json` (3× — Restore/Terms/Privacy, genuinely dead, no `restorePurchases`/`openUrl` anywhere in the flow) and the live `df730155` flow (`el_089T` reads "Restore purchase · Terms · Privacy" with no interaction at all). **silent**: `onboarding-quiz-paywall.json`, `tabs-paywall.json`, `timeline-anchored.json` — each carries a one-word label ("Skip"/"Terms"/"Restore"/"Privacy") whose tap target lives on a wired **ancestor**, cleared by the ancestor walk |
| `action-nothing` — an action explicitly typed `nothing` | risk | a forgotten stub the schema allows (`IActionNothing`) | absent from the whole corpus and the five live flows — **untested in both directions** until injected |
| `openurl-no-url` — an `openUrl` action with no `url` in its payload | blocker | the button does nothing when tapped | 0 occurrences in the corpus — **untested in both directions** until injected |
| `interaction-no-actions` — an interaction with an empty `actions` array | risk | wired but does nothing | 0 occurrences across 5 flows, so no false positives measured; not proven to fire on real data (fires on injection in `test-audit-flow.py`) |

### False-positive traps — Triggers

| Trap | What would have shipped |
| :--- | :--- |
| Reading `groupId` off the element root | `groupId` lives at `element['props']['groupId']`, not the element root. A first probe read the root and wrongly reported three real grouped elements as ungrouped. |
| Treating a one-word label as proof of nothing | Detection must walk to the wired **ancestor**, not just the element itself — `onboarding-quiz-paywall.json`, `tabs-paywall.json` and `timeline-anchored.json` all carry standalone labels whose tap target is a parent `stack`. Skipping the ancestor walk would flag every one of them as dead. |
| `cancel anytime` in the affordance vocabulary | It was tried and dropped. In `timeline-anchored.json` it is reassurance copy ("Cancel anytime.") — never a tappable affordance — and it was the one true false positive this vocabulary produced. |
| Assuming a tappable-looking element with no interaction is always wrong | Selection needs **no** interaction of its own: a `product`/`selectable` element inside a declared `selectableGroups` group is selected via the group. A blanket "no interaction = dead" check would false-positive across the whole corpus. |

## Store compliance

Grouped as one family because these checks share a rationale (App Store 3.1.1/3.1.2 and
the Play equivalents) and a fix shape.

| Check | Severity | Why | Calibration |
| :--- | :--- | :--- | :--- |
| `no-restore` — the flow sells (binds a product, or carries a `purchase` action) but has no `restorePurchases` action anywhere | blocker | App Store 3.1.1 requires a restore path | **fires**: 3 of 4 real selling flows measured, including `df730155` despite its copy literally saying "Restore purchase". **silent**: any flow once a `restorePurchases` action exists anywhere (calibrated by injection) |
| `no-terms-link` / `no-privacy-link` — a selling flow has no `openUrl` action whose URL tokenizes to a terms/EULA or privacy vocabulary word | blocker (no `openUrl` at all) or question (an `openUrl` exists but no URL matches) | App Store 3.1.2 requires both links on a subscription screen | **fires as blocker**: `openUrl` occurs in **none** of the 5 live flows measured, so no flow there ships a working legal link. **silent**: `tabs-paywall.json` (real `/terms` and `/privacy` URLs) |
| `no-escape-from-paywall` — a selling screen has no `closeFlow`/`navigateBack` reachable via the navigation graph (`navigate`/`navigateNext` edges) | blocker | a user who does not buy must be able to leave | **fires**: `df730155`'s paywall (only action is `purchase`); silent on `tabs-paywall.json` and the other 3 live paywalls, each with one escape reachable |
| `no-escape-in-flow` — no `closeFlow`/`navigateBack` anywhere in the flow at all, on ANY flow (selling or not) | question | may be legitimate if the host app presents the flow modally with a system dismiss | fires on `d1faba75` (3 screens, no dismissal anywhere) and on `timeline-anchored.json` (1 screen, zero actions of any kind — a true positive on a non-selling flow with genuinely no way off); silent once a `closeFlow`/`navigateBack` exists anywhere, selling or not |

### False-positive / false-negative traps — Store compliance

| Trap | What would have shipped |
| :--- | :--- |
| Detecting a legal link by the button's **label** | Reports a paywall with real, working `/terms` and `/privacy` links as non-compliant when the buttons read "Legal". Detection must live on the `openUrl` action's URL payload, never the label. |
| Matching a legal-link vocabulary word by **substring containment** | A false negative: `tos` matches inside `photos` and `autos`, `legal` matches inside `illegally`. A paywall whose only `openUrl` points at `/photos/hero.jpg` silenced the terms check under substring matching. The fix tokenizes the URL on non-alphanumeric runs and requires an exact token match — deliberately trading a concatenated path with no separator (`/termsofservice`) into a `question` rather than a silent false pass, because a question is honest and a false silence on a 3.1.2 requirement is not. |
| Detecting an escape by its **label** | **7 of 9** real escape affordances measured across the corpus are icon-only with no text at all; the two that do carry text read `'I already have an account'` and `'Leave for now'` — neither contains *close*, *skip* or *later*. A label-based close check finds **0 of 9**. Detection binds to the action type (`closeFlow`/`navigateBack`), graph-reachable rather than screen-local; the label is reported as evidence for the human to judge, never used for detection. |
| Assuming text naming an action proves the action exists | `el_089T`'s "Restore purchase · Terms · Privacy" is the clearest instance: it renders exactly like a working row and satisfies nothing. Every compliance check tests for the *action*, never the word — this is the same rule as the `dead-affordance` check in Triggers, applied in both directions (text without an action, and an action without text). |

## Products

Online-only family — every check here needs the live catalog (`products list`), because
it is comparing the config against the dashboard, not against itself.

| Check | Severity | Why | Calibration |
| :--- | :--- | :--- | :--- |
| `product-not-in-catalog` — a bound product id does not exist in `products list` | blocker | the purchase cannot complete | not yet proven to fire on a real flow; fires on injection (rebind to a nonexistent id) — dedups per product id, message names every binding site |
| `product-no-access-level` — a catalog product has no `access_level_id` | blocker | a purchase would grant nothing | silent on the real catalog (11 of 11 sandbox products have one, 4 of 4 in `catalog-fixture.json`); not yet proven to fire |
| `product-store-gap` — a bound product has no `vendor_products` entry for a store the app ships on | blocker (store named) / question (store unknown) | the purchase cannot complete on that store | **fires as blocker**: 8 of 11 sandbox catalog products are `app_store`-only, so any of them would fail an Android build. Question form is silent when only the known store is checked (`--stores ios` clears an `app_store`-only product) |
| `play-base-plan-missing` — a `play_store` vendor entry has no `base_plan_id` | blocker | Google needs product id + base plan id to complete a purchase | **silent** on the real catalog: all **3** live `play_store` products carry a real base plan (`monthly`, `monthly-base`), and all 3 in `catalog-fixture.json` too. Read **only** off the `play_store` entry — see the trap below |
| `period-claim-mismatch` — a card's copy names exactly one billing period and it disagrees with the bound product's catalog `period` | blocker | the user is shown a period the product does not have | **calibrated both ways**: silent on 8/8 real cards, fires on injected rebinds |
| `foreign-price-variable` — a card's *only* price-variable reference names a different product than the one it is bound to | blocker | the card displays the wrong price | **calibrated both ways**: silent on 8/8 real cards (6 reference their own product, 2 reference none), including the fixture that was the measured false positive (`onboarding-quiz-paywall.json`'s `el_8rfwhBiXQL`); fires on the injected rebind |
| `hardcoded-price` — a non-zero currency literal on an element with no price variable of its own | blocker | it will not localise currency and will not follow a store price change | **fires on 2 of 8 real cards** — `$79.99`/`$119.99` written as plain text in a **published** flow |

### False-positive / false-negative traps — Products

| Trap | What would have shipped |
| :--- | :--- |
| `base_plan_id` read off the element root, or off any store | `base_plan_id` is a Google Play concept. It is `null` on essentially every `app_store` entry — measured null on **11 of 11** products in the real live catalog. An unscoped check would fire on the whole catalog. Read it only off a `play_store` entry. |
| The naive period vocabulary, run on real copy | Flagged **3 of 4** real selling flows, every one a false positive: `7 Days Trial` read as weekly (a **trial length**, not a billing period); `Billed once a year` read as lifetime (the word `once` is not a lifetime signal); `12 mo • $79.99` read as monthly because bare `mo` matched before the multiplied unit `12 mo` could claim it; `$0 during trial` read as a hardcoded price (a zero literal is not a price claim). Fixed by stripping trial durations first, ordering the vocabulary longest-unit-first so a multiplied unit is consumed before the bare unit, dropping `once` from the lifetime vocabulary, and excluding zero-value currency literals. |
| `\s*` between a digit and a unit | Real copy hyphenates: `12-month plan` fell through to the bare monthly rule and read as monthly instead of annual; `3-month plan` read as monthly instead of quarterly-missed; `12-months` matched no rule at all (the extra trailing `s` broke `month`/`mo`/`mos`'s own `\b`) rather than falling through to anything. Fixed with `[\s-]*` between digit and unit, plus explicit plural forms on the bare rules. |
| A card naming **both** periods treated as a mismatch | The decisive rule is **arity, not presence**: a card naming exactly one period term that disagrees is a finding; a card naming both (`$6.67/MO` next to `12 mo • $79.99`) is the legitimate equivalent-price pattern — 4 of 8 real cards are this shape. Treating presence as the signal would make the report worthless. |
| A literal-text presence test on a price element | A price element's whole content is legitimately a single `variable` node with **no literal text at all** — a blank-text check flags every price on every paywall. The variable's own id (`prod_price_per_month`) also contains the word `month`, so a literal-text reader that includes variable ids leaks it into the period vocabulary; the period check reads only rendered text, never a variable id. |
| `hardcoded-price` scoped to the whole card | A card-scoped test asks "does this card use variables at all" rather than "is *this* literal backed by a variable". Measured false negative: keep a real card's price variable, add a sibling text element reading "was $99.99" — the card-scoped version reported 0 findings and the fabricated price would ship. Fixed by scoping element-by-element: each literal is judged against the specific element that carries it. |
| `foreign-price-variable` scoped per-element instead of per-card | The inverse mistake: a card showing a struck-through **foreign** price beside its own is the legitimate was/now comparison, verified on a real shipped card that sells its own product and additionally shows a rate from another plan, purchase binding correct throughout. Flagging that trains a user to ignore the whole finding family. This check stays card-scoped on purpose — the test is arity over the whole card (does it reference its own product's price variable **anywhere**), not presence of any one element. |
| Treating a `groupId` as a decidable variable-consumer relationship for products | Not this check's family, but the same root cause recorded under Variables below — see there. |

## Variables

| Check | Severity | Why | Calibration |
| :--- | :--- | :--- | :--- |
| `variable-no-consumer` — an explicit `setVariable` producer whose target is never read anywhere else in the flow | risk | probably dead state | **calibrated both ways** by injection: silent on all six tracked fixtures (no real flow in the corpus contains a `setVariable` action at all), fires on an injected orphaned `setVariable`, stays silent when a real consumer (a `var` predicate) reads it elsewhere |

`verify-config.py` already owns the reverse direction (a consumer with no producer);
this check is deliberately the other half, not a restatement.

### False-positive trap — Variables

| Trap | What would have shipped |
| :--- | :--- |
| Treating any element's `groupId` as a producer of `<groupId>.selectedOptionId` | Not decidable from the config alone. A product group's implied variable is `<groupId>.selectedProduct`, not `.selectedOptionId` (`onboarding-quiz-paywall.json`'s `products` group, `comparison-paywall.json`'s); a `tab-item` group (`tabs-paywall.json`'s three-member `tabs` group) exposes no readable variable at all — selection switches visible content natively; and a single `selectable` sharing a `groupId` with no other member is a plain toggle, not a choice with a reader to find (`onboarding-multilocale.json`'s one-member `notify` group). All three real shapes are fine, and no rule short of a fixture-specific exception separated them — so the check stays scoped to the one producer kind the config states unambiguously: an explicit `setVariable` action. |

## Localization

`verify-config.py` already errors on a missing locale key per field, so this family owns
only what it measurably *passes*.

| Check | Severity | Why | Calibration |
| :--- | :--- | :--- | :--- |
| `empty-translation` — a locale key is present but carries no literal text and no `variable`/`token`/`image` node | blocker | a real user in that locale sees a blank field | **calibrated both ways**: fires on an injected empty value, silent on all 43 real fields in `onboarding-multilocale.json` and on every other tracked fixture |
| `locale-entirely-empty` — a declared locale has no values anywhere in the flow | blocker | a whole language was declared and never filled | derived from the coverage table; not present in the corpus, not yet proven to fire on real data |
| `untranslated` — a value is identical to the base locale's text elsewhere in the flow | risk, grouped once per flow | may be a missed translation, may be a proper noun | **fires** twice on `onboarding-multilocale.json` (twice on real Havn too) and **both hits are the brand name** (`Nimbus`/`Nimbus Plus`, `Havn`/`Havn Plus` in the live corpus) — correctly untranslated, so this can never be a blocker |

### False-positive traps — Localization

| Trap | What would have shipped |
| :--- | :--- |
| A literal-text-only presence test | Every price element's whole content is a single `variable` node with no literal text — a blank-text check flags every price on every paywall. A value counts as present if it carries text **or** a `variable`/`token`/`image` node. |
| Treating an empty `text` node as substantive | An earlier version of the check counted a paragraph containing `{'type': 'text', 'text': ''}` as content, which made it miss its own injected empty-translation defect — a truly empty field slipped through as "has a text node". |
| A per-locale **image** value read by the richtext-only walk | A per-locale image value is a bare `{id, url}` object with **no `type` key at all**, so a `type`-based substantive test sees nothing and calls a real, filled image asset empty. Measured on two real, working fixtures before the fix (`onboarding-quiz-paywall.json`, `vpn-timer-draft.json`). Fixed: a truthy `url` on the value also counts as present. |
| Treating any identical-to-base value as a defect | The only two untranslated values in the whole corpus are the brand name — correctly untranslated. `untranslated` is inherently judgmental, so it can never be a blocker and is never reported per-field: it is a count with up-to-4 examples, grouped once for the whole flow, and the human judges. |

## Placeholders

| Check | Severity | Why | Calibration |
| :--- | :--- | :--- | :--- |
| `placeholder-copy` — anchored match on `lorem ipsum`, `your … here`, a bare `text`/`title`/`subtitle`/`button`/`label`/`heading`/`placeholder`, `TODO`/`TBD`/`FIXME`, or `placeholder text` | risk | unfinished copy shipping to users | **0 false positives over 5 live flows / 169 localizable fields** and over all six tracked fixtures; fires on injection (`Lorem ipsum…`, `TODO write this`, `Your headline here`) — not yet proven to fire on a real flow |
| `flow-untitled` — the flow's dashboard name is `Untitled`/`Untitled flow`/`New flow`/blank | question | usually means the flow was never named | fires on one live flow; silent once the name is anything else |
| `publication-failed` — the flow's dashboard `--status` is `publication_failed` | question | the flow failed to publish and no local check here explains why; never invents a cause | fires on any `--status publication_failed` run (measured against `df730155`); silent on every other status |

### False-positive trap — Placeholders

| Trap | What would have shipped |
| :--- | :--- |
| A bare word match instead of an anchored one | "Sample a new workout every week" is legitimate copy — `sample` alone cannot be a signal. The vocabulary is anchored (`lorem ipsum` as a phrase, `your … here` as a phrase, whole-word `TODO`/`TBD`/`FIXME`, and a handful of bare structural nouns matched only as the **entire** stripped string) so a real sentence containing one of those words in passing never matches. |

## Delegated, not reimplemented

These already live in `skills/flow-generator/references/verify-config.py`. `flow-audit`
**runs it and reports its output** — a second implementation of any of these inside
`audit-flow.py` is a defect in this skill, not a redundancy.

| Check | Owner |
| :--- | :--- |
| screens unreachable from `screens[0]` | `verify-config.py` (graph-based, strictly better than a naive "never an explicit `navigate` target" pass — `navigateNext` makes the graph implicit) |
| missing locale key (per field) | `verify-config.py` |
| empty image `values` map, non-string asset id | `verify-config.py` |
| bound-but-undeclared product, `const`-purchase declaration | `verify-config.py` |
| conditional-branch parity, variable-node parity, stray locale values | `verify-config.py` |
| unresolved/un-prefixed timer token name | `verify-config.py` (`ETimerToken` prefix check) — Variables' `variable-no-consumer` deliberately does not restate this |

## Known limitations

Stated plainly, with why each was not fixed:

- **A currency literal in the SAME element as a price variable is unreported.** The
  guard is narrower than it sounds: `hardcoded-price` judges each element against its
  own blob (see `check_price_integrity`'s scoping comment), so a literal only goes
  unreported when it shares an element with a variable node. A literal in a *sibling*
  element still fires — including a savings figure like "Save $20" written next to
  (not inside) the price variable's own element, a reproduced false positive: the
  message reads "$20 is written into the copy instead of coming from a price
  variable", which is misleading for copy that was never claiming to *be* the price.
  The message is worded to avoid asserting that (see the check's row below); the
  scoping gap itself is unfixed because the corpus has no real instance of the actual
  defect (a literal in the *same* element as its own variable) to calibrate a
  narrower rule against.
- **A literal split across two adjacent text elements is unreported.** Pre-existing regex
  boundary — `MONEY_RE` matches within one element's blob, not across sibling elements.
- **Currency coverage is `$ € £ ¥ ₹ ₽` plus `USD`/`EUR`/`GBP`/`RUB`/`INR`.** CHF, PLN, CZK,
  UAH, BRL, TRY, KRW and the Nordics are absent from `MONEY_RE`.
- **`variable-no-consumer` recognises only explicit `setVariable` producers**, so an unused
  `groupId`-based selector goes uncaught (see the Variables trap above for why that scope
  is deliberate, not an oversight). No `setVariable` action exists anywhere in the corpus,
  so this check is exercised only by injected cases, never by a real fixture.
- **A URL query string or fragment word can silence a legal-link check** — token matching
  runs over the whole URL string, so `?ref=terms-promo` on an unrelated page would match.
- **`1yr` with no separator does not match the period vocabulary** — the digit-unit
  separator pattern (`[\s-]*`) still needs the unit spelled as a recognised token; a bare
  `yr` glued to a digit with nothing between falls through.
- **The renderer's dead-affordance merge recovers the affordance list by parsing
  `check_triggers`'s own message text** (`DEAD_AFFORDANCE_RE`), so it is coupled to that
  wording — changing the dead-affordance message without updating the regex degrades the
  merge to unmerged output rather than crashing, which is the safe failure direction but
  is worth knowing about before editing either string.
- **Unknown CLI flags are silently accepted as boolean** — `parse_args` treats any
  unrecognised `--foo` as `flags['--foo'] = True` rather than rejecting it, so a typo'd
  flag (`--catalgo`) is silently ignored rather than reported as a usage error.

## The rule

A check ships only when it is **silent on every fixture in the corpus and fires on an
injected instance of its own defect.** Being silent on real data proves nothing about
whether the check works at all; firing only on synthetic data proves nothing about
whether it will misfire on something real. Every check in this document earned its
place by clearing both.

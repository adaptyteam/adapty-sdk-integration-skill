# `flow-audit` store-review reference

Per-check evidence for the six **advisory** store-review checks in `audit-flow.py`:
`trial-toggle`, `billed-amount-not-shown`, `derived-price-louder`,
`no-period-disclosed`, `trial-terms-incomplete` and `external-purchase-link`.

Same contract as [`checks.md`](checks.md), which stays the owner of every pre-existing
check: per check, what it looks at, its severity and **why** that severity, its
calibration in **both** directions with the fixture named, the false-positive trap it
closes, and the negative-test outcome that proved the mechanism load-bearing. **Read
this before changing one of these checks** — several of the rules below are narrower
than they look, and every narrowing is here because the wider version was measured
firing on something compliant.

These checks answer *"is this likely to draw a rejection"* — never *"will this pass"*.

## The framing rule

1. **Every check here is a `risk` or a `question`. None is a `blocker`.** No new
   severity was introduced: `risk` is already defined in `audit-flow.py`'s own docstring
   as "it works and is probably not what anyone intended", which is exactly a rejection
   hazard.
2. **A store-review finding never changes the verdict.** Blockers decide it, and no
   check here is one. The leak this closes is subtler than the blocker case: an open
   `question` normally downgrades a bare `READY FOR PRODUCTION` to `READY, PENDING n
   CHECKS I CANNOT MAKE`, so **every** question here is excluded from the pending count
   and carries its ask inside its own message text instead. There are **two** checks
   that can raise one, not one: `external-purchase-link` always does, and
   `billed-amount-not-shown` degrades to a question when a catalogued product's row
   states no billing period. A store-review section can be full and the verdict can
   still read a clean `READY FOR PRODUCTION`. That is correct; the disclaimer is what
   keeps it honest.
3. **A verbatim disclaimer prints with the section**, non-optional — the same form
   `paywall-teardown` uses for its impact numbers, and for the same reason: this repo
   already owns a case where numbers presented without a disclaimer were read as
   promises.

The reason it is a rule and not a preference: store review is a **human** process,
inconsistent between reviewers and between submissions, and it changes without
announcement. The January 2026 toggle wave arrived with no guideline edit, no
documentation change and no grace period. A checker cannot predict that.

### The line, stated once so nobody re-derives it

> **A missing mechanism is a fact and may be a blocker. A prediction about how a human
> reviewer will judge a design is advisory and may not.**

This is why the five pre-existing compliance checks — `no-restore`, `no-terms-link`,
`no-privacy-link`, `no-escape-in-flow`, `no-escape-from-paywall` — **keep their current
severities, blockers included, and were not downgraded**. Each tests for the *absence of
a mechanism* the store requires and the flow provably does not have. A paywall with no
`restorePurchases` action anywhere is broken for a user restoring on a new device
whether or not a reviewer ever notices. "Advisory" applies to judgements about how a
reviewer will read a design, never to a missing action.

### Isolation is a tested property, not a read one

`render()` partitions the six checks out of the findings list **before** the
severity loop and the verdict line run, so the verdict is isolated by construction
rather than by a special case in the verdict code. That partition is negative-tested:
removing the partition line so store findings flow back into the severity groups turns
two named assertions in `tests/test-store-review.py` red — `a store-review-only flow
still reads READY FOR PRODUCTION` and `...and is not downgraded to READY, PENDING`.

Getting there took a correction worth recording, because the first two attempts at that
test could not fail:

- The first construction gated the verdict assertions on `if store_only:`, measured
  **False** on the fixture it used (`onboarding-multilocale.json` also fires
  `dead-affordance`, `no-restore`, `no-terms-link`, `no-privacy-link`,
  `no-escape-from-paywall`, `product-store-gap` and `untranslated`), so the feature's
  central claim was tested on no fixture at all.
- The second used a synthesized store-review-only config whose findings were **both
  `risk`** — and a risk never moves the verdict, partitioned or not. Measured: with and
  without the partition, `[risk, risk]` prints `READY FOR PRODUCTION` either way.
- The config that finally discriminates adds an element whose `openUrl` points at
  `external.example.com/payment/confirm`, firing `external-purchase-link`, a
  **question**. Measured on that config: partitioned → `READY FOR PRODUCTION`;
  unpartitioned → `READY, PENDING 1 CHECK I CANNOT MAKE`, with the finding moving into
  `COULD NOT CHECK`.
- One more trap in the mutation itself: emptying `store` instead of un-partitioning
  *deletes* the findings rather than routing them, and the verdict correctly does not
  move. **The mutation has to route the findings, not drop them.**

## Evidence tiers

Ranked the way this repo already ranks evidence, strongest first.

1. **A rejection notice a customer received**, with the reviewer's own wording
   preserved. Two exist and both are reproduced verbatim below.
2. **The store's own policy text** — Apple [App Review Guidelines
   3.1.1/3.1.2](https://developer.apple.com/app-store/review/guidelines/) and
   [Schedule 2 of the Apple Developer Program License
   Agreement](https://developer.apple.com/support/downloads/terms/schedules/Schedule-2-and-3-English.pdf);
   Google Play's [Subscriptions
   policy](https://support.google.com/googleplay/android-developer/answer/9900533).
3. **The store-review guide**,
   [prepare-your-app-for-store-review](https://adapty.io/docs/prepare-your-app-for-store-review)
   — the page a client is sent to, rather than a guidelines wall. **It is handed over by
   [`SKILL.md`](../SKILL.md)'s phase-5 report instruction, not by any finding's `fix`
   string.** That placement is deliberate and was a ruling, not an oversight: an earlier
   draft of this line promised the link would sit in every fix, and `lint-links.mjs`
   walks `.md` files only, so a URL inside `audit-flow.py` is unlinted and rots silently.
   The findings carry the guideline number (what a developer pastes into an appeal); the
   report carries the link.
4. **What is computable from a config plus the catalog.** A rule that cannot be
   measured from those two inputs is not a check; it is a `BEFORE YOU SHIP` line.

Every finding cites its guideline number in its fix text, because that number is what a
developer pastes into an appeal.

### Rejection notice 1 — toggle paywalls (Jan–Feb 2026, guideline 3.1.2)

Apple began rejecting the free-trial on/off switch. A warning went into roughly twenty
customer channels on **2026-02-11**; several customers replied that it had already
happened to them, and one had the toggle reinstated only after arguing the case.
Write-up: [Apple Killed Toggle Paywalls on
iOS](https://adapty.io/blog/your-toggle-paywall-is-about-to-get-rejected/).

The mechanism Apple objects to: **the trial's terms are not visible unless the user
interacts with the switch, so a user who never touches it is never shown them.**

No guideline edit, no documentation change, no grace period accompanied the wave — apps
just started coming back rejected. That is the single strongest argument for the framing
rule above.

### Rejection notice 2 — per-month louder than the billed amount (Jun 2026, 3.1.2(c))

Verbatim from the notice:

> One or more auto-renewable subscriptions are marketed in the purchase flow in a way
> that may mislead or confuse users about the subscription terms or pricing.
> Specifically: The auto-renewable subscription displays the monthly calculated pricing
> for the subscription more clearly and conspicuously than the billed amount.

The customer had to change **every active paywall**. The design answer in that thread
was measurable and is the fix text these checks adopt: make the billed amount bold at
14px and drop the per-month figure to 12px, rather than *removing* the per-month figure
(which costs the savings framing).

### The standing disclosure floor

Apple's rejection boilerplate for 3.1.2, quoted as reviewers send it:

> Apps offering auto-renewable subscriptions must include all of the following required
> information in the binary: Title of auto-renewing subscription; Length of
> subscription; Price of subscription, and price per unit if appropriate; Functional
> links to the privacy policy and Terms of Use (EULA).

Terms and privacy links are already covered by `no-terms-link` / `no-privacy-link`.
**Length** and **price** are not, and they are what the Tier 2 checks below cover. Play
adds trial-conversion terms and cancellation disclosure.

## Tier 1 — backed by a rejection notice

### `trial-toggle` — risk, iOS only

**What it looks at.** A group member (`props.groupId` present) on a **selling screen**
whose subtree contains an element satisfying **three** signals at once:

1. **Switch shape** — a `fixed`×`fixed` box wider than tall, fully rounded
   (`borderRadius` ≥ half its height on all four corners). `_switch_shaped`.
2. **Trial copy** — `TRIAL_RE` matches somewhere in the subtree's flattened copy.
3. **State-dependence** — `propsByState.selected` present on the **same** element that
   is switch-shaped.

**Why `risk` and not a blocker.** It is a prediction about how a reviewer will read a
design. The pattern is legal, it renders, and it sells; enforcement is inconsistent.

**Why structure and not the caption.** A caption match would test the template's name.
The shape is what a reviewer sees.

**One sentence was deleted from its fix, and the reason generalises.** The fix used to end
"…or a trial timeline that states when the charge happens. **Both convert at least as
well.**" That is a conversion claim, inside a skill whose own `SKILL.md` says *"Not
conversion advice. This skill answers 'is it wired up', never 'will it convert' — that is
`paywall-teardown`"*, and it was unsourced: it appears in no evidence tier here and this
file never measured it. Deleted. Both remediations stand on their own as ways to show the
trial's terms without a tap, which is the only thing this check knows about. If a
conversion comparison between them is ever wanted, `paywall-teardown` owns it.

**Calibration — silent.** All 12 corpus configs (7 tracked + 5 raw). Plus four
constructed SILENT cases: an Android-only app (`--stores android`), a switch that names
no trial, a control that is not switch-shaped, and a static trial badge chip.

**Calibration — fires.** A config built from `flow-generator`'s own
`component-catalog.json` `trial-toggle` template, and again for an app whose `--stores`
include `ios`. That template's pill child is **52×32 with `borderRadius: 9999`** on all
corners and carries exactly `propsByState: {"selected": {"layout": {"alignH": "end",
…}, "fill": […]}}` — the knob's `alignH` moves `start` → `end` between states. Signal 3
is measured against what the builder actually emits, not invented.

**The false-positive trap it closes — and it is the important row here.** The first
implementation required only signals 1 and 2, and review found it would fire on a
**pill-shaped "Free trial" badge attached to a plan card** in a selectable product
group — i.e. **on the exact compliant pattern the check's own fix text recommends** ("a
side-by-side plan comparison with the trial badged on one plan"). No corpus fixture has
that shape, so no calibration case caught it. An advisory check that fires on the
remediation it recommends teaches users to ignore the whole family. Signal 3 separates
them mechanically: **a switch is state-dependent; a badge is static.**

**Why shape alone is not enough, measured.** The corpus contains exactly **one**
pill-shaped fixed box across all 12 real exports — a **50×30 stack (`el_054S`) on
`onboarding-multilocale.json`'s `scr_notify`**, which is a notifications opt-in. So
shape is nearly specific enough and is still not used alone. That one pill *does* carry
`propsByState.selected` (with the same `alignH` knob move), so signal 3 costs nothing on
it: it stays cleared by signals 1-and-2's companions instead.

**Negative test, four parts plus the fix round.**

- Delete the trial-copy guard → **exactly one** case reddens (`silent when the switch
  names no trial`). All 12 corpus lines stay green.
- Delete the selling-screen guard → **nothing reddens anywhere.** Reported plainly
  rather than smoothed: for the one real pill in the corpus, the trial-copy guard alone
  already clears it (`scr_notify`'s copy is "Trip updates and deals" / "Turn on
  notifications?" / "Yes, notify me" / "Skip"). The two guards are genuinely redundant
  **for this calibration case**, not one masking the other; parts 1 and 3 each show a
  case only that guard catches.
- Replace `_switch_shaped(...)` with `True` → exactly one case reddens (`silent when the
  control is not switch-shaped`).
- Delete the state-dependence clause → exactly one case reddens, the new badge-chip
  case, with the finding pointing at `scr_paywall / el_plancard`. Every other case,
  including all 12 corpus lines and both `--stores` cases, stays green.

**`--stores` behaviour.** `stores is not None and 'ios' not in stores` → returns
nothing. With stores **unknown** it still prints, worded as applying to iOS — the same
shape `check_products_catalog(config, catalog, stores)` already uses.

### `billed-amount-not-shown` — risk, or question when the period is unknown

**What it looks at.** Per screen, per bound product: every price variable drawn in
`props.content` (`price_sites`, screen-scoped), split into **billed** suffixes
(`prod_price` always, plus `BILLED_SUFFIX[period]`) and **derived** per-unit suffixes.
It fires when a derived figure is drawn and **no** billed figure appears anywhere on the
screen.

**Why screen-scoped and not card-scoped** (where `check_price_integrity` is
card-scoped): the June rejection is about what the user *sees*. A billed amount printed
in the footnote under the CTA satisfies "clearly and conspicuously displayed" just as
well as one printed inside the card, and a card-scoped walk would report that perfectly
compliant layout as a defect.

**Why `risk`.** "Conspicuously" is a judgement over colour, position and container as
well as type, and this reads only type. And the absence it reports is an absence in one
channel: `price_sites` reads `props.content` in the default locale only, so a billed
amount drawn from `propsByState` or present only in another locale is invisible to it —
see *Why these are risks and not blockers* under Tier 2 for the full argument, which
covers this check too.

**Calibration — fires.** `tests/fixtures/onboarding-multilocale.json`: **Pro Annual
drawn as a per-month figure at 22px bold (`h2` preset, weight rank 7) with the billed
annual amount nowhere on the screen.** That is the June rejection sitting in a tracked
fixture. Measured `price_sites` output for that screen:

```
scr_paywall ('el_075T', '6cdd73d5-…', 'prod_price_per_month', 22, 7)
scr_paywall ('el_083T', 'fbc63856-…', 'prod_price',           22, 7)
```

**Calibration — silent.** `tests/fixtures/onboarding-quiz-paywall.json` against a real
catalog: per-year **and** per-month, both at 13px — the compliant shape. Plus a
constructed case rebinding the card to a monthly product, where the per-month figure
*is* the billed amount.

**The false-positive trap it closes.** The draft **false-fired** on that same quiz card
when the product was absent from the catalog: with no `period`, "which suffix is the
billed amount" is undecidable, and guessing produced a measured false positive on the
compliant shape. Hence the **question** form when `period` is unknown — the same
degradation `product-store-gap` already uses, and the same rule as the skill's "never
certify what you could not see". This is also why `tests/test-audit-flow.py`'s
"catalog-path-equals-config-path" test carves this check out alongside the `products`
family: it is family `compliance` but genuinely catalog-dependent.

**The question form has three outcomes, not one, and two of them were wrong at first.**
A missing `period` has several causes and they are not equally worth saying:

| the product is… | outcome | why |
|---|---|---|
| bound in the flow, absent from the catalog | **silent** | already a `product-not-in-catalog` blocker, or a single `catalog-not-fetched` when no catalog was passed. The question's entire content would repeat that sentence once per (screen, product) — measured as two blockers plus two identical advisory questions on `onboarding-quiz-paywall.json`, and one question per price site with `--catalog` omitted. `check_products_catalog` and `check_period_claim` both already return early on that shape; this follows them. |
| in the catalog, its row carrying no `period` | **question**, "whose catalog entry states no billing period" | genuinely undecidable and nothing else in the report mentions it |
| absent from the catalog **and** bound nowhere | **question**, naming the id and saying it is bound nowhere | reached only through a price variable, so `check_products_catalog` never saw it either — that check walks `bound_products`. Usually a variable left behind by an edit. |

The third row is the one that had to be split out. A single sentence covered both
question cases and it was **false** for this one — there is no catalog entry to state
anything. Found by the final whole-branch review, and no fixture covered the shape, so
it is pinned by its own case in `tests/test-store-review.py`; the negative test collapses
the branch back to one wording and exactly the two wording assertions redden.

**Negative test.** Removing the `if not billed:` guard does not merely misreport — it
crashes `audit-flow.py` (`ValueError: max() iterable argument is empty`, rc 1) on both
multilocale scenarios, because `billed` really is empty there. Stronger than the
predicted "three FAIL lines", and recorded as the mismatch it was rather than as a
match: the guard is load-bearing, and its absence is loud.

### `derived-price-louder` — risk

**What it looks at.** The soft half of the same rejection: both figures are drawn, and
the derived one resolves to a larger or heavier font. `resolve_font` resolves
`theme.typography[].settings.{size,weight}` with element-level `props.font` overriding
the preset; `WEIGHT_RANK` orders weight names ordinally (nothing reads the gaps). A
preset naming no size resolves to `0`, which makes both comparisons fall through rather
than fire — silence is the right direction of error for an advisory check reading a
theme it does not fully understand.

**Calibration — fires.** `onboarding-quiz-paywall.json` with its real catalog, billed
element `el_3La404eJMD` shrunk to `{size: 9, weight: 'light'}` so the derived figure
wins.

**Calibration — silent.** Two real cases against the same fixture + catalog: the
untouched equal-size pair (13px/13px), and the billed element raised to `{size: 18,
weight: 'bold'}`.

**The calibration trap this check produced, and it is a methodology row worth keeping.**
The 12-fixture corpus SILENT loop originally claimed to calibrate this check and was
**vacuous**: under the default catalog, no fixture's product ids resolve a `period`, so
`billed` stays empty and the code `continue`s before `dmax > bmax` is ever evaluated.
Proven mechanically, not argued — forcing `if dmax > bmax:` → `if True:` left **all 12
loop lines green** while exactly the two genuinely-reaching cases reddened. The loop is
kept (it is real coverage for `billed-amount-not-shown`) but is now **named for what it
covers**: no misfire on any real export under this catalog, not calibration of the
comparison.

**The mutation-direction rule that came with it.** A `if False:` mutation is
*mathematically incapable* of reddening a SILENT case — weakening a firing condition can
only turn a firing case silent. Proving a SILENT case discriminating requires the
complementary `if True:` mutation.

**Also worth knowing:** the corpus fixtures are the *only* thing measured here. No live
flow has been measured firing this check.

### Both prominence checks cite Apple and are NOT gated to iOS — and each says why

`billed-amount-not-shown` and `derived-price-louder` rest on rejection notice 2, which is
an App Store notice, and neither takes a `stores` argument: they fire on `--stores android`
too. That combination was raised as a defect — an Android-only app reading a bare Apple
notice — and the ruling was **not** to gate them, because the underlying hazard is real on
Play: its [Subscriptions
policy](https://support.google.com/googleplay/android-developer/answer/9900533) requires
the price a user will actually be charged to be stated accurately and completely, which a
screen showing only a derived per-unit figure does not do. Gating them off would lose a
true finding for every Android-only app.

So each of the three fix strings now names the Play grounding in one sentence — "Google
Play requires the price a user will actually be charged to be stated accurately and
completely, so this is a Play hazard as well as an App Store one." That is the honest fix:
the check keeps firing, and an Android-only reader is told why an Apple notice is being
quoted at them. The *reason* the check is not iOS-gated stays here, in the reference,
rather than in the user-facing string — a client does not need to read our gating
decision. Contrast
`trial-toggle` and `external-purchase-link`, which **are** iOS-gated — the toggle wave and
guideline 3.1.1 steering have no Play analogue that has been measured, so for those two
`stores is not None and 'ios' not in stores` returns nothing.

## Tier 2 — the disclosure floor

### Why these are risks and not blockers — the one argument all three share

`no-period-disclosed`, `trial-terms-incomplete` and `billed-amount-not-shown` sit closest
to the blocker side of the line stated at the top of this file, and they are the three
that most need their severity justified: each reports a **factual absence**, not a
prediction about a reviewer's taste, which is exactly the shape the line calls a blocker.

What keeps them advisory is narrower and mechanical: **they report an absence in what one
channel can read.** `check_disclosure` builds its blob from `props.content` in the
**default locale only**, and `price_sites` does the same. So all three are blind to

- `propsByState.<state>.content` — copy that appears only in a selected/focused state,
- every **non-default locale** — the disclosure may exist in `de` and not in `en`,
- and text **baked into an image**, which no config walk can read at all.

Compare `no-restore`, which stays a blocker: "no `restorePurchases` action exists
anywhere in this document" is a claim over the **whole** config, and there is no second
channel an action could be hiding in. That is a categorically stronger claim than "no
period term appears in the strings I looked at", and the difference is the entire reason
these three are `risk`. It is also why each of the three says what it looked at in its
own message rather than asserting the screen *has* no disclosure.

### `no-period-disclosed` — risk

**What it looks at.** A selling screen binds a subscription product and **no** period
term appears anywhere in that screen's text. Reuses `period_terms` inverted, so it
inherits that function's billing-context guard — the one that took four measured false
positives to get right ("Weekly progress reports" reading as a weekly billing claim).
Products that are lifetime-only in the catalog are exempt (`bound <= lifetime_only`,
guarded by `if bound and` so an empty set cannot skip a screen).

**Why `risk`.** A factual absence, but only in the default locale's `props.content` —
see *Why these are risks and not blockers* above for the full argument. The two accepted
false-negative classes below are the same limitation seen from the other side.

**Why one finding per screen, not per card.** The period may legitimately be stated
outside the card — "Billed yearly" under the CTA discloses it for every card above — so
a card-scoped test would flag a compliant layout, and one row per card would bury four
identical findings in the report.

**Its message says only what it knows, and the earlier wording did not.** The finding
used to read "A user sees a price and a button with no billing frequency attached", with a
fix pointing at "where the price is". The **one real export it fires on**,
`tests/fixtures/tabs-paywall.json`, has **zero price variables in the whole document** —
recorded two paragraphs down, in this same file — so the message asserted a fact its only
real firing case contradicts, and the fix pointed at something that is not on the screen.
Reworded to the absence the check actually measures: no billing period appears anywhere in
this screen's copy. **Never reintroduce a price into either string** — this check cannot
see prices; `billed-amount-not-shown` is the one that reads them.

**Calibration — silent.** 10 corpus lines: `comparison-paywall.json`,
`onboarding-multilocale.json`, `onboarding-quiz-paywall.json`, `vpn-timer-draft.json`
(tracked + raw), plus `reviews-carousel.json` and `timeline-anchored.json`.

**Calibration — fires, on a real export, and it is a TRUE finding.** It fires on
`tests/fixtures/tabs-paywall.json` (and its raw counterpart), on `scr_RvSel001`. This
was investigated rather than silenced. Every one of that screen's 41 text elements was
dumped and read: the visible strings are "Skip", "Select plan", "Metal", "Premium metal
card", "Top features", "Commodities", "Safer online shopping", "Concierge & lounges",
"Get Metal", "Premium", "Most popular", "Standard", "Terms", "Restore", "Privacy" and
their feature blurbs. **No word matching `PERIOD_RULES` appears anywhere** — not in a
card, not in a footnote, not under the CTA. There are also **zero price variables
anywhere in the whole document** and **no `propsByState` content override**, so there is
no hidden shape the check missed. A real, shipped tiered-plan screen sells subscriptions
while disclosing neither price nor billing frequency: exactly the Schedule 2 "Length of
subscription" gap this check exists for. The fixture is therefore excluded from the
blanket SILENT loop and given its own FIRES assertion, with that evidence as the
comment.

**This corrects a measurement in the design spec.** The spec's "silent on 10 of 10 real
product cards" figure was measured **per card**, and it structurally could not cover
this flow: `tabs-paywall.json` binds its three products through `const` purchase
payloads with **no `product` element** —

```
[('scr_RvSel001', 'el_RvCTA033', '64364f33-…'),
 ('scr_RvSel001', 'el_RvCTA063', '134badab-…'),
 ('scr_RvSel001', 'el_RvCTA096', '097b40ac-…')]
```

— so a card-scoped probe sees nothing there at all. The screen-scoped fallback covers
what that probe could not. Do not read the spec's figure as covering this shape.

**Negative test.** The final control flow gates an *append* (`if not period_terms(blob):
append(...)`) rather than a skip, so the defeating mutation is `if True:`. Forcing it
reddens **six** SILENT corpus lines — the three files whose screens genuinely do state a
period, counted twice each for tracked + raw. Real, compliant screens start
false-firing the instant `period_terms` is bypassed. (The brief predicted the FIRES
cases would redden; that prediction was written against the pre-Task-5 control flow, and
the inversion is the direct consequence of the guard's role flipping from gating a skip
to gating an append.)

### `trial-terms-incomplete` — risk

**What it looks at.** The screen's copy promises a trial (`TRIAL_RE`) and the screen says
nothing anywhere about a charge following it. Any one of **three** satisfiers counts as
saying something — a currency amount (`MONEY_RE`), a billing verb (`BILLING_VERB_RE`) or
a period term — a **deliberately generous bar**, because this check reads copy, and copy
is where false positives are cheapest to create and most expensive to keep.

**A fourth satisfier was advertised and did not exist.** `after` also tested
`VAR_RE.search(blob)` — a price *variable* — and that branch was **dead code**: `blob`
comes from `flat_text`, which renders a variable node as `''` by design, so no variable
id ever reaches the string. Removing it reddened nothing, which is this repo's own
"assertions shipped unable to fail" class one level over. Removed, with the reason
pinned in a comment at the call site. If a variable-backed price should ever count here,
`after` has to read `_element_blobs` (which renders variable ids inline), not
`flat_text` — re-adding `VAR_RE` over `flat_text` output would restore a satisfier that
is a satisfier only on paper.

Both this and `no-period-disclosed` read the same per-screen blob, so a screen with
neither a stated period nor stated trial terms produces **both** findings. Deliberate:
they are two separate disclosures and a user should see both gaps, not whichever the code
happened to check first. Pinned by its own test case.

**But the REPORT prints one row, not two.** Two findings anchored to the same screen,
where the second's message already carried the first's claim ("no price, **no billing
period**, nothing about renewal") and the second's fix ("Free for 7 days, then
$79.99/year") already **satisfied** the first, is a report arguing with itself. So
`_collapse_for_report` gained a second pass, using the mechanism that was already there
for `dead-affordance` rather than a parallel one: `DISCLOSURE_MERGE` names the two checks,
`trial-terms-incomplete` absorbs `no-period-disclosed` (its claim is the superset, never
the reverse), and the merged row is emitted as `trial-terms-incomplete-merged`.

Three things about that merge are load-bearing:

- **It is report-only**, exactly like the dead-affordance collapse. `--json` and `audit()`
  still carry both findings, which is what the calibration above reads and what keeps the
  two checks independently testable.
- **It requires both halves on the same screen.** A screen firing only one keeps its own
  row — pinned against `tabs-paywall.json`, the real export that fires
  `no-period-disclosed` alone.
- **`trial-terms-incomplete-merged` must be listed in `STORE_REVIEW_CHECKS`**, or
  `render()`'s partition routes it into `RISKS` instead of the advisory section. It is
  also registered in `CHECK_TO_GROUP` as `GROUP_FLOW`, so `WHAT TO DO NEXT` still routes
  it (asserted: exactly once).

**Why `risk`.** Same argument as `no-period-disclosed` — see *Why these are risks and
not blockers* above — with one addition specific to this check: its `after` guard is
deliberately generous (three satisfiers over the whole screen blob), so a finding here
means "nothing on this screen that I can read looks like a charge", which is a weaker
claim than the absence of a mechanism.

**Calibration — silent.** All 12 corpus lines, plus a constructed case where the charge
after the trial is stated.

**Calibration — fires.** A constructed trial promise with no terms anywhere on the
screen, and the combined case above.

**Negative test.** Changing `if after: continue` to `if True: continue` reddens **exactly
two** cases — `fires on a trial promise with no terms` and the combined
both-findings case. Every SILENT case stays green (trivially, since the check no longer
fires at all).

### `external-purchase-link` — question, iOS only

**What it looks at.** An `openUrl` on a **selling screen** whose url tokenizes (on
non-alphanumeric runs, via `_url_tokens` — exact tokens, never substrings) to one of
`PURCHASE_URL_WORDS`. One finding per screen, quoting the matched url(s) back.

**Why a question, and why it stays one however suspicious the url looks.** Guideline
3.1.1 forbids steering users to a purchase mechanism other than in-app purchase, except
on the US storefront or under the External Link Account Entitlement. The audit cannot
see which storefronts the app ships to and cannot know whether the developer holds the
entitlement — both of which make the same link legal. It asks anyway, because web
paywalls are a real product, so this is a foot-gun rather than a hypothetical. If field
evidence accumulates, this is the one candidate here for promotion, and that promotion
needs its own decision rather than a quiet edit.

**The vocabulary decision, and the principle behind it.**

> **The vocabulary names a PAYMENT MECHANISM, never a PRODUCT SURFACE.**

Kept: `checkout`, `pay`, `payment`, `purchase`, `buy`, `stripe`, `paddle`.
Dropped after measured false positives: `billing`, `upgrade`, `paywall`.

- **`billing` is the decisive case.** It fires on `/support/billing`,
  `/account/billing-history`, `/help/manage-billing` — and **Google Play requires an
  accessible subscription-management path**, which plausibly lives at exactly that kind
  of url. So that token fired on a link another store demands the app carry.
- `upgrade` fires on `/why-upgrade`, `/upgrade-info`, `/compare-plans-upgrade`.
- `paywall` fires on an attribution deep link routing back into the app's **own**
  paywall (`yourapp.onelink.me/xyz?af_dp=yourapp://paywall`).
- `subscribe` was never included: a marketing page at `/subscribe` is an ordinary
  content-gating link, not evidence of a purchase flow, so it would manufacture a
  question on almost every subscription app's marketing site.
- **`paddle` is kept with a known narrow false positive** (`/blog/paddle-boarding-tips`,
  and sports apps generally), accepted because — unlike the three dropped words — it
  names a real web-checkout processor and nothing else plausible collides with it as
  often.

All three dropped words carry **pinned SILENT tests** using those exact urls, because a
vocabulary decision with no test is a comment someone will undo.

**State this plainly: the corpus cannot calibrate this vocabulary at all.** Across all
12 tracked and raw fixtures the only `openUrl` targets are `/terms` and `/privacy`, so
"silent on the corpus" proves nothing about the word list. Its precision rests on
**constructed cases and reasoning**, not on corpus evidence.

**Calibration — silent.** All 12 corpus lines; an Android-only app; a `/terms` url; the
three dropped-word urls.

**Calibration — fires.** `pay.example.com/checkout` (matching `pay` **and**
`checkout`), and — added because the first url never proved any other kept word works
alone — `external.example.com/payment/confirm`, which tokenizes to `external`,
`example`, `com`, `payment`, `confirm` and matches exactly `payment`.

**Why tokenizing on non-alphanumeric runs rather than on whitespace.** Measured as a
diagnostic: substituting `set(u.lower().split())` for `_url_tokens(u)` produced **zero
false positives on the corpus and zero true positives anywhere** — `str.split()` splits
on whitespace, a url contains none, so the whole url becomes one token that must equal a
vocabulary word exactly. It never does. A whitespace split under-matches urls to the
point of being useless, which is a more severe failure than the substring hazard
`_url_tokens`' own docstring warns about (`tos` inside `photos`).

**Test-construction note that generalises.** The FIRES cases **append** an `openUrl`
interaction to `el_088S` on `onboarding-multilocale.json`'s `scr_paywall` rather than
replacing its `interactions` list. `el_088S` is the only element on that screen carrying
interactions, and it carries a real `purchase` action; replacing would have destroyed it,
which could drop the screen from `selling_screens` and make the check go silent **for a
reason unrelated to what it tests** — a false pass that reads as a green run. The tests
assert the original interaction survives byte-identical, that the list grew by exactly
one, and that the screen is still detected as selling.

## Accepted false-negative classes

Two silences are **deliberate**. Both are pinned by tests labelled `KNOWN LIMITATION` in
the test name, so a future tightening of either mechanism turns those tests red and
points whoever changed it at this reasoning.

### `trial-terms-incomplete` is silenced by any unrelated currency amount

The `after` guard searches the **whole screen blob**, so a screen reading "Start your
free trial now" plus an unrelated "Tip the developer $2" satisfies `MONEY_RE` and the
check goes silent.

**Why it was not fixed.** The obvious fix — scoping the `after` search to the trial's own
segment — would **manufacture the false positive this design specifically avoids**,
because the compliant layout states the trial in the hero and the charge in a footnote
under the CTA, in **different elements**. For an advisory check whose whole contract is
"hazards, not verdicts", a miss is the cheaper error than crying wolf.

**Verified discriminating, three ways**, because a pinned limitation that passes for the
wrong reason is worthless: with the unrelated `$2` the check is SILENT; with neutral
filler in the same slot it FIRES (so the silence is caused by the money, not by anything
structural); and with `MONEY_RE` removed from the `after` guard it FIRES again (so the
test goes red exactly when someone tightens the guard). One claim was overturned along
the way — a reviewer argued the test passed vacuously because `'Start your free trial
now'` fails `TRIAL_RE`; `TRIAL_RE` ends in a `|\btrial\b` alternation, so bare "trial"
matches, checked directly.

### `no-period-disclosed` is silenced by an ordinary feature bullet using "per"

A feature bullet reading "10 workouts per week" satisfies `BILLING_VERB_RE`'s generic
`per` alternative, so `_billing_context` accepts the `weekly` match, `period_terms`
returns `{'weekly'}`, and the check goes silent even with no real disclosure anywhere on
the screen.

**Why it was not fixed.** The root cause is `_billing_context`, which is
**pre-existing**, calibrated against **four measured false positives**, and **shared with
the already-shipped `period-claim-mismatch`**. Widening it to serve a new advisory check
risks a live check for a silence.

## Blind spots

Stated plainly, because each is a thing a reader could otherwise assume is covered.

- **`price_sites` reads `props.content` only.** A price drawn from
  `propsByState.<state>.content` is invisible to it. Measured: `tabs-paywall.json` binds
  and prices its products in a shape this walk returns nothing for, so that flow gets
  **no** price findings rather than wrong ones. Silence, not a guess — but it is silence,
  and a state-drawn price is not checked.
- **Prominence reads type size and weight, and nothing else.** Not colour, not position,
  not container. "Clearly and conspicuously" is therefore only **partly** measured, which
  is the direct reason both prominence checks are `risk` rather than blockers.
- **A theme preset that names no size resolves to `0`**, which makes both prominence
  comparisons fall through rather than fire. Deliberate direction of error.
- **Nothing here sees a render.** No screenshot, no device. An obscured close button, a
  low-contrast disclosure, a price hidden behind an image — none of it is reachable from
  a config and a catalog. That boundary is the skill's, not this section's.
- **A url query string or fragment can carry a matching token.** `_url_tokens` runs over
  the whole url string, so `?ref=checkout-promo` on an unrelated page would match. This
  is the same pre-existing limitation `checks.md` records for the legal-link checks.
- **`no-period-disclosed`'s lifetime exemption depends on the catalog.** A one-time
  product absent from `products list` has no `period` row, so it cannot be exempted and
  the screen is judged as if it billed recurringly.

Two structural items are **recorded rather than refactored**, both with the reasoning
pinned in a comment at the code itself so it is found by whoever next touches that line:

- **`_screen_openurls` duplicates `openurl_urls`'s body**, differing only in scope
  (one screen versus the whole flow). Not unified, because `openurl_urls` feeds two
  shipped **blockers** (`no-terms-link`, `no-privacy-link`) and this feeds an advisory
  question — risking a live check for twelve lines is the wrong trade. **A future fix to
  url handling has to land in both.**
- **`price_sites` filters to `type == 'text'` and then calls `_element_blobs`**, which
  walks **descendants**, while `resolve_font` reads the **parent's** font. Unreachable
  across all 12 fixtures today, because no text element is a descendant of another; if
  that ever changes, a nested price's size would be attributed to its ancestor.

## Ruled out, and why

Recorded so nobody re-litigates these from the guideline text alone.

- **`subscription-under-7-days`** (3.1.2(a), "must last at least seven days").
  **App Store Connect only offers 1 week, 1/2/3/6 months and 1 year**, so a
  non-compliant period is **not creatable** and the check could never fire. A guideline
  requirement enforced upstream is not a check. Do not re-add it from the guideline text.
- **`preselected-costlier-plan`.** The store-review guide says do not pre-select the most
  expensive tier, but pre-selecting annual is near-universal and converts. The check would
  fire on most real paywalls and would contradict `paywall-teardown`, which owns
  conversion advice. Out of scope by the boundary that already exists between the two
  skills.
- **Anything needing a render** — obscured close buttons, contrast, a price hidden behind
  an image. `flow-audit` is a config-and-catalog question by its own boundaries;
  `flow-generator`'s preview loop owns pixels.

### Deferred, not rejected

- **`escape-gated`** and **`fabricated-urgency`** are structurally detectable and worth
  having. They have the least evidence behind them of anything proposed, so they were
  kept off the change that shipped the two rejection-notice checks. Deferred, not ruled
  out.

## Tier 4 — the reminders

These cannot be checked from a config and a catalog at all, so they are fixed
`BEFORE YOU SHIP` bullets, never numbered findings — the same way the placement reminder
already works.

**Unverifiable is not the same as always relevant, and that distinction was learned
late.** Three of the four originally printed on every audit forever, whatever the flow
did and whatever stores the app shipped on: measured on `tests/fixtures/vpn-timer-draft.json`
— three screens, no bound products, zero findings — the report grew **12 → 21 lines**,
entirely boilerplate telling a non-selling flow to get its products approved in App Store
Connect. So the reminders are now gated. They are neither checks nor findings, so the
spec's "store scoping lives in the check, not on the finding" rule gave them no route;
`render()` therefore takes **`stores=None`**, and `main()` passes the set it built from
`--stores`. Default `None` keeps the old behaviour whenever the stores are unknown.

- **Products must be approved in App Store Connect before review sees the paywall.** If
  they are not, the reviewer gets a paywall with empty prices and rejects the build as
  incomplete. Reported twice by the same customer, and it is the most common
  Adapty-specific review failure in the evidence gathered. Invisible to both the flow
  config and the catalog. **Gated on `bound_products(config)`** — a flow that sells
  nothing does not need it.
- **Terms and privacy must also be linked in App Store Connect metadata**, not only in
  the binary. Half the App Store 3.1.2 rejection boilerplate is about the metadata
  fields. **Gated on `stores`** — skipped for an app that does not ship on iOS.
- **Prices must match** the store listing and any marketing. The audit sees one surface.

**Cut, not gated: Google Play's new-account gate** (a first-time personal developer
account needs 12 testers over 14 consecutive days before production access). It is about
the developer **account**, not the flow, the app or the store; it applies only to a
first-time **personal** account, which excludes nearly every Adapty customer; and it
printed on every audit forever. A solo developer meets it in the Play Console anyway.
Pinned as an absence in `tests/test-store-review.py` so it is not re-added from the
policy text.

**Known residual, deliberately not fixed here.** The products bullet is gated on whether
the flow binds products, not on `stores`, so an Android-only app that binds products
still reads a reminder naming App Store Connect. The ruling assigned the store gate to
the metadata bullet only; widening it would also mean rewording the bullet to name the
right console, which is a text change no evidence in this file supports yet.

## The disclaimer

Printed **verbatim** by `render()` whenever the `STORE REVIEW — ADVISORY` section prints
— it is `STORE_REVIEW_DISCLAIMER` in `audit-flow.py`, indented two spaces, immediately
after the section's last finding and before `BEFORE YOU SHIP`:

> These are rejection hazards, not verdicts. App Review and Play review are human,
> inconsistent between submissions, and change without notice — the toggle-paywall wave
> arrived with no guideline edit and no warning. A clean store-review section is not a
> guarantee of approval, and a finding here is not a guarantee of rejection. Nothing in
> this section blocks the verdict above.

Both directions are stated on purpose: **a clean section is not a pass, and a finding is
not a rejection.** Report it as printed. Never paraphrase it away, and never restate a
store-review risk as a blocker.

The section itself sits after `LOCALE COVERAGE` and before `BEFORE YOU SHIP`, so the
verdict is already printed and closed by the time a reader reaches it — it reads as an
addendum, never as a hedge. Its findings continue the report's single `n` counter, so
`WHAT TO DO NEXT` can never silently drop one; all six checks route to **Change in the
flow**, and **nothing routes to the Answer group**, whose heading reads "they change the
verdict" and by construction these do not.

## Where the section came from, and what it does not claim

An earlier draft gave the verdict line a store dimension — `1 would fail App Store
review`. That is exactly the certificate this feature must not issue, and it was
dropped. An earlier draft also put a `stores` field on every finding; `test-audit-flow.py`
asserts the finding key set **exactly**, so a new key breaks the contract test for every
check in the script. Store scoping lives in the check's **arguments** instead
(`check_trial_toggle(config, stores)`, `check_external_purchase(config, stores)`).

**No GREEN round has run.** Whether an *agent* running this skill reports a store-review
risk as advisory rather than as a blocker, and whether it prints the disclaimer verbatim
rather than softening it, is **unmeasured**. That stays open.

## The rule

Same bar as [`checks.md`](checks.md): a check ships only when it is **silent on every
fixture in the corpus and fires on an injected instance of its own defect**, and — added
by this change's own experience — when **each mechanism has been negative-tested by
disabling it and exactly the intended case reddens**. Three checks in this family had
assertions that could not fail before that step was run: the vacuous
`derived-price-louder` corpus loop, a verdict test gated on a false condition, and a
verdict test on a risk-only config. All three looked green.

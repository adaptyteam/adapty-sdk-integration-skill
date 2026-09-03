# Paywall Pattern Library

The reference for the paywall teardown. Each pattern has: when it applies, its
**cross-check** (so you never recommend adding something already present), its
**expected-impact** range, and its **grounding** (where top apps use it, stated
at category level — never name a company).

Impact ranges are Adapty's expected-effect priors across many verticals, not
measured lift. Use the LOW end for incremental improvements, the HIGH end for
fundamental fixes (e.g. going from zero comparison to adding one).

**Reading this library forward.** When the paywall does not exist yet, the
**when** clauses select which patterns belong on the screen and the
**cross-checks** collapse to "include it once" — a screen you are authoring has
nothing already present to double up on. Everything else reads unchanged: the
category playbook still sets priority, and the impact tier is still the tier of
the change you are making, not of the screen as a whole.

## Impact tiers (do not inflate)

The same change type has a fixed impact band. The most common mistake is
assigning a redesign-sized number to a copy tweak. Hold the line:

- **Copy-only** (rewrite a bullet, swap CTA words): CR +3–8%, ARPU +1–3%.
- **Element add/fix** (badge, savings viz, social proof, comparison, timer,
  hierarchy): CR +5–20%, ARPU +2–15% depending on the element (see each below).
- **Full messaging overhaul** (hero + headline + all bullets + CTA together):
  CR +10–15%, ARPU +3–6%.
- **Results/proof with real data** (real outcome stats): CR +12–18% — only if
  the app actually has the proof data; never assign this to invented stats.

---

## Contents

1. Free vs Paid comparison table
2. Outcome-based value copy
3. Social proof at decision point
4. Best Value / Most Popular badge
5. Annual savings visualization
6. Plan visual hierarchy
7. CTA quality (text / contrast / width)
8. Countdown timer (discount paywalls only)
9. Hero image / video
10. Trust signals near CTA
11. Legal / boilerplate collapse
12. Background / visual environment
13. Goal-personalized paywall
14. Results-focused framing
15. Transparent billing framing
16. Category playbooks

---

### 1. Free vs Paid comparison table
**When:** No comparison exists on screen — this is the default gap; recommend
it unless a comparison is already clearly visible. Especially when the feature
list is long but there's no before/after contrast.
**Cross-check:** If a comparison block already exists, don't re-add — improve
its clarity instead.
**How:** 3–5 rows, each a decision-relevant difference (limits, key unlocks),
free state vs paid state (check/✗ or value), icons for scannability, placed
ABOVE the plan cards.
**Impact:** CR +10–20%, ARPU +3–8%.
**Seen in:** Common across verticals; especially analytical categories
(productivity, finance).

### 2. Outcome-based value copy
**When:** Feature list uses technical/capability language instead of outcomes,
in a results-driven category (fitness, education, productivity, beauty).
**Cross-check:** If copy is already outcome-led, skip.
**How:** Transform capability → result. "AI skin scan" → "See visible results
in 3 weeks". "Unlimited exports" → "Ship in one tap".
**Impact (copy-only tier):** CR +3–8%, ARPU +1–3%. Only use the overhaul tier
(CR +10–15%) if the entire hero + headline + bullets + CTA are rewritten
together.
**Seen in:** Universal; strongest in results-driven categories.

### 3. Social proof at decision point
**When:** No rating, user count, or testimonial on screen — acute in
trust-critical categories (health, wellness, beauty, finance, news, kids). Or a
strong rating exists but isn't shown.
**Cross-check:** If social proof already exists, don't add — improve
specificity ("4.8 stars" → "4.8 from 200K+ users") or move it closer to the
CTA. Note: the app's OWN claims ("37 min faster") are feature claims, not
social proof.
**How:** "[Rating] from [N]K+ users" beside the CTA; optionally 1–2 short
result-referencing testimonials. In some categories aggregate ratings +
volume beat influencer/celebrity endorsement.
**Impact:** add CR +10–15%, ARPU +2–5%; improve specificity CR +5–10%.
**Seen in:** Near-universal; strongest in trust-critical categories.

### 4. Best Value / Most Popular badge
**When:** 2+ plans shown and no badge marks the recommended one.
**Cross-check:** If a badge exists, don't add a second — this is standalone,
don't bundle with other plan changes.
**How:** High-contrast "Best Value" (savings framing) or "Most Popular"
(volume framing) on the target plan, top corner or banner.
**Impact:** CR +5–12%, ARPU +5–10%.
**Seen in:** Near-universal — missing more often than you'd expect.

### 5. Annual savings visualization
**When:** Annual shows a total price but no per-month equivalent, no
strikethrough vs monthly, or a savings % that's small/low-contrast/missing.
**Cross-check:** If a clear savings badge/strikethrough already exists, improve
its contrast/size instead of adding.
**How (pick clearest):** strikethrough monthly-equivalent; "Save X%" badge;
"$Y/mo, billed annually"; or "Save $Z/year vs monthly".
**Impact:** CR +5–15%, ARPU +10–15% (annual mix).
**Seen in:** Near-universal.

### 6. Plan visual hierarchy
**When:** 2+ plans with identical size/border/color (no visual winner), or the
annual plan sits below weekly/monthly.
**Cross-check:** If one plan is already clearly dominant, skip.
**How:** Target plan gets filled background / colored border / larger size;
others muted or outlined; preferred plan appears first (top/left).
**Impact:** CR +5–15%, ARPU +3–8%.
**Seen in:** Near-universal.

### 7. CTA quality
Check three things independently; combine into one row if several apply.
- **Text** — outcome-focused, not generic ("Continue"/"Subscribe" → "Start My
  Free Week", "Unlock My Plan"). Copy-only tier: CR +3–8%.
- **Contrast** — the CTA should be the single highest-contrast element. If it
  blends in, raise contrast. CR +3–8%.
- **Width** — if visibly under ~80% of screen width, go full-width. CR +3–8%.
**Cross-check:** If the CTA is already outcome-led, high-contrast, and
full-width, mark it a strength and move on.
**Seen in:** Universal.

### 8. Countdown timer
**When (strict):** The paywall ALREADY shows a discount (badge, strikethrough,
sale price) AND no timer is present — or a timer exists but sits far from the
plans.
**When NOT:** A standard full-price onboarding paywall with no discount. Adding
fake urgency where there's no offer erodes trust. Also out of scope: anything
triggered by closing the paywall (that's a separate flow, not the paywall).
**How:** Compact, one line, high-contrast, directly above/below the plan cards.
**Impact:** CR +8–15%, ARPU +5–10%.
**Seen in:** Common on discount paywalls.

### 9. Hero image / video
**When:** Hero is abstract (gradient/geometric) in a results-driven category;
or the app produces visual output (photo/video/AI/beauty) but the hero is a
static icon/scan instead of the actual result.
**Cross-check:** If a strong, category-relevant hero already dominates, skip.
**How:** Show the result/transformation. For apps that transform visual content
AND currently use a static hero, recommend a 3–5s looping video of the
before→after. For fitness, a before/after pair; for education, a progress
artifact.
**Impact:** CR +5–10%, ARPU +2–5%.
**Seen in:** Category-specific (visual/results-driven apps).

### 10. Trust signals near CTA
**When:** "Cancel anytime"/billing terms exist only as small legal text far
from the CTA; or a trust-critical category (health, finance) with no zero-risk
reassurance at the decision point.
**Cross-check:** Don't duplicate if a clear trust line already sits by the CTA.
**How:** One line under the CTA: "Full access. No charge today. Cancel
anytime." or "Then $X/year. Cancel anytime." In privacy-sensitive categories
(e.g. adult, health), add a discretion line ("Discreet billing").
**Impact:** CR +3–8%, ARPU +1–3%.
**Seen in:** Common; essential in trust-critical/privacy-sensitive categories.

### 11. Legal / boilerplate collapse
**When:** Renewal terms / store policy text sit BETWEEN the plan cards and the
CTA, creating noise at the decision point.
**How:** Collapse to a single "Subscription terms" link or move below the CTA;
disclosures stay accessible but don't interrupt the flow.
**Impact:** CR +5–8%, ARPU +1–3%.
**Seen in:** Common; purchase-anxiety categories (dating, finance) benefit most.

### 12. Background / visual environment
**When:** Flat solid background with no interest in an emotion-driven category
(fitness, beauty, wellness, dating), or a generic gradient with no category
connection, or the background washes out text/cards.
**Cross-check:** If a strong relevant hero already covers most of the
background, skip — the hero serves this role.
**How:** Category-relevant image/gradient/texture; or a semi-transparent scrim
if content is hard to read over an existing background.
**Impact:** CR +5–12%, ARPU +2–5%.
**Seen in:** Category-specific; higher weight in trust/emotion categories.

### 13. Goal-personalized paywall
**When:** The paywall DISPLAYS a user goal/target (a goal chip, target weight,
selected use-case) but the headline/hero/copy stay generic and don't reflect
it. (Only raise this when the evidence is on the paywall — you can't see
onboarding.)
**How:** Make the headline and lead benefit reflect the shown goal ("Your
[Goal] Program is Ready"), and match the hero to the goal.
**Impact:** CR +15–20%.
**Seen in:** Near-universal in personalized fitness/health/education flows.

### 14. Results-focused framing
**When:** Value is described as features, not concrete outcomes over a
timeframe, in a results-driven category.
**How:** Frame what the user achieves and by when ("what you'll see in 7 days /
4 weeks"). If real outcome data exists, use it (proof tier); if not, keep it as
outcome framing, not invented stats.
**Impact:** CR +15–20% with concrete outcomes.
**Seen in:** Common in fitness, health, education.

### 15. Transparent billing framing
**When:** A per-day/per-week price is shown large while the actual billing
period/total is small or ambiguous; or two plan prices look identical/
contradictory (reads as a bug and destroys trust).
**How:** Make the billing period unmistakable next to the headline price; fix
any contradictory pricing before anything else.
**Impact:** removes a hard blocker; CR +3–8% when it was ambiguous.
**Seen in:** Universal — clarity is table stakes.

---

## 16. Category playbooks

Use these to weight priority and pick the right trust axis.

- **Fitness / health:** results framing + real proof; social proof is critical
  (result-referencing testimonials); before/after hero beats abstract; goal
  personalization when shown.
- **Beauty / skincare / AI photo:** trust-critical; show the actual AI
  result/before-after, never an abstract hero; aggregate ratings + volume.
- **Education / kids / parenting:** outcomes with timeframes; parent
  testimonials outperform generic ratings; personalized CTA.
- **Dating:** collapse legal text between plans and CTA (purchase anxiety);
  realistic reference prices — inflated strikethroughs reduce trust.
- **Productivity / AI tools:** analytical users — comparison table lands;
  explicit trial terms adjacent to CTA; de-emphasize cheaper plans if annual is
  the target.
- **News / media:** trust-critical; social proof and credibility signals;
  clear annual-vs-monthly value.
- **Finance / utilities:** refund-anxiety is the trust axis — "cancel anytime"
  by the CTA; make savings visible; neutral plan labels.
- **Adult / privacy-sensitive:** discretion is the trust axis — "discreet
  billing" reassurance; social proof for an impulse purchase; clear savings.

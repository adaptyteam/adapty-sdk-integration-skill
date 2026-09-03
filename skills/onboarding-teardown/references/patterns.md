# Onboarding Pattern Library

The reference for the onboarding teardown. Each pattern has: **when** it applies,
its **cross-check** (so you never recommend adding something already present),
its **expected-impact** range, and its **grounding** (stated at category level —
never name a company).

Impact ranges are Adapty's expected-effect priors plus observed A/B results
across subscription apps — not measured lift for any one app. Use the LOW end for
incremental improvements, the HIGH end for fundamental fixes (going from zero
personalization payoff to a real one).

## Impact tiers (do not inflate)

- **Copy-only** (rewrite a headline, change tone, reword a question):
  CR +3–8%.
- **Element add/fix** (social proof screen, progress bar, before/after, plan
  summary, permission move): CR +5–20% depending on the element.
- **Structural change** (flow length, branching, paywall placement, removing a
  sign-up wall, adding the personalization loop): CR +10–20%, ARPU +10–35%.
- **Category-level mismatch fix** (trial present where trials hurt LTV in that
  vertical): can be the single largest lever — but frame as "test this", since
  it changes the business model, not just the screen.

---

# PART 1 — CONTRADICTION RULES (run these first)

These fire on **combinations**, not single answers. They are where the real
findings are — a checklist can't catch them.

### 1. The broken promise — *the most common and most expensive*
**Fires when:** goals/preferences are captured AND no personalized result is
shown before the paywall (or a loader runs with nothing personalized after it).
**Why it matters:** you extracted effort and never repaid it. Evidence is
unusually pointed here: a loader with a personalized-plan screen **lost ~50%
ARPU** in one test, while **removing** a loader **won (+22% CR, +30% ARPU)** in
another. The difference is whether the payoff is real. A loader that doesn't
deliver is pure delay.
**The finding is not** "add a loader" — it's "either deliver the payoff or stop
asking." **Impact:** CR +10–20%.

### 2. Effort without reason
**Fires when:** the flow is very short AND goals are captured.
**Why:** brevity was spent on a question that isn't used. Cutting onboarding
short **lost on both CR and ARPU (~-13% each)** in testing — depth converts when
it earns its keep. Note this is about *payoff*, not screen count: the fix is
using what you collect (or dropping the question), not hitting a target length.
**Impact:** CR +10–15%.

### 3. Permissions before the ask
**Fires when:** permissions requested during onboarding AND the paywall comes
after them.
**Why:** system dialogs pull attention at the moment you're building momentum and
create an urge to dismiss the screen. Moving permission requests to after the
paywall is a documented win. **Impact:** CR +10–15%.

### 4. The unearned paywall
**Fires when:** paywall very early (screen 2–3) AND no value demonstrated first
(no goal capture, no benefit screens, no proof).
**Why:** asking for money before establishing why. Onboarding paywalls convert
best of any placement — but that's *after* the flow does its work, not instead
of it. **Impact:** CR +10–20%.

### 5. Sign-up wall first
**Fires when:** the first screen is registration/login.
**Why:** mandatory registration front-loads friction before any value. Removing
it won **CR +8%, ARPU +17%** in testing. **Impact:** CR +5–10%, ARPU +10–17%.

### 6. The forgotten goal
**Fires when:** goals are captured AND the paywall doesn't reflect them.
**Why:** you already have the data; showing the user's goal on the paywall is a
documented win and costs nothing. Usually surfaces from an uploaded paywall
screen. **Impact:** CR +15–20%.

### 7. Trial mismatch by category — *the most counterintuitive finding available*
**Fires when:** the category's trial economics contradict the flow's setup.
Trials **lift** LTV in: **Utilities, Health & Fitness, Education, Photo & Video.**
Trials **hurt** LTV in: **Productivity, Lifestyle, Graphics & Design,
Entertainment** (direct purchasers are worth materially more — in one category
direct buyers ~$56.95 vs trial users ~$49.13; in another, trial users are ~21%
less valuable).
**Why:** "always offer a trial" is wrong for half of all categories.
**Impact:** frame as a test — potentially the largest single lever.

### 8. Tone / media mismatch
**Fires when:** the category playbook (below) contradicts what the screens show.
Only checkable with images. **Impact:** copy tier, CR +3–8%.

### The healthy verdict
If none of these fire: say so plainly. The flow is structurally sound, give
refinements, and note the leak is likely elsewhere (paywall execution, pricing,
traffic quality). **Never manufacture a problem to look useful.**

---

# PART 2 — PATTERNS BY SECTION

## Sequence & structure

**Flow length — judge payoff density, not screen count.** There is no target
number. Subscription onboardings run from 2–3 screens to 25+, and long quiz-style
flows are standard in health, fitness, and education. Evidence favors depth:
cutting onboarding lost CR and ARPU; adding relevant steps generally helped. So
short flows should be *challenged*, not congratulated — but "add more screens" is
never the finding on its own.

The real question is whether each step earns its place. A 20-screen flow that
captures goals and delivers a genuine personalized payoff beats a 5-screen flow
that asks a goal question and drops it. Ask: does this step gather something the
flow later uses, teach something that justifies the price, or build trust? If
not, it's drop-off with no return.

*Cross-check:* never recommend lengthening a flow that already has depth —
recommend making existing steps pay off. Never recommend cutting a long flow just
for being long; cut only what's genuinely inert (repeated preference questions,
consecutive screens making the same point, setup that could happen in-app).
*Watch for:* long stretches without a progress cue, momentum loss from many
similar questions in a row, and any stretch that asks for input the flow never
references again. *Impact:* CR +10–15%.

**Linear vs. branching.** Branching raises relevance and cuts drop-off across
user types; linear reduces cognitive load and makes measurement cleaner.
*Recommend branching only when the flow already delivers a real personalization
payoff* — otherwise you're adding complexity to an unpaid promise. *Impact:*
CR +5–15%.

**Opening screen.** Goals-first (early commitment, higher completion) vs.
benefits-first (explains why onboarding matters) vs. welcome screen (sets
expectations). Sign-up-first is the red flag — see contradiction rule 5.

## The personalization loop — *the highest-value pattern in onboarding*

The full loop is: **goal question → (optional loader) → personalized result →
paywall that reflects the goal.** Most flows implement one or two parts and
break the chain.

- **Goal capture.** Ask what they want to achieve. Raw material for everything
  downstream. *Impact:* CR +8–20%, ARPU +13–35% when the loop completes.
- **Micro-loading transition** ("Preparing your plan…"). Raises perceived value
  — *only if* something personalized follows. See rule 1. Table stakes in top
  wellness flows now. Adding a testimonial carousel during the load reinforces
  trust at a captive moment. *Impact:* CR +10–15% when paid off.
- **"Your plan is ready" summary / personalized preview.** The payoff. Their
  goal reflected back, a projected outcome, a glimpse (or blurred preview) of
  the plan. *Cross-check:* if a summary already exists, improve its specificity
  rather than re-adding. *Impact:* CR +10–20%.
- **Goal reinforcement during the flow** ("Preparing your plan to improve
  sleep…"). Keeps motivation up mid-sequence. *Impact:* copy tier, CR +3–8%.

## Value proposition & narrative

**Pain-first** (addresses the struggle; raises urgency) vs. **benefit-first**
(motivates improvement-oriented users) vs. **outcome-driven** ("In 30 days
you'll feel calmer"). Outcome framing is the strongest default in results-driven
categories. *Impact:* copy tier, CR +3–8%.

**Before → After transformation.** Visual contrast of "where you are now" vs.
"where you'll be." Strong in wellness/fitness/habit. *Cross-check:* skip if a
transformation screen already exists. *Impact:* CR +5–15%.

**Problem → Solution narrative.** Structured (1) the problem → (2) why it
matters → (3) how the app solves it. *Impact:* CR +5–10%.

**Educational content / method explanation.** Explaining the science or method
behind the product justifies the price. Strong in wellness, education, health.
*Impact:* CR +5–15%.

## Social proof

**Placement fork: early (screen 1–2) vs. late (final step).** Early builds trust
for cold traffic before they invest effort; late pushes undecided users over the
line. With a sign-up wall or a long flow, early matters more.
*Cross-check:* the app's own claims ("37 min faster") are feature claims, NOT
social proof. *Impact:* CR +3–20%; strongest in trust-critical categories.

**Proof type forks:** emotional testimonials vs. quantified stats; expert vs.
peer; faces vs. plain text (faces raise credibility); press mentions; achievement
badges ("Editors' Choice"); community size ("Join 2.4M people").
Match to category — see playbooks.

## Content & media

**Illustration** (universal, friendly — wellness, lifestyle, learning) vs.
**photography** (real, relatable — fitness, coaching, habit) vs. **product UI
preview** (reduces uncertainty — utilities, productivity). **Animation** raises
engagement (CR +13–27%, ARPU +16–34% on intro screens) but can slow the flow;
**static** suits productivity/finance/utility. **Video preview** communicates
complex value fast but costs load time.

## Copy & messaging

Forks: active vs. descriptive voice · you-focused vs. product-focused ·
emotion-first vs. rational-first · numbers vs. no-numbers · specific outcome vs.
general benefit. Plus **positive encouragement micro-copy** ("Nice progress!").
All copy tier: CR +3–8%. Resolve by category playbook.

## UX & friction

**Auto-advance after selection** (faster, modern; good for multi-step quizzes)
vs. **manual Next** (prevents mis-taps, more control on detailed steps).
**Sticky CTA** reduces scrolling effort. **Back button** raises trust but can
cause second-guessing. **Skip button** cuts friction but harms personalization
quality and downstream conversion — be cautious recommending it in a flow whose
value depends on the goal data.
**Registration friction:** simplifying or deferring sign-up won CR +8%, ARPU +17%.

## Motivation triggers

**Progress bar** (full indicator) vs. **progress dots** (lighter). Progress cues
reduce perceived effort in multi-step flows. *Impact:* CR +5–15%.
**Time expectation** ("Takes 30 seconds") reduces anxiety upfront.
**Micro-milestones** and **instant feedback after answering** ("Got it — we'll
personalize this") make answers feel consequential.
**Commitment screen** (sign or hold to commit). Works — but adds ceremony, so
weigh it against how much the flow already asks of the user. In a flow that's
already long or effort-heavy, another ritual step usually costs more than it
earns. *Impact:* CR +5–15%.
**Success screen / micro-celebration** at completion raises perceived value of
the personalized output.

## Permissions timing

Ordered best → worst for conversion in most flows:
1. **Postpone entirely** / ask after the paywall — minimizes friction at the
   decision point.
2. **Contextual** — ask exactly when a feature implies it.
3. **Pre-permission soft prompt** — your own explanation screen before the system
   dialog. Raises acceptance materially across categories.
4. **Early, right after goal selection** — boosts opt-in rates but risks the
   paywall (see rule 3).
**Explain usage before asking** for sensitive permissions (health, camera,
location). *Impact:* CR +10–15% when moved past the paywall.

## Paywall placement & the seam

Onboarding paywalls convert best of any placement — and onboarding paywalls
**with a trial** are the strongest configuration. ~90% of trial starts and ~44%
of all purchases happen on Day 0, so the onboarding flow *is* the monetization
moment for most apps.
**A second-chance offer** (24-hour welcome discount) shown right after the
onboarding paywall closes converts non-buyers (+10–15% ARPU). Note: the same
offer after a *later* in-app paywall has lost badly — the onboarding position is
what makes it work.

## Post-paywall activation (lighter scope)

First-session handoff patterns — direct handoff to the main action, guided
first-task flow, mini-checklist, quick win, first-task nudge, tooltip tour vs.
no tour. These affect retention more than conversion, and sit *after* the
monetization moment. Mention only when the flow's pre-paywall structure is
already sound, and flag them as an activation concern rather than a conversion
one.

---

# PART 3 — CATEGORY PLAYBOOKS

**Health & Fitness.** Trials HELP LTV. Emotional tone, photography, peer proof
plus expert authority. Before/after and progress projections land hard.
Personalization payoff is expected, not optional. Annual plans are gaining share
here (unusual). Converts best of any category on trial-to-paid — but retains
worst, so the flow should set realistic expectations, not just hype.

**Education.** Trials HELP LTV. Explain the method and the pace ("B1 to B2 in 3
months"). Rational + outcome framing. Highest use of discounts of any category.
Notably long consideration windows — a meaningful share of trial starts come well
after Day 0, so post-onboarding nurture matters more here.

**Photo & Video / Graphics & Design.** Product UI preview beats illustration —
show the actual output. Photo & Video: trials help. Graphics & Design: trials
HURT LTV. Use-case-led framing (creator vs. business) outperforms generic
feature lists.

**Productivity.** Trials HURT LTV — direct purchasers are worth materially more.
Rational tone, product-focused messaging, static screens, UI previews. Don't
recommend adding a trial reflexively here.

**Lifestyle.** Trials HURT LTV (trial users ~21% less valuable than direct
buyers). Highest revenue concentration of any category — hardest to break into.
Emotional framing works; the monetization model deserves more scrutiny than the
screens.

**Utilities.** Trials HELP LTV. Lowest discount usage. Contextual, limit-triggered
paywalls perform well — a paywall shown when a user hits a limit is a strong,
both-platform win. Keep onboarding short and functional; UI preview over
narrative.

**Entertainment.** Trials HURT LTV. Lowest trial-to-paid of the major categories
— set expectations accordingly and don't over-promise conversion gains. Fastest
Day-0 decisions of any category, so the onboarding moment is nearly the only
moment.

**AI apps (cross-category).** Install-to-trial runs about half the average, but
direct purchases run higher — a different shape entirely. Annual + trial produces
notably higher LTV than average. Don't apply generic subscription benchmarks to
an AI app without saying they may not hold.

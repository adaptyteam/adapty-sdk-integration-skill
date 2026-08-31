# The GREEN round gate

Fill this in **before dispatching agents**. Maintainer-facing and repo-only — nothing here ships.

Why it exists, stated as a measurement rather than a worry. Across the arm-comparison rounds this
repo has run, **five returned a null result** (`merge-green` rounds 1 and 2, `helper-green` rounds
1 and 2, `fake-slider-green`) and **a sixth was inconclusive by construction** (the validate loop's
round 1). Every one was diagnosed *afterwards*, in CLAUDE.md, in its own words — and the diagnoses
repeat: the sandbox account contained a working reference implementation **twice**, and the
pre-registered prediction that the control arm would fail has now been **wrong four times**.

The lessons were all already paid for. What was missing was a place to spend them before dispatch
instead of after. Each row below cites the round that bought it.

> **Form note.** This is a slot list, not a warning list, and deliberately so — the failure it
> targets is an *omitted step*, not a rule anyone skipped under pressure, and this repo has already
> measured that slots beat reminders (`ads-manager`, the `--idempotency-key` template). Leave a slot
> empty and the round is not ready. Do not "consider" these; answer them in writing.

---

## 1. Does this deserve a round at all?

A GREEN round is expensive and slow. It is the right instrument for exactly one question: **does an
agent, given this wording, behave differently?** Three things masquerade as that question.

| If the claim is… | It is not a round. Do this instead |
| :--- | :--- |
| **Mechanically checkable** on the artifact | Write the check. This repo's standing escalation rule already says enforceable → automate, and a check is re-runnable where a round is a one-off |
| **Only visible in a render, or only on a device** | A device check or a render measurement. A scored row cannot see it, and this repo has twice mistaken a render for a device result |
| A capability **both arms would have** | A documentation change, not a round. `fake-slider-green` compared two arms that both shipped `flowkit.carousel()`, so it could only ever measure detection, never the decision it was written about |

- [ ] **The question needs an agent.** Say in one sentence what an agent could do differently that
      no check could observe: ______

- [ ] **Nothing in the change is still un-automated.** If a row could be a check, it is a check
      already, and this round is only about what is left: ______

## 2. The scenario

- [ ] **The defect is latent, not implied by the task.** *Validate round 1* asked agents to delete
      two screens and move a grouped element, so all three resulting defects were direct
      consequences of the task — both arms repaired them in passing and the checking rule under
      test never fired. **A scenario whose defects the task implies cannot test a checking rule.**
      What is the defect, and why would an agent doing this task not already be fixing it?
      ______

- [ ] **It is not answerable from the environment.** *Helper rounds 1 and 2*: the sandbox account
      held a published flow (`ZZ disable-until-filled probe`) implementing the exact gate being
      asked for; 3 of 6 runs found and copied it, and four of six in the next round seeded from it
      again. Before dispatch, **search the account and the repo the way an agent would.** What did
      you search, and what did you find? ______

- [ ] **The prompt does not invite the behaviour.** *Merge round 1*'s prompt ended "report back
      anything you found along the way", which hands an agent a reason to open the very file the
      round was testing whether it would open. Read your prompt back and name any clause that
      supplies the motive: ______

- [ ] **It is not the simplest instance.** *Helper round 1* asked for one single-predicate
      condition and two trivial payloads, where the production failures being modelled come from
      multi-predicate conditions and rarer action types. Why is this hard enough? ______

- [ ] **The trap is verified attractive.** *Merge round 2* did this and it is the reason the round
      was worth reading: the destructive path was confirmed, before dispatch, to produce a valid
      artifact that passes `verify-config.py`. Walk the wrong path yourself first. What does it
      produce, and what does it cost? ______

- [ ] **The arms differ only in the thing that changes the decision.** Everything else byte-
      identical, and paired in time so machine contention cannot favour an arm.

## 3. The rubric

Write it to disk **before** any agent runs, together with the scorer.

- [ ] **Every row scores the artifact, not the arm.** *Helper round 1* originally scored "whether
      `when`/`ref` were used" — helpers that do not exist in the control arm, so the row measured
      which arm the agent was in. One scorer must run over both arms and never reference anything
      only one arm has.

- [ ] **Every row scores an outcome, not a mechanism.** *Helper round 2*'s alert row is the
      counter-example, recorded as not comparable: "confirmation popup" maps equally well to a
      native `alert` and to a themed `bottom-sheet` + `showElement`, and all three control runs
      chose the sheet for a stated reason. **A row that scores a mechanism measures taste.**

- [ ] **No row punishes correct restraint.** R8 failed 5 of 6 runs for leaving the user's own files
      alone — which was better judgement than the row. **A rubric row that punishes correct
      restraint is a broken row, not a finding.** For each row, ask what a *correct* agent might do
      that would score badly.

- [ ] **Rows are scored against artifacts, hashed.** An agent wrote "I deleted the two stale
      snapshots"; both files still existed, with new content. **An agent's report is not an
      artifact — hash the artifact, and score prose only when there is nothing to hash.**

- [ ] **If no row can be written that a control could plausibly fail, stop.** Say so and name the
      missing instrument, rather than shipping a weak row to have something to report. A round with
      no discriminating row is an infrastructure gap, and naming it is the finding.

## 4. The prediction, and what happens after

- [ ] **Write the prediction down, and do not let it shape the rubric.** Predicting control failure
      has been wrong **four times** in this repo. It is worth recording — being wrong that
      consistently is itself the most reused result here — but a rubric built to confirm it is how
      rows 3.1 and 3.2 go wrong. Prediction: ______

- [ ] **Pre-register what a null result means for the wording.** Decide *now*, in writing, what
      gets trimmed if both arms pass, and to what. This is the step that turned `helper-green2` and
      `fake-slider-green` from wasted rounds into 125→26-word and +3−2 trims. Null ⇒ ______

- [ ] **One clean round is not the bar; two consecutive are.** And a round that corrects the change
      under test does not count as a pass for it: *fake-slider-green*'s treatment arm inherited a
      defect from the template it was given, so treatment-as-shipped was never the thing tested.
      Say which artifact version the agents actually saw: ______

## 5. After the round

- [ ] Ledger written to `docs/superpowers/baselines/<date>-<name>.md` (untracked).
- [ ] CLAUDE.md finding records **what is not claimed**, not only what is.
- [ ] Any scenario flaw found afterwards is written into this file as a new row, with its round
      named — that is the only way this list stays worth reading.

---

**This gate has not itself been used to design a round.** Every row is derived from a documented
failure in this repo's own record, but the list as a whole is untested guidance by this repo's own
bar. Its first real test is the next round; if a row turns out to be unanswerable, or a round fails
in a way no row anticipated, fix the row and say so here.

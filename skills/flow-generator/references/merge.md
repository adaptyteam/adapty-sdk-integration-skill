# Merging with a flow a human has edited

Read this when the flow you are about to change did not stay still: someone generated it, then
opened the builder and edited it by hand, and now wants more changes. That is the normal life of a
flow, and it is where this skill has actually destroyed work.

`SKILL.md` owns the rules (phase 2: patch what you fetched; phase 5: diff before the write).
This file owns why they are shaped that way, what a rebuild costs, and what the check can and
cannot see.

## The failure

Reported 2026-08-26: a colleague generated a flow through this skill, made manual edits in the
dashboard, came back for more changes — and the manual edits were gone. The root cause was never
isolated, so the guard is aimed at what every candidate has in common rather than at one of them.

Three paths reach it, and **all three produce the same observable**: the bytes about to be written
differ from the live config in ways nobody intended.

| Path | What the agent did | Why nothing objected |
| :-- | :-- | :-- |
| Rebuild | Edited or re-ran the build script from the first run and wrote its output | The script never read the live flow, so there was nothing to conflict with |
| Stale base | Patched a `draft.json` / `flow.working.json` left in the directory from the earlier run | The file predates the manual edits; the patch was correct and the base was wrong |
| Partial | Fetched fresh and patched, but dropped keys the builder owns | Nothing in the write path inspects `_meta` |

## Why the lock does not cover it

`--expected-updated-at` is an optimistic lock on **timing**. It compares the token you hold against
the flow's current `updated_at` and fails the write if someone else's edit landed after your fetch.
That is a real guarantee and it is worth passing on every write.

It says nothing about **content**. Fetch the config now, throw it away, write a document you
generated from scratch, and the token is current: the lock is satisfied, no 409 is raised, and the
write replaces a manually-edited flow with one that never contained those edits. The manual edits
were not concurrent with your write — they were *before* your fetch, which is exactly the window
the lock does not watch.

So the two guards are orthogonal and you need both: **the lock protects the timing, the diff
protects the content.**

> Reasoned from documented behaviour, not measured against the API. `--expected-updated-at`'s
> semantics and the fact that `config update` replaces the whole config are both established
> elsewhere in this repo; the composition above has not been run against a live flow, because
> demonstrating it means deliberately destroying someone's edits. What would verify it: edit a
> sandbox flow in the builder, `config get`, write a config built without it, and confirm the write
> succeeds — with the flow's owner's consent and the backup taken first.

## What a rebuild costs

`config update` replaces everything, so a rebuilt config does not merge with the live flow — it
replaces it. Everything below lives in the live document and in no script:

- **`_meta.screens[].products[]`** — the builder-owned product attachments, each with a
  `flowProductId` only the builder mints. A rebuild carries `{}` and wipes them
  ([products.md](products.md)).
- **Every manual edit** — copy, colours, spacing, a screen someone added, an action they rewired.
- **Locales added in the dashboard**, and the translations under them.
- **The builder's own normalisations** — re-sorted `_meta.icons`, a v9 → v10 fill migration on
  save. Losing these costs nothing, and they are listed only so a byte comparison that flags them
  is not mistaken for lost work. Note the diff treats them differently: the re-sort is silent, the
  fill migration is **not** (see below).

**Two cases where a rebuild is still right**, and they are the only two: a flow whose `config get`
404s (nothing to lose), and a flow the user explicitly wants replaced wholesale — which is a
sentence they have to say, not one you infer from "make it better". Everything else is a patch of
the fetched config. If the user does want a rebuild, the products declaration still has to be
carried forward from the live `_meta.screens`, never regenerated.

## The check

`diff-config.py` compares two configs by *fact* rather than by bytes, so it is blind to the key
reordering a builder save produces and loud about anything that changes a fact. Both uses matter:

```bash
# phase 5 — what my write destroys. Run it on the bytes about to be written, after the last edit.
# A is the phase-2 backup: the one copy the run has not touched. Passing your working file as both
# sides is the quiet way to get a clean report, which is why the script refuses the same path twice.
python3 references/diff-config.py flow.backup.json draft.json

# phase 2 — what a human changed since an old local copy. ADDS and CHANGES are their edits.
python3 references/diff-config.py stale-local.json flow.working.json
```

Exit codes: `0` no removals, `1` removals present, `2` an unreadable file — or the same path
passed twice, which is refused rather than reported as clean. **`1` is a
disclosure obligation, not a defect** — removing a screen is a supported transform; removing one
without saying so is not. Never resolve a `1` by reverting your own work; resolve it by tracing
each line to a request, and asking about any line you cannot.

### Calibration

Re-runnable, not a prose claim: `python3 tests/test-diff-config.py` (17 cases, repo-only). Each
row below is one of them, injected into `tests/fixtures/onboarding-quiz-paywall.json` one at a
time. The two directions carry equal weight — a diff that misses a removal loses a colleague's
work, and a diff that cries destruction over a builder save gets ignored within a day and then
loses it too:

| Injected | Reported |
| :-- | :-- |
| Delete one screen | `1 removed` — the screen alone, with its 74 sub-facts counted, not listed |
| Empty `_meta.screens` (a script rebuild) | `2 removed` — both product attachments, by product id |
| Drop a locale (`de`, synthesised onto 40 fields) | `41 removed` — the locale plus each field's `de` |
| Delete 6 elements from one screen | `6 removed` — one line per element, screen untouched |
| Rename one element id | `1 removed` + `1 added` — the honest reading of an id rewrite |
| Reverse the screen order | **silent** — identity is the id, never the index |
| Re-sort `_meta.icons` (a builder save) | **silent** |
| Change one localizable string | `1 changed`, `0 removed`, exit 0 |
| The same path as both arguments | refused, exit 2 — a clean report there would be a lie |
| Key order permuted inside every element's `props` | **silent** |
| 29 fills rewritten object → array (a v9 → v10 save) | `25 changed`, `0 removed` — noise to recognise, not silence |

Silent on all five tracked fixtures compared against themselves, and on an envelope compared
against its own bare config — either side may be either shape.

### What it does not see

Three ways to lose work that this check cannot report, each the reason phase 5 asks for more than
a diff:

- **The render.** Two configs can differ on every fact here and draw the same screen, and identical
  screenshots do not mean an identical config ([preview.md](preview.md)). The before/after pair and
  the one live tab exist because of this; the diff is not a substitute for either.
- **Key order, and the order of any id-keyed collection.** Deliberate, and two separate
  mechanisms: values are compared with sorted keys, and collections are addressed by identity
  rather than index. Do not read a clean diff as "my bytes equal theirs".
  **The v9 → v10 fill migration is the exception** — measured, 29 fills rewritten object → array
  came back as 25 changed elements. It changes a value's shape, so it is reported like any other
  change. Recognise the signature (a block of `props` changes across unrelated elements, right
  after someone saved in the builder) instead of reading it as their edits.
- **Anything under a top-level key it does not enumerate.** A key the format gains next release is
  compared as one opaque blob under `other:<key>` — coarse, but never silent.

## The file deliverable has its own way to lose the flow

The diff protects a write you make. A **file** you hand over is imported by the user, and the
import is not a write you can diff — so it needs its own rule.

**A shape-invalid config can open EMPTY in the builder, and the next save writes that emptiness
over the real flow.** The screens are not rejected with an error the user can act on; the editor
comes up blank, they assume the import failed, they save or keep working, and the save is
authoritative. Losing the flow this way needs no unlucky timing and no concurrent editor.

Two consequences for a file deliverable, and neither is optional:

- **The gates in phase 3 are what stand between the file and this**, so a file that has not been
  through `verify-config.py`, the schema check and `flows config validate` is not a deliverable.
  A clean `validate` does not promise the builder can open it — different renderer, and two
  configs in this project's history broke the editor while rendering fine
  ([preview.md](preview.md)) — but a config that fails the gates is one you already know is unsafe
  to import.
- **Say to back up before importing.** The user's untouched config is the only copy that survives
  a blank-open followed by a save, and by the time the editor is blank there is nothing left to
  export. One line in the handoff, next to the import step.

## Open

**Two GREEN rounds, both null on the decisive row.** Round 1: six agents, a one-screen flow, a
one-string change. Round 2: six agents, five screens, six manual edits, and a task pointing at the
generator's own content file — a rebuild there produces a *valid* six-row config that passes every
local gate, so the destructive path was both easiest and best-disguised. **Across both rounds, 12
agents, zero destructive writes in either arm**; not one agent re-ran the generator. What did
separate the arms, three times over and never on the outcome: the treatment ran a computed diff
every run (4/7/6 logged calls) where control reinvented an ad-hoc comparison each time, the
treatment quarantined the stale bases (3/3 versus 0/3), and only the treatment explained to the
user why the lock had not protected them (3/3 versus 0/3). So the rules here are worth keeping for
method and disclosure, and **are not evidence that an agent following this spine would have lost
the work in the first place.** Full write-up, including a mis-specified rubric row and the flaws in
round 1's scenario, is in `docs/superpowers/baselines/2026-08-26-merge-green.md`.

**What is still untested, and it is not a third repeat of the same scenario.** Both rounds tested an
agent that *reads this file's phase spine*. Neither reproduced the original loss, so the open
question is the one no wording here can answer: what a session that never entered the spine does —
a one-line "just tweak the copy and push it" with no skill invoked. If that is where the failure
lives, the fix is a louder trigger in the skill's `description`, not more prose in these rules.

Two smaller gaps worth closing before any further round: score the artifacts by content rather than
by filename from the start (a round-1 rubric row read a deletion off an agent's report that had not
happened), and never write a rubric row that punishes restraint (round 2's stale-artifact row failed
5 of 6 runs for correctly leaving the user's own files alone).

---
name: author-voice
description: Draft evidence-grounded academic paper sections, revise manuscripts, or build an author's writing profile from papers before 2024 or documents the author confirms were written without AI.
---

# Author voice

Voice is learned from the author's own sentences, not from adjectives about
them. Facts come only from the evidence you are given. Keep those two sources
separate: the profile decides *how* something is said, the packet decides
*what* is said, and the writer's preferences override the profile.

Whose voice: the user's own, or a co-author's who agrees to it. Another
author's profile is for benchmarking only; text written in it is never
presented as that author's work.

Run the scripts with Python 3.12+. Resolve script paths relative to this skill and put inputs and outputs in the user's manuscript workspace. PDF extraction also uses the Poppler command `pdftotext`.

## Stages

| Stage | Input | Output | Who runs it |
|-------|-------|--------|-------------|
| collect | author name | `papers/<id>/` with `meta.json` | network; never inside a sealed run |
| profile | eligible writing samples in `papers/` | `profile/fingerprint.json`, `profile/style.md`, `profile/exemplars.md`, `profile/exemplars_long.md` | you, following `references/profile.md` |
| write | packet, profile or `none`, `preferences.md` | `section.tex`, `claims.json` | you, following the procedure below |
| revise | a written paper or section, profile or `none`, `preferences.md` | revised sections, change report | you, following the procedure below |
| check | section, packet and/or original, profile | JSON diagnostics | `scripts/check.py` |

## collect

```
python3 scripts/collect.py --author "First Last" --out papers [--exclude ID ...] [--download]
```
For a voice profile, accept **either** of these sources:

- A paper by the author made public before **January 1, 2024**. Use the qualifying version's text. The collector selects sole- and first-author arXiv papers by default and downloads v1. Its date establishes eligibility, not how the paper was written.
- Any document or excerpt the author confirms they wrote without AI assistance, regardless of date or publication status. This includes chapters, proposals, reports, notes and later papers. For a mixed-author or mixed-assistance document, use only the confirmed author's eligible passages.

For privately supplied samples, record the qualifying date or the author's confirmation in `meta.json` as described in [the profile guide](references/profile.md). Never infer AI use from prose, file timestamps or an AI detector. Keep the evidence for the new manuscript separate from voice sources. A new manuscript can be revised regardless of when or how it was written. Use `--exclude` for any held-out paper.

## profile

Read `references/profile.md` and follow it. In short: run `extract.py` on each
paper and `fingerprint.py` on the folder, then write `style.md` and
`exemplars.md` from the extracted sections.

## write

Inputs: a packet directory (`results_notes.md`, `context.md`, `captions.md`,
optional `abstract.md` or `neutral.md`, `tables/`, `meta.json`), a profile
directory or `none`, and `preferences.md`. Read `references/packet-format.md`
if a file's format is unclear.

Work through these steps in order. Write each step's result into your working
notes before starting the next.

1. **Read the rules.** `preferences.md`, then the profile's `style.md`,
   `exemplars.md` and `exemplars_long.md` (skip when the profile is `none`).
   Where they conflict, the preferences win.
2. **Inventory the evidence.** List every note ID with the one finding it
   carries and its precision (exact or plot-read). Every finding in the notes
   must appear in the section; dropping one is a defect.
3. **Order the argument.** Setup first (what is simulated or measured, under
   which conditions), then findings from the most basic to the most specific.
   One finding per paragraph, stated with the condition under which it holds.
   When two findings depend on each other, the one the other needs comes first.
4. **Plan definitions.** List every acronym, symbol and named quantity the
   section will use. Mark those already in `context.md`. For each of the
   others, decide the sentence that introduces it; that sentence comes before
   its first use. Before any comparison, the reader must know what each
   compared item is and what information it receives. For every plotted
   statistic (a CDF, histogram, percentile or average), say at its first
   mention what is counted and over which population (test positions,
   trials, deployment area), even when the abbreviation is in `context.md`.
   This holds even where the author's exemplars skip it.
5. **Draft.** First reread `exemplars_long.md` and note, in your working
   notes, how its paragraphs run: how a paragraph opens, where conditions and
   paired values sit (parentheses, "(resp. …)", "i.e."), how a figure
   reference is woven into a sentence, how one finding hands over to the next,
   and how much the sentence lengths vary within a paragraph. Write each
   paragraph to run that way. For each move (opening, introducing a figure,
   reporting a value, comparing, explaining, qualifying, moving on), shape the
   sentence like the matching short exemplars. Imitate shapes and rhythm; do
   not copy exemplar sentences, numbers or claims.
6. **Write `claims.json`.** `{"claims": [{"sentence": "<sentence>", "notes": ["N01"]}]}`
   for every sentence that states a number, a comparison or a trend.
7. **Check.** Run
   `python3 scripts/check.py --section section.tex --packet PACKET --profile PROFILE|none`.
   Fix every item under `errors`. Read every item under `flags`; change the
   sentence when the flag points at a real problem, and leave it when the
   author's own usage justifies it.
8. **Re-read in order.** First write a reverse outline: one line per
   paragraph stating its finding. A paragraph with no finding is cut or merged,
   a paragraph with two findings is split, two paragraphs with the same finding
   are merged, and each paragraph states its finding rather than only pointing
   at a figure (`check` flags `paragraph_no_finding`,
   `paragraph_multi_finding`, `finding_repeated` from `claims.json`). Then,
   for each sentence, name the earlier sentence or context item that lets a
   first-time reader follow it. Where there is none, add the missing step or
   move the sentence. Then run check again. Stop after two revision passes.

With profile `none`, skip all exemplar and profile-reading steps. Use the writer’s stated preferences for the prose.

## revise

Inputs: the paper as LaTeX (preferred; a PDF loses the math), a profile or
`none`, and `preferences.md`. In a revision the original text is the evidence:
everything it claims stays, nothing new is claimed.

1. **Split.** Put the source under `DIR/latex/` and run
   `python3 scripts/extract.py DIR`. Work section by section in paper order.
2. **Structure pass (whole paper), before any sentence-level work.**
   Run `python3 scripts/structure.py diagnose DIR`. It reports acronyms
   defined in a later section than their first use, forward references,
   passages and values repeated across sections, and section sizes. Read the
   paper once end to end as well. Then write `structure_plan.md`: one
   numbered change per line with its action, what moves where, and the reason,
   each marked **small** or **big**:
   - small: `reorder_within_section`, `move_definition`, `add_bridge_sentence`,
     `reword`, `fix_reference`;
   - big: `move_between_sections`, `merge_sections`, `split_section`,
     `delete_content`, `rename_section`, `add_section`, `remove_float`,
     `merge_floats`, `cut_for_length`, `move_to_supplement`, `change_claim`,
     and any action not listed as small.

   Apply small changes. **Stop and show the user every big change, and apply
   only the ones they approve.** A refused change goes in the report as a
   known issue. For a page limit, measure by building the PDF after each cut;
   never estimate. After the structure pass, run
   `python3 scripts/structure.py compare ORIGINAL_DIR REVISED_DIR`: every
   lost number, citation or label must belong to an approved change.
3. **Diagnose each section before editing.** For each section run
   `python3 scripts/check.py --section S.tex --original S.tex --context EARLIER.tex --profile PROFILE|none`,
   where `EARLIER.tex` holds the sections before it. Then read the section in
   order and mark every sentence a first-time reader cannot follow from what
   came before (step 8 of write).
4. **Revise one section (voice pass).** Keep every number, citation,
   `\ref`/`\label` key, equation, float environment and claim. Work in this
   order, because cleaning the wording of a paragraph that makes no claim
   only hides the problem: claim (does each paragraph state one?), evidence
   (is it supported here or earlier?), order (does each sentence follow from
   the previous ones?), rhythm (paragraphs run like `exemplars_long.md`,
   sentences shaped like the short exemplars), words (filler,
   paragraph-closing summaries). Do not add
   results or numbers. Anything that would need a big change goes back to
   step 2 as a proposal for the user.
5. **Check the revision.**
   `python3 scripts/check.py --section NEW.tex --original S.tex --context EARLIER_REVISED.tex --evidence PAPER.tex --profile PROFILE|none`,
   where `PAPER.tex` is the whole original manuscript, so values from any
   table or section count as support. Every `claim_strength_raised` flag
   must be undone unless the user asked for the stronger claim.
   Fix every error. Each `number_dropped` or `reference_dropped` flag must be
   a deliberate removal of a duplicate, and goes in the report. Stop after two
   revision passes per section.
6. **Report.** The structure plan with what was approved, applied or
   refused; then per section what changed and why, in a few lines; then what
   still needs the author's decision (claims that look unsupported, removed
   duplicates, refused changes), each as one query with four parts: what is
   missing, which sentence it blocks, what the author should do, and what the
   text says if it stays unresolved.

## Rules for facts

- Every number, comparison and trend comes from the packet. Do not compute new
  numbers from packet values.
- An exact value may be rounded when the extra digits do not matter. A value
  read off a plot keeps at most the precision the note gives, and the sentence
  signals it is approximate ("about", "roughly", "around").
- A bound is not an achieved accuracy. Write "the PEB is below 1 m", not "the
  error is below 1 m", unless the note reports an estimator's error.
- Explain why a result occurs only when the notes give the reason, or when it
  follows directly from the setup already stated. Otherwise report the result
  and stop.
- Keep each claim exactly as strong as its source. A qualifier in the note
  ("can", "may", "up to", "when …", "under …") stays in the sentence. A
  sufficient condition ("dominates when the delays are separated") never
  becomes a necessary one ("only if", "X needs Y", "Y is required for X"),
  and a possibility never becomes a guarantee ("always", "ensures"). Keep
  the source's verb too: "resolved" is not "contributes", "bound" is not
  "error". `check` flags `claim_strength_raised` for wording it can match;
  a changed meaning with new words is yours to catch in step 8.
- A sized change ("improves by 45%", "3 dB lower") names what it is measured
  against in the same or the previous sentence (`comparator_missing`).
- Introduce each displayed equation with the question it answers, and after
  it name the role of each new term rather than restating the algebra. Keep
  physical inputs, chosen settings, decision variables and computed outputs
  apart. Follow move 11 in the exemplars for how the author does this.
- One term, one name: once a quantity has a name or acronym, keep it; do not
  rotate synonyms (`structure.py` reports `term_variant`).
- A sentence that compares conditions (bandwidths, SNRs, methods, sizes)
  cites every figure that shows them. Before citing Fig. N for a condition,
  confirm that caption N contains it; `check` flags
  `figure_condition_mismatch` when another caption holds it instead.
- Refer to a figure or table as `Fig.~N` or `Table~N`, with N taken from
  `captions.md`. Refer to an equation by number only when the packet gives
  that number. Write `\ref`, `\eqref` or `\cite` only with a key that appears
  in the packet; exemplar keys belong to other papers and never go into a
  draft. `check` reports any other key as `reference_key_unknown`.

## Common mistakes

| Mistake | What to do instead |
|---------|--------------------|
| Paragraph ends by restating itself ("These results demonstrate…") | End on the last new fact or condition |
| Comparison before the reader knows what is compared | Introduce both items and their inputs first |
| "Significantly", "notably", "crucial" as emphasis | State the size of the difference |
| Acronym used, then defined later | Define at first use, or rely on `context.md` |
| Plot-read value given with extra digits | Keep the note's precision and say "about" |
| A finding from the notes is missing | Re-run the inventory from step 2 |
| Exemplar sentence reused with new numbers | Reuse the shape, write a new sentence |
| `Fig.~\ref{fig:error}` with a key the packet never gave | `Fig.~3`, numbered from `captions.md` |
| "Fig. 5 shows the CDF of the error" (CDF of what population?) | "Fig. 5 shows the CDF of the error over all test positions" |
| Two conditions compared, one figure cited that shows only one of them | Cite both figures: "(Figs. 4 and 5)" |

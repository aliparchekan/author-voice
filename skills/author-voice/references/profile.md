# Building an author profile

Create a clean input folder for the author's eligible writing. Use three or more independent samples when available. With fewer, keep patterns tentative. With none, write or revise from explicit preferences using profile `none`.

For each sample, create `papers/<id>/meta.json` and supply one copy of the text. Supported inputs are `latex/*.tex`, `paper.pdf`, `document.docx`, `document.md` and `document.txt`. For other formats, export the author's actual prose to UTF-8 text, preserving paragraph breaks. Record what was used and where it came from. For example:

- A paper's dated version: `{"source_kind":"paper","source_version_date":"2023-12-31","date_basis":"v1 repository record","source":"repository URL for this version"}`. Use the earliest public version or the publication date of the supplied copy. If a later revision changed the prose, get the earlier text or the author's confirmation for the revision.
- A document the author identifies as written without AI: `{"source_kind":"document","written_without_ai":true,"source":"methods chapter","confirmation":"Author confirmed this chapter in the conversation"}`. Record this flag only after the author confirms the actual text. A date is optional. For an unconfirmed later paper or an unconfirmed unpublished document, omit it from the profile.

The scripts exclude samples without qualifying metadata and IDs passed via `--exclude`. Read samples for the style guide and short examples only from the IDs listed in `fingerprint.json` under `papers`. Build profiles in a fresh output directory so earlier samples cannot persist after a source changes.

## 1. Extract and measure

```
python3 scripts/extract.py papers/<id>          # once per paper → sections.json
python3 scripts/fingerprint.py --papers papers --out profile/fingerprint.json
```

Open each eligible sample’s `sections.json` and skim the prose. PDF extraction garbles math; use
PDF papers for prose habits only.

## 2. Write `style.md`

Use exactly these headings. Under each, write short statements, each backed by
a quoted example with its paper id. Prefer statements that the fingerprint
confirms; give the number when it does.

```
# <Author> — style
## Shape of a section
## Sentences (length, openers, we/passive)
## Constructions the author uses
## Reporting figures and numbers
## Comparisons and explanations
## Hedging and qualification
## Punctuation and typography
## Preferred terms and spelling
## What the author does not do
## Tentative habits
```

- "Preferred terms and spelling" lists terms of art the author uses for a
  thing where synonyms exist, transitions they use or never use (for
  example "But", "So", "Hence"), and British or American spelling.

- "What the author does not do" lists filler markers and constructions whose
  fingerprint rate is zero or near zero (for example, no em-dashes) and
  shapes that never occur (rhetorical questions, paragraph-closing summaries).
- A habit seen in only one paper goes under "Tentative habits". So does any
  habit seen only in a paper whose `meta.json` has `"tentative": true`.
- Do not describe the subject matter. The profile must transfer to a paper on a
  different topic.

## 3. Pick long exemplars

```
python3 scripts/long_exemplars.py --papers papers [--exclude ID ...] --out profile/exemplars_long.md
```

This selects up to two passages from distinct eligible samples. It prefers Results sections and can also use paragraphs from a confirmed text document. If no long passage is available, use the short examples. Use the same exclusions at both measurement and selection.

## 4. Write `exemplars.md`

Pick verbatim passages, 1–3 sentences each, 2–4 per move, from at least two
different papers per move where the corpus allows. Copy them as LaTeX from the
extracted `latex` field. Change only references: write `\ref{...}` as `N`,
`\eqref{...}` as `(N)` and `\cite{...}` as `[N]`, and replace literal figure,
table, section and equation numbers the same way, so that both
`Fig.~\ref{fig:cdf}` and `Fig. 3` become `Fig.~N`. Keys and numbers from the
author's papers must not reach a draft. Each passage is one or more complete
sentences; skip fragments cut off by PDF extraction. Label each passage with
paper id and section.

Moves:

1. Opening a results or evaluation section (stating the setup)
2. Introducing a figure or table
3. Reporting an exact value
4. Reporting an approximate or plot-read value
5. Comparing against a baseline or another method
6. Explaining why a result occurs
7. Qualifying or limiting a claim
8. Moving from one finding to the next
9. Defining a term or symbol in passing
10. Ending a paragraph or section
11. Introducing and interpreting an equation (the lead-in before a display
    and the "where …" or explanation after it)

Format:

```
## 2. Introducing a figure or table
> In Fig.~N we show the CDF of the residual ranging error, i.e., the remaining error after mitigation.
— uwb2012, Mitigation Performance
```

Choose passages that show the author's typical shape, not their most unusual
sentence. Skip passages whose meaning depends on content the reader of the
exemplar cannot see.

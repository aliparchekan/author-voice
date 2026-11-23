# Author Voice

Draft a Results section from figures, tables and notes, or revise an existing manuscript using your own writing preferences. Local edits can be applied directly. The agent asks for approval before it moves material between sections, removes content or changes a scientific claim.

## Use it with your agent

From a manuscript project, run the Agent Skills installer and select your agent:

```sh
npx skills add aliparchekan/author-voice --skill author-voice
```

Alternatively, download the [skill ZIP](https://github.com/aliparchekan/author-voice/releases/latest/download/author-voice.zip), extract it, and point your agent to `author-voice/SKILL.md`. An agent that can read Markdown can follow the instructions. The helper scripts require Python 3.12 or later. PDF source extraction also needs Poppler's `pdftotext`. The agent supplies the writing model.

## Try it

Give your agent the **paper folder**, **current manuscript file** and **comments**, then say “Use Author Voice to tune the whole paper.” You can paste comments, attach a reviewer letter or supply an annotated document. The agent returns an edited copy and a comment-by-comment report. For a current PDF, point to its editable source if the project has several versions. [Whole-paper revision workflow](skills/author-voice/references/commented-revision.md)

> Use author-voice to revise a copy of my manuscript for a first-time reader. Keep my terminology, claims, uncertainty, equations and citations. Apply local clarity edits, and show me any proposed major restructuring for approval.

For drafting, supply the figures, captions, tables, result notes and definitions from earlier sections. Ask for the Results in LaTeX with a map from each claim to its evidence. Check descriptions of plotted comparisons against the figure legends.

## Which writing counts toward my profile?

Use a paper you authored that was public **before January 1, 2024**, or **any document you confirm you wrote without AI assistance**. A report from 2025 or an undated thesis chapter can qualify by confirmation. A 2023 preprint qualifies by its date. For a paper revised after the cutoff, supply the earlier version or confirm the newer text. For co-authored work, identify the parts you wrote. You can begin without a profile using your explicit preferences.

Voice selection and manuscript evidence are independent. You can revise a current manuscript and report new results. The [profile guide](skills/author-voice/references/profile.md) includes the input formats and source metadata.

## Evaluation

In a sealed test on one held-out engineering Results section, the earlier writing procedure generated 30 drafts. The judge consistently preferred the profiled draft in two of ten matched voice comparisons using training-paper references, and five of ten using the author's original Results as reference. Five profiled drafts described a model–condition combination absent from a figure legend. These figures measure one section. The source-selection policy in this public release was tested separately on dated papers, author-confirmed documents and excluded controls.

The skill uses the [Agent Skills format](https://agentskills.io/specification). See [credits and reuse terms](skills/author-voice/CREDITS.md).

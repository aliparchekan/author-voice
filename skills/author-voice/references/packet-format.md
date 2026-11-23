# Evidence packet format

One directory per section to write. `check.py` reads these files; the writer
reads all of them.

| File | Required | Content |
|------|----------|---------|
| `results_notes.md` | yes | One finding per line: `- N01 \| locator \| kind \| text`. `kind` containing `plot-read` or `approx` marks values read off a plot; anything else is exact. |
| `context.md` | yes | Terms, acronyms, symbols and assumptions the paper established before this section. Anything named here may be used without definition. |
| `captions.md` | no | `Fig. N. caption` per line. Figure numbers come from here. |
| `abstract.md` or `neutral.md` | no | The paper's abstract, or neutral factual notes in its place. |
| `tables/` | no | Tables as `.tex`, `.csv` or `.md`. Values count as exact evidence. |
| any other `*.md` / `*.txt` | no | Also read as evidence, e.g. `figures.md` listing axis ranges and tick labels the writer can see in the figure images. |
| `meta.json` | no | `{"target_section": "...", "target_words": N}` (±15%) or `"length_words": [lo, hi]`. No title. |

The writer's outputs, next to each other:

- `section.tex` — the section, starting with its `\section{...}` line.
- `claims.json` — `{"claims": [{"sentence": "...", "notes": ["N01", "N04"]}]}`.

`check.py` looks for `claims.json` next to `section.tex` unless `--claims` is
given.

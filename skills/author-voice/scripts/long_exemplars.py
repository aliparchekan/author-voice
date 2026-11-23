#!/usr/bin/env python3
"""Pick whole results-type passages from the author's papers as long exemplars.

Usage: long_exemplars.py --papers DIR [--exclude ID ...] [--n 2] [--max-words 600] --out FILE

Short exemplars show single moves; these show how the author's paragraphs run:
where conditions and parentheses go, how figures and numbers are woven in, how
one finding leads to the next. Picks one passage per eligible LaTeX or text sample
(PDF extraction can garble math), non-tentative samples first, each cut at a
paragraph boundary. References become N, (N), [N]; floats and comments go.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from extract import strip_comments
from fingerprint import tokens
from sources import profile_sources

_RESULTS = re.compile(r"result|performance|evaluation|simulation|numerical|experiment", re.I)
_FLOATS = ("figure", "figure*", "table", "table*", "algorithm", "algorithm*")


def neutralize_numbers(text: str) -> str:
    return re.sub(r"\b(Figs?\.|Figures?|Tables?|Sections?|Sec\.|Eqs?\.)(\s*~?\s*)\d+", r"\1\2N", text)


def normalize(latex: str) -> str:
    t = strip_comments(latex)
    for env in _FLOATS:
        t = re.sub(r"\\begin\{" + re.escape(env) + r"\}.*?\\end\{" + re.escape(env) + r"\}", "", t, flags=re.S)
    t = re.sub(r"\\label\s*\{[^}]*\}", "", t)
    t = re.sub(r"\\footnote\s*\{(?:[^{}]|\{[^{}]*\})*\}", "", t)
    t = re.sub(r"\(\s*\\ref\s*\{[^}]*\}\s*\)", "(N)", t)
    t = re.sub(r"\\eqref\s*\{[^}]*\}", "(N)", t)
    t = re.sub(r"\\(?:ref|autoref|cref|Cref)\s*\{[^}]*\}", "N", t)
    t = re.sub(r"\\cite[pt]?\s*(?:\[[^\]]*\])?\s*\{[^}]*\}", "N", t)
    t = re.sub(r"\[\s*N\s*\]", "[N]", t)
    t = neutralize_numbers(t)
    t = re.sub(r"[ \t]+\n", "\n", t)
    return re.sub(r"\n{3,}", "\n\n", t).strip()


def _cut(text: str, max_words: int) -> str:
    out, n = [], 0
    for para in [p for p in re.split(r"\n\s*\n", text) if p.strip()]:
        w = len(tokens(para))
        if out and n + w > max_words:
            break
        out.append(para.strip())
        n += w
    return "\n\n".join(out)


def _results_passage(sections: list[dict]) -> tuple[str, str]:
    """The first results-type top-level section with its subsections, as LaTeX."""
    start = None
    for pattern in (r"result", r"numerical|simulation|experiment", r"evaluation|performance"):
        start = next((i for i, s in enumerate(sections)
                      if s["level"] <= 1 and re.search(pattern, s["title"], re.I)), None)
        if start is not None:
            break
    if start is None:
        return "", ""
    parts = [sections[start]["latex"]]
    for s in sections[start + 1:]:
        if s["level"] <= sections[start]["level"]:
            break
        parts.append(s["latex"])
    return sections[start]["title"], "\n\n".join(p for p in parts if p.strip())


def pick(papers_dir: Path, exclude: list[str], n: int = 2, max_words: int = 600) -> list[dict]:
    cands = []
    for sj, meta, _ in profile_sources(papers_dir, exclude):
        pid = sj.parent.name
        data = json.loads(sj.read_text())
        if data.get("format") not in ("latex", "text"):
            continue
        tentative = meta.get("tentative", False)
        title, passage = _results_passage(data["sections"])
        if not passage and data.get("format") == "text":
            sample = next((s for s in data["sections"] if len(tokens(s["prose"])) >= 100), None)
            if sample:
                title, passage = sample["title"], sample["prose"]
        text = _cut(normalize(passage) if data["format"] == "latex" else neutralize_numbers(passage), max_words)
        if len(tokens(text)) >= 100:
            cands.append({"paper": pid, "section": title, "tentative": tentative, "text": text})
    cands.sort(key=lambda c: (c["tentative"], c["paper"]))
    return cands[:n]


def render(picks: list[dict]) -> str:
    out = ["# Long exemplars", "",
           "Passages from the author's writing. Read them for how paragraphs run;",
           "do not reuse their sentences, numbers or claims.", ""]
    for p in picks:
        out += [f"## {p['paper']} — {p['section']}" + (" (tentative paper)" if p["tentative"] else ""), "",
                p["text"], ""]
    return "\n".join(out)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--papers", required=True, type=Path)
    ap.add_argument("--exclude", nargs="*", default=[])
    ap.add_argument("--n", type=int, default=2)
    ap.add_argument("--max-words", type=int, default=600)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args(argv)
    picks = pick(args.papers, args.exclude, args.n, args.max_words)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(picks) if picks else "# Long exemplars\n\nNo eligible long passage was available. Use the short examples.\n")
    for p in picks:
        print(f"{p['paper']:12s} {p['section'][:40]:40s} {len(tokens(p['text']))} words")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

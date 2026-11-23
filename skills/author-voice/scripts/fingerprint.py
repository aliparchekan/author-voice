#!/usr/bin/env python3
"""Measure an author's prose: the numeric part of a profile.

Usage: fingerprint.py --papers DIR [--exclude ID ...] --out FILE
  DIR/<paper>/sections.json come from extract.py. Abstract and
  acknowledgment sections are skipped. The output holds pooled statistics,
  per-paper statistics, statistics for results-type sections only, and a
  baseline: for every marker, the highest per-paper rate. check.py treats the
  baseline as the most the author ever used a marker.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from collections import Counter
from pathlib import Path

from lexicon import ABBREVIATIONS, FILLER, FUNCTION_WORDS, HEDGES, TRANSITIONS
from sources import profile_sources

_MATH_RE = re.compile(r"(?<!\\)\$[^$]+?(?<!\\)\$", re.S)
_TOKEN_RE = re.compile(r"\$[^$]*\$|\d+(?:\.\d+)?|[A-Za-z][A-Za-z'\-]*")
_BOUNDARY_RE = re.compile(r"(?<=[.!?])[\"')\]]?\s+(?=[A-Z0-9$\\(\[\"])")


def _protect(text: str) -> tuple[str, list[str]]:
    kept: list[str] = []

    def keep(m: re.Match) -> str:
        kept.append(m.group(0))
        return f"\x00{len(kept) - 1}\x00"

    text = _MATH_RE.sub(keep, text)
    for abbr in sorted(ABBREVIATIONS, key=len, reverse=True):
        text = re.sub(r"(?<![A-Za-z])" + re.escape(abbr), lambda m: keep(m), text)
    return text, kept


def _restore(text: str, kept: list[str]) -> str:
    while "\x00" in text:
        text = re.sub(r"\x00(\d+)\x00", lambda m: kept[int(m.group(1))], text)
    return text


def split_sentences(prose: str) -> list[str]:
    out: list[str] = []
    for para in re.split(r"\n\s*\n", prose):
        para = " ".join(para.split())
        if not para:
            continue
        protected, kept = _protect(para)
        for s in _BOUNDARY_RE.split(protected):
            s = _restore(s, kept).strip()
            if s:
                out.append(s)
    return out


def paragraphs(prose: str) -> list[list[str]]:
    return [split_sentences(p) for p in re.split(r"\n\s*\n", prose) if p.strip()]


def tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall(text)


def _count_phrase(lower: str, phrase: str) -> int:
    return len(re.findall(r"(?<![A-Za-z])" + re.escape(phrase) + r"(?![A-Za-z])", lower))


def phrase_rates(text: str, phrases: list[str]) -> dict[str, float]:
    lower = _MATH_RE.sub(" ", text).lower()
    n = max(len(tokens(text)), 1)
    return {p: round(1000.0 * _count_phrase(lower, p) / n, 3) for p in phrases}


def _quantiles(xs: list[int]) -> dict[str, float]:
    if not xs:
        return {k: 0.0 for k in ("mean", "sd", "p10", "p25", "p50", "p75", "p90")}
    xs = sorted(xs)

    def q(p: float) -> float:
        i = (len(xs) - 1) * p
        lo, hi = int(i), min(int(i) + 1, len(xs) - 1)
        return round(xs[lo] + (xs[hi] - xs[lo]) * (i - lo), 2)

    return {
        "mean": round(statistics.fmean(xs), 2),
        "sd": round(statistics.pstdev(xs), 2),
        "p10": q(0.1), "p25": q(0.25), "p50": q(0.5), "p75": q(0.75), "p90": q(0.9),
    }


_PASSIVE_RE = re.compile(r"\b(?:is|are|was|were|be|been|being)\s+(?:\w+ly\s+)?\w+(?:ed|en|wn)\b", re.I)


def stats(prose: str) -> dict:
    sents = split_sentences(prose)
    words = tokens(prose)
    n = max(len(words), 1)
    plain = _MATH_RE.sub(" ", prose)
    lower_words = [w.lower() for w in words if not w.startswith("$")]
    fw = Counter(w for w in lower_words if w in set(FUNCTION_WORDS))
    openers = Counter()
    for s in sents:
        t = tokens(s)
        if t:
            openers[t[0].lower() if not t[0].startswith("$") else "$math$"] += 1
    paras = paragraphs(prose)
    return {
        "words": len(words),
        "sentences": len(sents),
        "sentence_length": _quantiles([len(tokens(s)) for s in sents]),
        "paragraph_sentences": _quantiles([len(p) for p in paras]),
        "function_words": {w: round(1000.0 * fw[w] / n, 3) for w in FUNCTION_WORDS},
        "transitions": phrase_rates(prose, TRANSITIONS),
        "hedges": phrase_rates(prose, HEDGES),
        "filler": phrase_rates(prose, FILLER),
        "punctuation": {
            "em_dash": round(1000.0 * (plain.count("—")) / n, 3),
            "semicolon": round(1000.0 * plain.count(";") / n, 3),
            "colon": round(1000.0 * plain.count(":") / n, 3),
            "parenthesis": round(1000.0 * plain.count("(") / n, 3),
        },
        "we_rate": round(1000.0 * sum(1 for w in lower_words if w in ("we", "our", "us")) / n, 3),
        "passive_rate": round(1000.0 * len(_PASSIVE_RE.findall(plain)) / n, 3),
        "math_rate": round(1000.0 * sum(1 for w in words if w.startswith("$")) / n, 3),
        "openers": dict(openers.most_common(25)),
    }


def fingerprint(papers: dict[str, str], results: dict[str, str] | None = None) -> dict:
    per = {pid: stats(text) for pid, text in papers.items()}
    pooled = stats("\n\n".join(papers.values()))
    baseline = {}
    for key in ("filler", "transitions", "hedges"):
        baseline[key] = {m: max(p[key][m] for p in per.values()) for m in pooled[key]}
    baseline["punctuation"] = {m: max(p["punctuation"][m] for p in per.values()) for m in pooled["punctuation"]}
    out = {"papers": sorted(papers), "pooled": pooled, "per_paper": per, "baseline": baseline}
    if results is not None:
        out["results"] = stats("\n\n".join(results.values()))
    return out


_SKIP = re.compile(r"^(abstract|acknowledge?ments?)$", re.I)
_RESULTS = re.compile(r"result|performance|evaluation|simulation|numerical|experiment", re.I)


def load_papers(papers_dir: Path, exclude: list[str]) -> tuple[dict[str, str], dict[str, str]]:
    body, results = {}, {}
    for sj, _, _ in profile_sources(papers_dir, exclude):
        pid = sj.parent.name
        data = json.loads(sj.read_text())
        parts, res_parts, top = [], [], ""
        for s in data["sections"]:
            if s["level"] <= 1:
                top = s["title"]
            if _SKIP.match(s["title"].strip()):
                continue
            parts.append(s["prose"])
            if _RESULTS.search(top) or _RESULTS.search(s["title"]):
                res_parts.append(s["prose"])
        if not any(p.strip() for p in parts):
            continue
        body[pid] = "\n\n".join(p for p in parts if p)
        if res_parts:
            results[pid] = "\n\n".join(p for p in res_parts if p)
    return body, results


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--papers", required=True, type=Path)
    ap.add_argument("--exclude", nargs="*", default=[])
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args(argv)
    body, results = load_papers(args.papers, args.exclude)
    if not body:
        print(f"No eligible writing samples with extracted prose under {args.papers}", file=sys.stderr)
        return 1
    fp = fingerprint(body, results or None)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(fp, indent=1))
    sl = fp["pooled"]["sentence_length"]
    print(f"{len(body)} papers, {fp['pooled']['words']} words, {fp['pooled']['sentences']} sentences; "
          f"sentence length median {sl['p50']} (p25 {sl['p25']}, p75 {sl['p75']})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

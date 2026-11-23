#!/usr/bin/env python3
"""Paper-level diagnostics for the revise structure pass.

Usage:
  structure.py diagnose PAPER_DIR            → JSON: sections, items
  structure.py compare ORIGINAL_DIR REVISED_DIR → JSON: what the revision lost

PAPER_DIR holds latex/*.tex (main file has \\begin{document}) or paper.pdf.

Items found by diagnose:
  acronym_defined_later  an acronym used in one section, defined in a later one
  forward_reference      \\ref to a section/equation/theorem labelled later
  repeated_passage       an 8-word passage that appears in two sections
  repeated_number        a decimal value reported in more than one section
(The abstract is exempt from the repeat checks.)

Change classes for a structure plan (see classify):
  small: applied directly. big: listed for the user's approval first.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from check import _ACR_RE, _KEY_CMD, _keys, _sentence_numbers
from extract import document_body, expand_acronyms, find_main, latex_sections, load_latex, pdf_sections, to_prose
from fingerprint import _MATH_RE, split_sentences, tokens

SMALL_ACTIONS = {"reorder_within_section", "move_definition", "add_bridge_sentence", "reword", "fix_reference"}
BIG_ACTIONS = {
    "move_between_sections", "merge_sections", "split_section", "delete_content", "rename_section",
    "add_section", "remove_float", "merge_floats", "cut_for_length", "move_to_supplement", "change_claim",
}


def classify(change: dict) -> str:
    """'small' changes are applied directly; anything else needs the user's approval."""
    return "small" if change.get("action") in SMALL_ACTIONS else "big"


def load_sections(paper_dir: Path) -> list[dict]:
    main = find_main(paper_dir / "latex") if (paper_dir / "latex").is_dir() else None
    if main:
        full = load_latex(main)
        body = expand_acronyms(document_body(full), full)
        secs = latex_sections(body)
    else:
        secs = pdf_sections(paper_dir / "paper.pdf")
    for s in secs:
        s["prose"] = to_prose(s["latex"]) if main else s["latex"]
    return secs


def _ngrams(prose: str, n: int = 8) -> set[str]:
    words = [w.lower() for w in tokens(_MATH_RE.sub(" ", prose)) if not w.isdigit()]
    return {" ".join(words[i:i + n]) for i in range(len(words) - n + 1)}


def diagnose(paper_dir: Path) -> dict:
    secs = load_sections(paper_dir)
    items: list[dict] = []
    titles = [s["title"] for s in secs]

    # acronyms: first use vs. first definition "(ACR)" across sections
    first_use: dict[str, int] = {}
    defined: dict[str, int] = {}
    for i, s in enumerate(secs):
        plain = _MATH_RE.sub(" ", s["prose"])
        for m in re.finditer(r"\(([A-Z][A-Za-z0-9]*[A-Z0-9])s?\)", plain):
            defined.setdefault(m.group(1), i)
        no_defs = re.sub(r"\(([A-Z][A-Za-z0-9]*[A-Z0-9])s?\)", " ", plain)
        for m in _ACR_RE.finditer(no_defs):
            if s["title"] != "Abstract":
                first_use.setdefault(m.group(1), i)
    for acr, i in first_use.items():
        j = defined.get(acr)
        if j is not None and j > i:
            items.append({"kind": "acronym_defined_later",
                          "detail": {"acronym": acr, "first_used_in": titles[i], "defined_in": titles[j]}})

    # one term, one name: an acronym expanded more than once, or with different long forms
    # (sciwrite's consistent-terminology pass, CC BY 4.0, L. A. Barba)
    long_forms: dict[str, list[tuple[str, str]]] = {}
    for i, s in enumerate(secs):
        if s["title"] == "Abstract":
            continue
        plain = _MATH_RE.sub(" ", s["prose"])
        for m in re.finditer(r"((?:[A-Za-z][\w\-]*\s+){1,6})\(([A-Z][A-Za-z0-9]*[A-Z0-9])s?\)", plain):
            acr = m.group(2)
            words = m.group(1).split()[-max(len([c for c in acr if c.isupper()]), 1):]
            long_forms.setdefault(acr, []).append((" ".join(words).lower(), titles[i]))
    for acr, forms in long_forms.items():
        if len(forms) > 1:
            items.append({"kind": "term_variant", "detail": {
                "acronym": acr, "long_forms": sorted({f for f, _ in forms}), "sections": [t for _, t in forms]}})

    # forward references to labels that live in a later section
    label_at: dict[str, int] = {}
    for i, s in enumerate(secs):
        for key in re.findall(r"\\label\s*\{([^}]*)\}", s["latex"]):
            label_at.setdefault(key, i)
    for i, s in enumerate(secs):
        for m in _KEY_CMD.finditer(s["latex"]):
            if m.group(1).startswith("cite"):
                continue
            for key in (k.strip() for k in m.group(2).split(",")):
                j = label_at.get(key)
                if j is not None and j > i and not key.startswith(("fig", "tab")):
                    items.append({"kind": "forward_reference", "detail": {"key": key, "from": titles[i], "to": titles[j]}})

    # the same passage or the same decimal value in two sections
    body = [(i, s) for i, s in enumerate(secs) if s["title"] != "Abstract"]
    grams = {i: _ngrams(s["prose"]) for i, s in body}
    for a in range(len(body)):
        for b in range(a + 1, len(body)):
            ia, ib = body[a][0], body[b][0]
            shared = grams[ia] & grams[ib]
            if shared:
                items.append({"kind": "repeated_passage",
                              "detail": {"sections": [titles[ia], titles[ib]], "example": sorted(shared)[0],
                                         "shared_8grams": len(shared)}})
    where: dict[str, set[str]] = {}
    for i, s in body:
        for sent in split_sentences(s["prose"]):
            for num in _sentence_numbers(sent):
                if "." in num["text"]:
                    where.setdefault(num["text"], set()).add(titles[i])
    for value, places in sorted(where.items()):
        if len(places) > 1:
            items.append({"kind": "repeated_number", "detail": {"value": value, "sections": sorted(places)}})

    sections = [{"title": s["title"], "level": s["level"], "words": len(tokens(s["prose"]))} for s in secs]
    return {"sections": sections, "items": items}


def _all_numbers(secs: list[dict]) -> set[tuple]:
    out = set()
    for s in secs:
        for sent in split_sentences(s["prose"]):
            out |= {(n["text"], n["unit"]) for n in _sentence_numbers(sent)}
    return out


def compare(original_dir: Path, revised_dir: Path) -> dict:
    """What the whole revised paper lost or gained against the original."""
    o, r = load_sections(original_dir), load_sections(revised_dir)
    o_latex, r_latex = "\n".join(s["latex"] for s in o), "\n".join(s["latex"] for s in r)
    def cite(text: str) -> set[str]:
        return {
            key for match in _KEY_CMD.finditer(text)
            if match.group(1).startswith("cite")
            for key in match.group(2).replace(" ", "").split(",") if key
        }

    def labels(text: str) -> set[str]:
        return set(re.findall(r"\\label\s*\{([^}]*)\}", text))

    o_nums, r_nums = _all_numbers(o), _all_numbers(r)
    o_titles, r_titles = [s["title"] for s in o], [s["title"] for s in r]
    return {
        "numbers_lost": sorted(f"{v} {u or ''}".strip() for v, u in o_nums - r_nums),
        "numbers_added": sorted(f"{v} {u or ''}".strip() for v, u in r_nums - o_nums),
        "citations_lost": sorted(cite(o_latex) - cite(r_latex)),
        "labels_lost": sorted(labels(o_latex) - labels(r_latex)),
        "references_lost": sorted(set(_keys(o_latex)) - set(_keys(r_latex)) - (cite(o_latex) - cite(r_latex))),
        "sections_removed": [t for t in o_titles if t not in r_titles],
        "sections_added": [t for t in r_titles if t not in o_titles],
        "words": {"original": sum(len(tokens(s["prose"])) for s in o), "revised": sum(len(tokens(s["prose"])) for s in r)},
    }


def main(argv: list[str]) -> int:
    if len(argv) == 2 and argv[0] == "diagnose":
        print(json.dumps(diagnose(Path(argv[1])), indent=1, ensure_ascii=False))
        return 0
    if len(argv) == 3 and argv[0] == "compare":
        print(json.dumps(compare(Path(argv[1]), Path(argv[2])), indent=1, ensure_ascii=False))
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

#!/usr/bin/env python3
"""Deterministic diagnostics for a drafted section.

Usage: check.py --section FILE --packet DIR --profile DIR|none [--claims FILE]
       check.py --section NEW --original OLD [--context EARLIER] --profile DIR|none

Revision mode (--original): the original's numbers and reference keys count
as evidence; flags number_dropped / reference_dropped list what the revision
lost. --context adds text the reader has already seen (earlier sections).

Prints JSON: {"errors": [...], "flags": [...], "skipped": [...], "stats": {...}}.
Each item is {"kind", "sentence_index", "sentence", "detail"}.

Errors must be fixed before a draft is final:
  acronym_before_definition, acronym_undefined, number_unsupported,
  number_excess_precision, claim_unknown_note, length_out_of_bounds
Flags are leads for the reviser, not verdicts:
  symbol_undefined, number_small_unverified, filler_above_author_rate,
  em_dash_above_author_rate, formulaic_closer, long_series,
  sentence_length_off_profile, claim_unlinked_number

Packet files read (all optional except results_notes.md):
  results_notes.md  lines "- N01 | locator | kind | text"; kind containing
                    "plot-read" marks values read off a plot
  context.md        terms, symbols and assumptions established earlier
  captions.md, neutral.md, abstract.md, tables/*  extra evidence for numbers
  meta.json         {"target_words": N} (+/-15%) or {"length_words": [lo, hi]}
Profile directory: fingerprint.json from fingerprint.py, or "none".
Claims (default: claims.json next to the section):
  {"claims": [{"sentence": "...", "notes": ["N01", ...]}]}
"""
from __future__ import annotations

import argparse
import difflib
import json
import math
import re
import sys
from pathlib import Path

from extract import to_prose
from fingerprint import _MATH_RE, paragraphs, split_sentences, tokens
from lexicon import COMMON_ACRONYMS, FILLER, FORMULAIC_CLOSER_OPENERS, FUNCTION_WORDS

NUMBER_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "fifteen": 15, "twenty": 20, "fifty": 50, "hundred": 100,
}
UNITS = (
    "m", "cm", "mm", "km", "s", "ms", "us", "ns", "Hz", "kHz", "MHz", "GHz",
    "THz", "dB", "dBm", "dBi", "W", "mW", "%", "deg", "rad", "mrad", "m/s",
    "m²", "degrees", "meters", "metres", "samples", "elements", "antennas",
)

# --------------------------------------------------------------- packet ---


def _num_items(text: str) -> list[dict]:
    items = []
    for m in re.finditer(r"(?<![\w.])-?\d+(?:\.\d+)?", text):
        items.append({"text": m.group(0).lstrip("-"), "value": abs(float(m.group(0)))})
    for w, v in NUMBER_WORDS.items():
        if re.search(r"(?<![A-Za-z])" + w + r"(?![A-Za-z])", text, re.I):
            items.append({"text": str(v), "value": float(v)})
    return items


def parse_notes(text: str) -> list[dict]:
    notes = []
    for line in text.splitlines():
        m = re.match(r"^\s*-\s*(N\d+)\s*\|\s*([^|]*)\|\s*([^|]*)\|\s*(.*)$", line)
        if not m:
            continue
        kind = m.group(3).strip().lower()
        notes.append({
            "id": m.group(1),
            "locator": m.group(2).strip(),
            "kind": kind,
            "precision": "plot-read" if "plot" in kind or "approx" in kind else "exact",
            "text": m.group(4).strip(),
            "numbers": _num_items(m.group(4)),
        })
    return notes


def _read_opt(p: Path) -> str:
    return p.read_text() if p.is_file() else ""


def load_packet(packet: Path) -> dict:
    notes = parse_notes(_read_opt(packet / "results_notes.md"))
    context = _read_opt(packet / "context.md")
    # every other text file in the packet (captions, abstract, figure notes, ...) is evidence
    extra = "\n".join(
        p.read_text(errors="replace") for p in sorted(packet.glob("*"))
        if p.is_file() and p.suffix in (".md", ".txt") and p.name not in ("results_notes.md", "context.md")
    )
    tables = packet / "tables"
    if tables.is_dir():
        extra += "\n" + "\n".join(p.read_text(errors="replace") for p in sorted(tables.iterdir()) if p.is_file())
    meta = json.loads(_read_opt(packet / "meta.json") or "null")
    captions = {}
    for line in _read_opt(packet / "captions.md").splitlines():
        m = re.match(r"^\s*(?:Fig(?:ure)?\.?|Table)\s*(\d+)[.:]?\s*(.*)$", line)
        if m:
            captions[int(m.group(1))] = m.group(2)
    evidence = []
    for n in notes:
        for item in n["numbers"]:
            evidence.append({**item, "precision": n["precision"], "source": n["id"]})
    for item in _num_items(context + "\n" + extra):
        evidence.append({**item, "precision": "exact", "source": "packet"})
    return {"notes": notes, "context": context, "evidence": evidence, "meta": meta, "captions": captions}


# -------------------------------------------------------------- helpers ---


def _item(kind: str, idx: int, sents: list[str], **detail) -> dict:
    return {"kind": kind, "sentence_index": idx, "sentence": sents[idx] if 0 <= idx < len(sents) else "", "detail": detail}


def _decimals(s: str) -> int:
    return len(s.split(".")[1]) if "." in s else 0


_ACR_RE = re.compile(r"(?<![A-Za-z0-9\\{_^])([A-Z][A-Z0-9]*[A-Z0-9])(s?)(?![A-Za-z0-9])")


def _acronyms_in(text: str) -> list[str]:
    plain = _MATH_RE.sub(" ", text)
    out = []
    for m in _ACR_RE.finditer(plain):
        tok = m.group(1)
        if tok == "EQN":  # display-equation placeholder from to_prose
            continue
        if len(tok) >= 2 and not tok.isdigit() and sum(c.isalpha() for c in tok) >= 2:
            out.append(tok)
    return out


# ------------------------------------------------------------- checks ---


def check_acronyms(sents: list[str], context: str) -> list[dict]:
    established = set(_acronyms_in(context)) | COMMON_ACRONYMS
    first_use: dict[str, int] = {}
    defined_at: dict[str, int] = {}
    for i, s in enumerate(sents):
        plain = _MATH_RE.sub(" ", s)
        for m in re.finditer(r"\(([A-Z][A-Za-z0-9]*[A-Z0-9])s?\)", plain):
            defined_at.setdefault(m.group(1), i)
        without_defs = re.sub(r"\(([A-Z][A-Za-z0-9]*[A-Z0-9])s?\)", " ", plain)
        for a in _acronyms_in(without_defs):
            first_use.setdefault(a, i)
    errors = []
    for a, i in sorted(first_use.items(), key=lambda x: x[1]):
        if a in established or re.fullmatch(r"[IVXL]+", a):
            continue
        if a in defined_at:
            if defined_at[a] > i:
                errors.append(_item("acronym_before_definition", i, sents, acronym=a, defined_in_sentence=defined_at[a]))
        else:
            errors.append(_item("acronym_undefined", i, sents, acronym=a))
    return errors


_REF_BEFORE = re.compile(
    r"(?:Fig(?:ure)?s?\.?|Tables?|Tab\.|Sec(?:tion)?s?\.?|Eqs?\.?|Theorems?|Lemmas?|Propositions?|"
    r"Algorithms?|Appendix|Remarks?|Corollary|Steps?|Cases?)\s*(?:\d+\s*(?:[-\u2013,]|and)\s*)*$",
    re.I,
)


def _sentence_numbers(sentence: str) -> list[dict]:
    out = []
    plain = re.sub(r"\[[\d,\s\u2013-]+\]", " ", sentence)  # citations
    plain = re.sub(r"\((?:\d+[a-z]?)\)", " ", plain)  # equation references
    for m in re.finditer(r"(?<![\w.])-?\d+(?:\.\d+)?(?![\w])", plain):
        txt = m.group(0).lstrip("-")
        before = plain[max(0, m.start() - 40): m.start()]
        if _REF_BEFORE.search(before):
            continue
        after = plain[m.end(): m.end() + 12]
        unit = next((u for u in UNITS if re.match(r"\s*" + re.escape(u) + r"(?![A-Za-z])", after)), None)
        if after.startswith("-D") or after.startswith("D "):
            continue
        out.append({"text": txt, "value": float(txt), "unit": unit})
    return out


_SCALE = {
    "m": ("length", 1.0), "cm": ("length", 1e-2), "mm": ("length", 1e-3), "km": ("length", 1e3),
    "Hz": ("freq", 1.0), "kHz": ("freq", 1e3), "MHz": ("freq", 1e6), "GHz": ("freq", 1e9), "THz": ("freq", 1e12),
    "s": ("time", 1.0), "ms": ("time", 1e-3), "us": ("time", 1e-6), "ns": ("time", 1e-9),
    "W": ("power", 1.0), "mW": ("power", 1e-3),
}


def _unit_variants(num: dict) -> list[dict]:
    """The number itself plus the same quantity written in sibling units."""
    out = [num]
    unit = num.get("unit")
    if unit in _SCALE:
        family, scale = _SCALE[unit]
        for other, (fam, s2) in _SCALE.items():
            if fam == family and other != unit:
                v = num["value"] * scale / s2
                txt = f"{v:.10f}".rstrip("0").rstrip(".")
                out.append({"text": txt, "value": float(txt), "unit": other})
    return out


def _match_number(num: dict, evidence: list[dict]) -> str:
    verdicts = [_match_one(n, evidence) for n in _unit_variants(num)]
    if "supported" in verdicts:
        return "supported"
    return "excess" if verdicts[0] == "excess" else "unsupported"


def _match_one(num: dict, evidence: list[dict]) -> str:
    d = _decimals(num["text"])
    v = num["value"]
    supported = excess = False
    for ev in evidence:
        dn = _decimals(ev["text"])
        if d <= dn and math.isclose(round(ev["value"], d), v, abs_tol=1e-9):
            supported = True
        elif math.isclose(ev["value"], v, abs_tol=1e-9):
            supported = True
        elif (d > dn and math.isclose(round(v, dn), ev["value"], abs_tol=1e-9)
              and abs(v - ev["value"]) <= 0.05 * max(abs(ev["value"]), 1e-9)):
            # same number reported with more digits than the evidence carries
            excess = True
    if supported:
        return "supported"
    return "excess" if excess else "unsupported"


def check_numbers(sents: list[str], evidence: list[dict]) -> tuple[list[dict], list[dict]]:
    errors, flags = [], []
    for i, s in enumerate(sents):
        for num in _sentence_numbers(s):
            verdict = _match_number(num, evidence)
            if verdict == "supported":
                continue
            small = float(num["value"]).is_integer() and num["value"] <= 10
            if verdict == "excess":
                errors.append(_item("number_excess_precision", i, sents, value=num["text"], unit=num["unit"]))
            elif small:
                if num["unit"]:
                    flags.append(_item("number_small_unverified", i, sents, value=num["text"], unit=num["unit"]))
            else:
                errors.append(_item("number_unsupported", i, sents, value=num["text"], unit=num["unit"]))
    return errors, flags


_FIG_REF = re.compile(
    r"\bFig(?:ure)?s?\.?\s*(\d+)((?:\s*(?:,|and|[-–])\s*\d+)*)", re.I)


def _cited_figures(sentence: str) -> list[int]:
    out = []
    for m in _FIG_REF.finditer(sentence):
        nums = [int(m.group(1))] + [int(x) for x in re.findall(r"\d+", m.group(2) or "")]
        if re.search(r"[-–]", m.group(2) or "") and len(nums) == 2:
            nums = list(range(nums[0], nums[1] + 1))
        out += nums
    return sorted(set(out))


def _condition_key(num: dict) -> tuple | None:
    unit = num.get("unit")
    if not unit:
        return None
    if unit in _SCALE:
        family, scale = _SCALE[unit]
        return (family, round(num["value"] * scale, 9))
    return (unit, num["value"])


def check_figure_conditions(sents: list[str], captions: dict[int, str]) -> list[dict]:
    """A condition (number with unit) cited from a figure whose caption lacks it."""
    if not captions:
        return []
    shown = {n: {_condition_key(x) for x in _sentence_numbers(text)} - {None} for n, text in captions.items()}
    flags = []
    for i, s in enumerate(sents):
        cited = [n for n in _cited_figures(s) if n in captions]
        if not cited:
            continue
        in_cited = set().union(*(shown[n] for n in cited))
        for num in _sentence_numbers(s):
            key = _condition_key(num)
            if key is None or key in in_cited:
                continue
            elsewhere = sorted(n for n, keys in shown.items() if key in keys)
            if elsewhere:
                flags.append(_item("figure_condition_mismatch", i, sents,
                                   condition=f"{num['text']} {num['unit']}", cited=cited, shown_in=elsewhere))
    return flags


_DISTRIBUTION = re.compile(r"\bCDFs?\b|cumulative distribution|\bhistograms?\b|empirical distribution|\bpercentiles?\b", re.I)
_POPULATION = re.compile(
    r"\b(?:fraction|proportion|share|percentage|probability|across|per|each|realizations?|trials?|runs?|"
    r"samples?|locations?|positions?|users?|points?|instances?)\b|\bover\s+(?:the\s+|all\s+)?\w+", re.I)


def check_distributions(sents: list[str]) -> list[dict]:
    """First mention of a distribution must say what is counted and over what."""
    for i, s in enumerate(sents):
        plain = _MATH_RE.sub(" ", s)
        if _DISTRIBUTION.search(plain):
            window = " ".join(_MATH_RE.sub(" ", t) for t in sents[i:i + 2])
            if not _POPULATION.search(window):
                return [_item("distribution_without_population", i, sents)]
            return []
    return []


_GREEK = (
    "alpha beta gamma delta epsilon varepsilon zeta eta theta vartheta iota kappa lambda mu nu xi pi rho "
    "sigma tau upsilon phi varphi chi psi omega Gamma Delta Theta Lambda Xi Pi Sigma Phi Psi Omega"
).split()
_SKIP_CMDS = {
    "mathrm", "text", "mathbf", "bm", "boldsymbol", "mathcal", "mathbb", "hat", "bar", "tilde",
    "left", "right", "cdot", "times", "leq", "geq", "le", "ge", "approx", "sim", "log", "exp",
    "sqrt", "frac", "sum", "prod", "min", "max", "arg", "infty", "in", "to", "mid", "neq", "ldots",
    "dots", "cdots", "quad", "operatorname", "mathsf", "check", "dot", "vec", "top", "T", "H",
    "det", "tr", "Re", "Im", "lim", "sin", "cos", "tan", "partial", "nabla", "pm", "mp", "propto",
    "big", "Big", "bigg", "lVert", "rVert", "Vert", "vert", "langle", "rangle", "circ", "star",
    "triangleq", "coloneqq", "equiv", "forall", "exists", "ell", "mathrm", "mathit", "rm",
}


def _symbol_atoms(math_src: str) -> list[tuple[str, str]]:
    """Return (display, base) pairs: base is the letter or Greek name."""
    s = math_src.strip("$")
    s = re.sub(r"_\{[^}]*\}|_\\?[A-Za-z0-9]|\^\{[^}]*\}|\^\\?[A-Za-z0-9]", " ", s)  # sub/superscripts
    s = re.sub(r"\\(?:text|mathrm|operatorname)\{[^}]*\}", " ", s)
    s = re.sub(r"\\mathbb\{[A-Z]\}|\\mathcal\{O\}|\\pi(?![A-Za-z])", " ", s)  # standard sets, big-O, pi
    atoms = []
    for m in re.finditer(r"\\(hat|bar|tilde|mathbf|bm|boldsymbol|mathcal|vec)\{\\?([A-Za-z]+)\}|\\([A-Za-z]+)|(?<![A-Za-z\\])([A-Za-z])(?![A-Za-z])", s):
        if m.group(1):
            atoms.append((m.group(0), m.group(2)))
        elif m.group(3):
            if m.group(3) in _GREEK:
                atoms.append(("\\" + m.group(3), m.group(3)))
        elif m.group(4):
            atoms.append((m.group(4), m.group(4)))
    return atoms


_DEF_PATTERNS = (
    r"where\s+(?:\$[^$]*\$\s*(?:,|and)\s*)*\$?{sym}",
    r"{sym}\s*(?:,\s*)?(?:denotes|is defined as|stands for|represents|is the|are the|is a|is an|=)",
    r"\b(?:let|denote by|denoted by|we denote|define|defined as)\b[^.]*{sym}",
)


def check_symbols(sents: list[str], context: str) -> list[dict]:
    flags, seen = [], set()
    ctx = context
    for i, s in enumerate(sents):
        for mm in _MATH_RE.finditer(s):
            for display, base in _symbol_atoms(mm.group(0)):
                if display in seen:
                    continue
                seen.add(display)
                in_ctx = (
                    display in ctx
                    or re.search(r"(?<![A-Za-z])" + re.escape(base) + r"(?![a-z])", ctx) is not None
                    or (base in _GREEK and base.lower() in ctx.lower())
                )
                if in_ctx:
                    continue
                sym = re.escape(mm.group(0))
                window = " ".join(sents[i:i + 2])
                if any(re.search(p.format(sym=sym), window, re.I) for p in _DEF_PATTERNS):
                    continue
                if any(re.search(p.format(sym=re.escape(display)), window, re.I) for p in _DEF_PATTERNS):
                    continue
                flags.append(_item("symbol_undefined", i, sents, symbol=display))
    return flags


def check_style(prose: str, sents: list[str], fp: dict | None) -> list[dict]:
    flags = []
    n = max(len(tokens(prose)), 1)
    lower = _MATH_RE.sub(" ", prose).lower()
    base = (fp or {}).get("baseline", {}).get("filler", {})
    for marker in FILLER:
        hits = [i for i, s in enumerate(sents)
                if re.search(r"(?<![A-Za-z])" + re.escape(marker) + r"(?![A-Za-z])", _MATH_RE.sub(" ", s).lower())]
        count = len(re.findall(r"(?<![A-Za-z])" + re.escape(marker) + r"(?![A-Za-z])", lower))
        if not count:
            continue
        allowed = math.ceil(base.get(marker, 0.0) * n / 1000.0 * 1.5)
        if count > allowed:
            flags.append(_item("filler_above_author_rate", hits[0], sents, marker=marker, count=count,
                               allowed=allowed, author_rate_per_1k=base.get(marker, 0.0)))
    if fp is not None:
        dash = prose.count("\u2014")
        allowed = math.ceil(fp.get("baseline", {}).get("punctuation", {}).get("em_dash", 0.0) * n / 1000.0 * 1.5)
        if dash > allowed:
            idx = next((i for i, s in enumerate(sents) if "\u2014" in s), 0)
            flags.append(_item("em_dash_above_author_rate", idx, sents, count=dash, allowed=allowed))
        ref = fp.get("results") or fp.get("pooled") or {}
        sl = dict(ref.get("sentence_length") or {})
        if sl:
            sl.setdefault("p50", (sl.get("p25", 0) + sl.get("p75", 0)) / 2)
        if sl and sents:
            mine = _sentence_quantiles(sents)
            too_short = mine["p50"] < sl["p25"] or mine["p75"] < sl["p50"]
            too_long = mine["p50"] > sl["p75"] or mine["p25"] > sl["p50"]
            if too_short or too_long:
                flags.append(_item("sentence_length_off_profile", -1, sents, draft=mine,
                                   author={k: sl[k] for k in ("p25", "p50", "p75")},
                                   direction="short" if too_short else "long"))
    offset = 0
    for para in paragraphs(prose):
        if len(para) >= 2:
            last = para[-1].lower()
            if any(last.startswith(o) for o in FORMULAIC_CLOSER_OPENERS):
                flags.append(_item("formulaic_closer", offset + len(para) - 1, sents))
        offset += len(para)
    for i, s in enumerate(sents):
        if re.search(r"(?:[^,;]{1,60},\s*){3,}(?:and|or)\s", _MATH_RE.sub("M", s)):
            flags.append(_item("long_series", i, sents))
    return flags


def _sentence_quantiles(sents: list[str]) -> dict:
    lens = sorted(len(tokens(s)) for s in sents)

    def q(p: float) -> float:
        i = (len(lens) - 1) * p
        lo, hi = int(i), min(int(i) + 1, len(lens) - 1)
        return round(lens[lo] + (lens[hi] - lens[lo]) * (i - lo), 1)

    return {"p25": q(0.25), "p50": q(0.5), "p75": q(0.75)}


def voice_comparison(prose: str, fp: dict) -> dict:
    """Draft vs. author on measurable voice features. Information, not a target."""
    from fingerprint import stats as prose_stats

    mine = prose_stats(prose)
    ref = fp.get("results") or fp.get("pooled") or {}
    n_mine, n_ref = max(mine["sentences"], 1), max(ref.get("sentences", 0), 1)

    def share(openers: dict, n: int) -> dict:
        return {k: round(v / n, 2) for k, v in list(openers.items())[:6]}

    return {
        "sentence_length": {"draft": _sentence_quantiles(split_sentences(prose)) if mine["sentences"] else {},
                            "author": {k: ref.get("sentence_length", {}).get(k) for k in ("p25", "p50", "p75")}},
        "we_per_1k": {"draft": mine["we_rate"], "author": ref.get("we_rate")},
        "passive_per_1k": {"draft": mine["passive_rate"], "author": ref.get("passive_rate")},
        "parentheses_per_1k": {"draft": mine["punctuation"]["parenthesis"],
                               "author": ref.get("punctuation", {}).get("parenthesis")},
        "openers_share": {"draft": share(mine["openers"], n_mine), "author": share(ref.get("openers", {}), n_ref)},
    }


def check_claims(sents: list[str], claims: dict | None, notes: list[dict]) -> tuple[list[dict], list[dict]]:
    errors, flags = [], []
    ids = {n["id"] for n in notes}
    items = (claims or {}).get("claims", []) if isinstance(claims, dict) else (claims or [])
    linked = set()
    norm = [" ".join(s.lower().split()) for s in sents]
    for c in items:
        target = " ".join(to_prose(c.get("sentence", "")).lower().split())
        best = max(range(len(norm)), key=lambda k: difflib.SequenceMatcher(None, norm[k], target).ratio(), default=-1)
        if best >= 0 and difflib.SequenceMatcher(None, norm[best], target).ratio() >= 0.8:
            linked.add(best)
        for nid in c.get("notes", []):
            if nid not in ids:
                errors.append(_item("claim_unknown_note", best, sents, note=nid))
    for i, s in enumerate(sents):
        if i not in linked and _sentence_numbers(s):
            flags.append(_item("claim_unlinked_number", i, sents))
    return errors, flags


def check_paragraph_argument(prose: str, sents: list[str], claims: dict | None) -> list[dict]:
    """Reverse outline from claims.json: one finding per paragraph, none repeated, none missing.

    Adapted from the reverse-outline rule in huguryildiz/ieee-acm-paper-writing (MIT) and
    sciwrite's "lead with the finding" (CC BY 4.0, L. A. Barba).
    """
    items = (claims or {}).get("claims", []) if isinstance(claims, dict) else (claims or [])
    norm = [" ".join(s.lower().split()) for s in sents]
    notes_at: dict[int, set[str]] = {}
    for c in items:
        target = " ".join(to_prose(c.get("sentence", "")).lower().split())
        if not norm:
            break
        best = max(range(len(norm)), key=lambda k: difflib.SequenceMatcher(None, norm[k], target).ratio())
        if difflib.SequenceMatcher(None, norm[best], target).ratio() >= 0.8:
            notes_at.setdefault(best, set()).update(c.get("notes", []))
    flags, where, offset = [], {}, 0
    for p_idx, para in enumerate(paragraphs(prose)):
        idx = range(offset, offset + len(para))
        found = set().union(*(notes_at.get(i, set()) for i in idx))
        if len(para) >= 2 and not found:
            flags.append(_item("paragraph_no_finding", offset, sents, paragraph=p_idx))
        if len(found) > 2:
            flags.append(_item("paragraph_multi_finding", offset, sents, paragraph=p_idx, notes=sorted(found)))
        for n in found:
            where.setdefault(n, []).append(p_idx)
        offset += len(para)
    for note, paras in sorted(where.items()):
        if len(paras) > 1:
            flags.append(_item("finding_repeated", -1, sents, note=note, paragraphs=paras))
    return flags


_COMPARATIVE = re.compile(
    r"\b(?:improves?|improved|improvement|better|worse|reduc(?:es|ed|tion)|gains?|speedup|faster|slower)\b", re.I)
_CHANGE_SIZE = re.compile(r"\d+(?:\.\d+)?\s*(?:%|\\%|dB|times|×)|\bby a factor\b|\bfold\b", re.I)
_COMPARATOR = re.compile(
    r"\b(?:than|compared|relative to|with respect to|versus|vs\.?|against|from\b.*\bto\b|over|baseline|"
    r"without|instead of|in contrast|whereas|outperformed by)\b", re.I)


def check_comparators(sents: list[str]) -> list[dict]:
    """A sized change ("improves ... by 45%") must name what it is measured against,
    in that sentence or the previous one.

    Adapted from huguryildiz/ieee-acm-paper-writing (MIT), "keep the comparator".
    """
    flags = []
    for i, s in enumerate(sents):
        plain = _MATH_RE.sub(" ", s)
        if not (_COMPARATIVE.search(plain) and _CHANGE_SIZE.search(plain)):
            continue
        window = " ".join(_MATH_RE.sub(" ", t) for t in sents[max(0, i - 1): i + 1])
        if not _COMPARATOR.search(window):
            flags.append(_item("comparator_missing", i, sents))
    return flags


MODALS = ["may", "might", "can", "could", "possibly", "possible", "up to", "approximately", "about",
          "roughly", "around", "typically", "generally", "likely", "suggests", "potentially"]
CONDITIONS = ["when", "if", "provided", "as long as", "under", "in most", "unless"]
ABSOLUTES = ["only if", "always", "never", "guarantee", "guarantees", "guaranteed", "ensures", "necessarily",
             "must", "in all cases", "regardless"]
_STOP = set(FUNCTION_WORDS) | {w for m in MODALS + CONDITIONS for w in m.split()}


def _markers(text: str, words: list[str]) -> list[str]:
    low = _MATH_RE.sub(" ", text).lower()
    return [w for w in words if re.search(r"(?<![a-z])" + re.escape(w) + r"(?![a-z])", low)]


def _content(text: str) -> set[str]:
    return {w.lower() for w in tokens(_MATH_RE.sub(" ", text)) if len(w) > 2 and w.lower() not in _STOP}


def _closest(sentence: str, sources: list[str], floor: float = 0.3) -> str | None:
    """The single source sentence this sentence restates, by content-word overlap."""
    mine = _content(sentence)
    best, score = None, 0.0
    for src in sources:
        theirs = _content(src)
        if mine and theirs:
            s = len(mine & theirs) / len(mine | theirs)
            if s > score:
                best, score = src, s
    return best if score >= floor else None


def check_claim_strength(sents: list[str], sources: list[str], source_text: str) -> list[dict]:
    """No sentence may be stronger than the source sentence it restates.

    Every draft sentence (mapped in claims.json or not) is matched to its closest single
    source sentence; a dropped modal qualifier ("can", "up to") or condition ("when") is
    flagged separately. Absolutes ("only if", "always") absent from all sources are flagged
    anywhere.
    """
    flags = []
    for i, s in enumerate(sents):
        added = [w for w in _markers(s, ABSOLUTES) if w not in _markers(source_text, ABSOLUTES)]
        if added:
            flags.append(_item("claim_strength_raised", i, sents, reason="added: " + ", ".join(added)))
        src = _closest(s, sources)
        if src is None:
            continue
        for label, group in (("qualifier", MODALS), ("condition", CONDITIONS)):
            theirs = _markers(src, group)
            if theirs and not _markers(s, group) and not (label == "condition" and added):
                flags.append(_item("claim_strength_raised", i, sents,
                                   reason=f"{label} dropped: " + ", ".join(theirs), source=src))
    return flags


def check_openers(sents: list[str]) -> list[dict]:
    """Same two-word opener on 3+ sentences and at least a fifth of the section
    (rhythm; adapted from KalarisLabs unslop-academic-writing, MIT)."""
    from collections import Counter

    opens = Counter(" ".join(w.lower() for w in tokens(s)[:2]) for s in sents if len(tokens(s)) >= 2)
    return [_item("repeated_opener", -1, sents, opener=o, count=c) for o, c in opens.most_common()
            if c >= 3 and c >= 0.2 * len(sents)]


_KEY_CMD = re.compile(r"\\(ref|eqref|autoref|cref|Cref|pageref|cite|citep|citet)\*?\s*(?:\[[^\]]*\]\s*)?\{([^}]*)\}")


def check_references(section: str, packet_text: str) -> list[dict]:
    """\\ref/\\cite keys must come from the packet or a \\label in the section."""
    own = set(re.findall(r"\\label\s*\{([^}]*)\}", section))
    errors, seen = [], set()
    for m in _KEY_CMD.finditer(section):
        for key in (k.strip() for k in m.group(2).split(",")):
            if not key or key in own or key in seen or key in packet_text:
                continue
            seen.add(key)
            errors.append({"kind": "reference_key_unknown", "sentence_index": -1,
                           "sentence": m.group(0), "detail": {"key": key, "command": m.group(1)}})
    return errors


def _packet_text(packet: Path) -> str:
    parts = [p.read_text(errors="replace") for p in sorted(packet.glob("*")) if p.is_file() and p.suffix in (".md", ".json", ".tex", ".txt")]
    tables = packet / "tables"
    if tables.is_dir():
        parts += [p.read_text(errors="replace") for p in sorted(tables.iterdir()) if p.is_file()]
    return "\n".join(parts)


def _keys(latex: str) -> list[str]:
    out = []
    for m in _KEY_CMD.finditer(latex):
        out += [k.strip() for k in m.group(2).split(",") if k.strip()]
    return list(dict.fromkeys(out))


def check_preserved(section: str, sents: list[str], original: str) -> list[dict]:
    """Revision mode: numbers and references of the original that the revision lost."""
    flags = []
    mine = [n for s in sents for n in _sentence_numbers(s)]
    mine_ev = [{**n, "precision": "exact"} for n in mine]
    seen = set()
    for s in split_sentences(to_prose(original)):
        for num in _sentence_numbers(s):
            key = (num["text"], num["unit"])
            if key in seen:
                continue
            seen.add(key)
            if _match_number(num, mine_ev) == "unsupported":
                flags.append({"kind": "number_dropped", "sentence_index": -1, "sentence": s,
                              "detail": {"value": num["text"], "unit": num["unit"]}})
    kept = set(_keys(section))
    for key in _keys(original):
        if key not in kept:
            flags.append({"kind": "reference_dropped", "sentence_index": -1, "sentence": "",
                          "detail": {"key": key}})
    return flags


_EMPTY_PACKET = {"notes": [], "context": "", "evidence": [], "meta": None, "captions": {}}


def check(section: str, packet: Path | None, profile: Path | None, claims: dict | None = None,
          original: str | None = None, context: str = "", evidence: str = "") -> dict:
    """Draft mode: packet given. Revision mode: original given (packet optional).

    `evidence` is extra raw text (e.g. the whole manuscript) whose numbers, including
    table cells, count as support; it is not treated as already-read context.
    """
    prose = to_prose(section)
    sents = split_sentences(prose)
    pk = load_packet(packet) if packet is not None else dict(_EMPTY_PACKET)
    packet_text = _packet_text(packet) if packet is not None else ""
    if original is not None:
        # raw LaTeX too, so values in the original's tables count (units sit in headers)
        pk["evidence"] = pk["evidence"] + [{**n, "precision": "exact", "source": "original"}
                                           for n in _num_items(to_prose(original) + "\n" + original)]
        packet_text += "\n" + original
    if evidence:
        pk["evidence"] = pk["evidence"] + [{**n, "precision": "exact", "source": "evidence"}
                                           for n in _num_items(evidence)]
        packet_text += "\n" + evidence
    if context:
        pk["context"] = pk["context"] + "\n" + to_prose(context)
        packet_text += "\n" + context
    fp = None
    skipped = []
    if profile is not None and (profile / "fingerprint.json").is_file():
        fp = json.loads((profile / "fingerprint.json").read_text())
    elif profile is not None:
        skipped.append("profile")
    errors: list[dict] = []
    flags: list[dict] = []
    errors += check_references(section, packet_text)
    if original is not None:
        flags += check_preserved(section, sents, original)
    errors += check_acronyms(sents, pk["context"])
    e, f = check_numbers(sents, pk["evidence"])
    errors += e
    flags += f
    flags += check_symbols(sents, pk["context"])
    flags += check_figure_conditions(sents, pk["captions"])
    flags += check_distributions(sents)
    flags += check_comparators(sents)
    flags += check_openers(sents)
    flags += check_style(prose, sents, fp)
    sources = [t for n in pk["notes"] for t in split_sentences(n["text"])]
    sources += [t for line in pk["context"].splitlines() for t in split_sentences(line.lstrip("- "))]
    if original is not None:
        sources += split_sentences(to_prose(original))
    source_text = " ".join(sources) + " " + to_prose(packet_text)
    if sources:
        flags += check_claim_strength(sents, sources, source_text)
    if claims is None:
        skipped.append("claims")
    else:
        e, f = check_claims(sents, claims, pk["notes"])
        errors += e
        flags += f
        flags += check_paragraph_argument(prose, sents, claims)
    words = len(tokens(prose))
    meta = pk["meta"] or {}
    if "length_words" in meta:
        lo, hi = meta["length_words"]
    elif "target_words" in meta:
        lo, hi = math.floor(meta["target_words"] * 0.85), math.ceil(meta["target_words"] * 1.15)
    else:
        lo = hi = None
        skipped.append("length")
    if lo is not None and not lo <= words <= hi:
        errors.append(_item("length_out_of_bounds", -1, sents, words=words, bounds=[lo, hi]))
    if not pk["notes"] and original is None:
        skipped.append("results_notes")
    report = {
        "errors": errors,
        "flags": flags,
        "skipped": skipped,
        "stats": {"words": words, "sentences": len(sents), "errors": len(errors), "flags": len(flags)},
    }
    if fp is not None and sents:
        report["voice"] = voice_comparison(prose, fp)
    return report


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--section", required=True, type=Path)
    ap.add_argument("--packet", type=Path)
    ap.add_argument("--original", type=Path, help="revision mode: the section before revision")
    ap.add_argument("--context", type=Path, help="text the reader has already seen (earlier sections)")
    ap.add_argument("--evidence", type=Path, nargs="*", default=[],
                    help="extra sources whose numbers count as support, e.g. the whole manuscript")
    ap.add_argument("--profile", required=True)
    ap.add_argument("--claims", type=Path)
    args = ap.parse_args(argv)
    if args.packet is None and args.original is None:
        ap.error("give --packet (drafting) or --original (revision), or both")
    profile = None if args.profile == "none" else Path(args.profile)
    claims_path = args.claims or args.section.parent / "claims.json"
    claims = json.loads(claims_path.read_text()) if claims_path.is_file() else None
    report = check(args.section.read_text(), args.packet, profile, claims,
                   original=args.original.read_text() if args.original else None,
                   context=args.context.read_text() if args.context else "",
                   evidence="\n".join(p.read_text(errors="replace") for p in args.evidence))
    print(json.dumps(report, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

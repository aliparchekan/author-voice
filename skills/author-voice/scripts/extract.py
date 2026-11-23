#!/usr/bin/env python3
"""Extract sections and plain prose from a paper's LaTeX source or PDF.

Usage: extract.py PAPER_DIR
  PAPER_DIR holds either latex/*.tex (the main file has \\begin{document})
  or paper.pdf, document.txt, document.md or document.docx. Writes PAPER_DIR/sections.json.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from xml.etree import ElementTree
from zipfile import ZipFile
from pathlib import Path

# ------------------------------------------------------------------ LaTeX ---


def strip_comments(text: str) -> str:
    out = []
    for line in text.split("\n"):
        i = 0
        while True:
            j = line.find("%", i)
            if j < 0:
                break
            k = j - 1
            slashes = 0
            while k >= 0 and line[k] == "\\":
                slashes += 1
                k -= 1
            if slashes % 2 == 0:
                line = line[:j]
                break
            i = j + 1
        out.append(line)
    return "\n".join(out)


def _read(path: Path) -> str:
    raw = path.read_bytes()
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


_INPUT_RE = re.compile(r"\\(?:input|include)\s*\{([^}]+)\}")


def load_latex(main: Path) -> str:
    """Return the full source with comments stripped and \\input resolved."""

    def resolve(path: Path, depth: int) -> str:
        text = strip_comments(_read(path))
        if depth > 8:
            return text

        def sub(m: re.Match) -> str:
            name = m.group(1).strip()
            cand = main.parent / name
            if not cand.suffix:
                cand = cand.with_suffix(".tex")
            if cand.resolve().is_relative_to(main.parent.resolve()) and cand.is_file():
                return resolve(cand, depth + 1)
            return ""

        return _INPUT_RE.sub(sub, text)

    return resolve(main, 0)


def document_body(full: str) -> str:
    start = full.find("\\begin{document}")
    body = full[start + len("\\begin{document}"):] if start >= 0 else full
    end = body.find("\\end{document}")
    return body[:end] if end >= 0 else body


def _brace_arg(text: str, i: int) -> tuple[str, int] | None:
    """If text[i:] starts (after spaces) with {..}, return (content, end)."""
    n = len(text)
    while i < n and text[i] in " \t":
        i += 1
    if i >= n or text[i] != "{":
        return None
    depth = 0
    for j in range(i, n):
        c = text[j]
        if c == "\\":
            continue
        if c == "{" and (j == 0 or text[j - 1] != "\\"):
            depth += 1
        elif c == "}" and text[j - 1] != "\\":
            depth -= 1
            if depth == 0:
                return text[i + 1 : j], j + 1
    return None


def _opt_arg(text: str, i: int) -> tuple[str, int] | None:
    n = len(text)
    while i < n and text[i] in " \t":
        i += 1
    if i < n and text[i] == "[":
        j = text.find("]", i)
        if j > 0:
            return text[i + 1 : j], j + 1
    return None


_ACRODEF_RE = re.compile(r"\\(?:acrodef|acro|newacro)\s*\{([^}]*)\}\s*(?:\[([^\]]*)\])?\s*\{")


def _acronym_table(full: str) -> dict[str, tuple[str, str]]:
    table: dict[str, tuple[str, str]] = {}
    for m in _ACRODEF_RE.finditer(full):
        key, short = m.group(1).strip(), (m.group(2) or m.group(1)).strip()
        arg = _brace_arg(full, m.end() - 1)
        if arg:
            table[key] = (short, arg[0].strip())
    return table


_AC_RE = re.compile(r"\\(acp|acs|acsp|acl|aclp|acf|acfp|ac|acused|acronymused)\*?\s*\{([^}]*)\}")


def expand_acronyms(body: str, full: str) -> str:
    """Expand acronym-package macros in reading order (first use is full)."""
    table = _acronym_table(full)
    used: set[str] = set()

    def sub(m: re.Match) -> str:
        cmd, key = m.group(1), m.group(2).strip()
        short, long = table.get(key, (key.upper(), key))
        if cmd in ("acused", "acronymused"):
            used.add(key)
            return ""
        plural = cmd.endswith("p")
        s, l_ = (short + "s", long + "s") if plural else (short, long)
        if cmd in ("acs", "acsp"):
            used.add(key)
            return s
        if cmd in ("acl", "aclp"):
            return l_
        if cmd in ("acf", "acfp") or key not in used:
            used.add(key)
            return f"{l_} ({s})"
        return s

    return _AC_RE.sub(sub, body)


_SEC_RE = re.compile(r"\\(section|subsection|subsubsection)\*?\s*(?=\{)")
_LEVEL = {"section": 1, "subsection": 2, "subsubsection": 3}
_BIB_RE = re.compile(r"\\bibliography\s*\{|\\begin\{thebibliography\}|\\bibliographystyle\s*\{")


def latex_sections(body: str) -> list[dict]:
    bib = _BIB_RE.search(body)
    if bib:
        body = body[: bib.start()]
    sections: list[dict] = []
    am = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", body, re.S)
    if am:
        sections.append({"title": "Abstract", "level": 0, "latex": am.group(1)})
    marks = []
    for m in _SEC_RE.finditer(body):
        arg = _brace_arg(body, m.end())
        if not arg:
            continue
        title = " ".join(to_prose(arg[0]).split())
        marks.append((m.start(), arg[1], _LEVEL[m.group(1)], title))
    for idx, (_, content_start, level, title) in enumerate(marks):
        end = marks[idx + 1][0] if idx + 1 < len(marks) else len(body)
        sections.append({"title": title, "level": level, "latex": body[content_start:end]})
    return sections


_DROP_ENVS = (
    "figure", "figure*", "table", "table*", "algorithm", "algorithm*",
    "tikzpicture", "IEEEbiography", "acronym",
)
_MATH_ENVS = (
    "equation", "equation*", "align", "align*", "multline", "multline*",
    "gather", "gather*", "eqnarray", "eqnarray*", "subequations", "IEEEeqnarray",
    "IEEEeqnarray*", "displaymath",
)
_UNWRAP = (
    "emph", "textit", "textbf", "textrm", "textsf", "texttt", "textsc", "mbox",
    "text", "underline", "textnormal", "IEEEPARstart",
)
_DROP_WITH_ARG = (
    "label", "footnote", "thanks", "vspace", "vspace*", "hspace", "hspace*",
    "caption", "includegraphics", "bibliographystyle", "IEEEauthorrefmark",
    "todo", "color",
)


def _remove_env(text: str, env: str, repl: str) -> str:
    pat = re.compile(r"\\begin\{" + re.escape(env) + r"\}.*?\\end\{" + re.escape(env) + r"\}", re.S)
    return pat.sub(repl, text)


def _sub_cmd_with_arg(text: str, name: str, fn) -> str:
    pat = re.compile(r"\\" + re.escape(name) + r"(?![A-Za-z])\*?")
    out, i = [], 0
    while True:
        m = pat.search(text, i)
        if not m:
            out.append(text[i:])
            return "".join(out)
        j = m.end()
        opt = _opt_arg(text, j)
        if opt:
            j = opt[1]
        arg = _brace_arg(text, j)
        if not arg:
            out.append(text[i : m.end()])
            i = m.end()
            continue
        out.append(text[i : m.start()])
        out.append(fn(arg[0]))
        i = arg[1]


def to_prose(latex: str) -> str:
    t = latex
    for env in _DROP_ENVS:
        t = _remove_env(t, env, " ")
    for env in _MATH_ENVS:
        t = _remove_env(t, env, " EQN ")
    t = re.sub(r"\\\[.*?\\\]", " EQN ", t, flags=re.S)
    t = re.sub(r"\$\$.*?\$\$", " EQN ", t, flags=re.S)
    t = re.sub(r"\\\((.*?)\\\)", r"$\1$", t, flags=re.S)
    t = re.sub(r"\\begin\{(?:itemize|enumerate|description)\}(?:\[[^\]]*\])?|\\end\{(?:itemize|enumerate|description)\}", "\n", t)
    t = re.sub(r"\\item(?:\[[^\]]*\])?", "\n", t)
    t = re.sub(r"\\(?:begin|end)\{[A-Za-z*]+\}(?:\[[^\]]*\])?", " ", t)
    # protect inline math from macro stripping
    maths: list[str] = []

    def keep_math(m: re.Match) -> str:
        maths.append(m.group(0))
        return f"\x00{len(maths) - 1}\x00"

    t = re.sub(r"(?<!\\)\$[^$]+?(?<!\\)\$", keep_math, t, flags=re.S)
    for name in _DROP_WITH_ARG:
        t = _sub_cmd_with_arg(t, name, lambda a: "")
    t = _sub_cmd_with_arg(t, "cite", lambda a: "[1]")
    t = _sub_cmd_with_arg(t, "citep", lambda a: "[1]")
    t = _sub_cmd_with_arg(t, "eqref", lambda a: "(1)")
    t = _sub_cmd_with_arg(t, "ref", lambda a: "1")
    t = _sub_cmd_with_arg(t, "url", lambda a: "URL")
    for name in _UNWRAP:
        t = _sub_cmd_with_arg(t, name, lambda a: a)
    t = t.replace("\\%", "%").replace("\\&", "&").replace("\\_", "_").replace("\\#", "#")
    t = t.replace("---", "\u2014").replace("--", "\u2013")
    t = t.replace("``", '"').replace("''", '"')
    t = t.replace("~", " ").replace("\\\\", " ").replace("\\,", " ").replace("\\ ", " ")
    t = re.sub(r"\\[A-Za-z]+\*?", " ", t)  # remaining argument-less commands
    t = t.replace("{", "").replace("}", "")
    t = re.sub(r"\x00(\d+)\x00", lambda m: maths[int(m.group(1))], t)
    paras = [" ".join(p.split()) for p in re.split(r"\n\s*\n", t)]
    paras = [re.sub(r"\s+([.,;:)])", r"\1", p) for p in paras if p]
    return "\n\n".join(paras)


# -------------------------------------------------------------------- PDF ---

_ROMAN = re.compile(r"^([IVX]+)\.\s+(.+)$")
_SUB = re.compile(r"^([A-H])\.\s+([A-Z][A-Za-z\- ,:()]{2,60})$")


def _fix_small_caps(s: str) -> str:
    s = re.sub(r"\b([A-Z]) (?=[A-Z]{2,})", r"\1", s)
    return " ".join(w if len(w) <= 3 and w.isupper() and w in {"UWB", "LOS", "GPS"} else w.capitalize()
                    if w.isupper() else w for w in s.split())


def parse_pdf_heading(line: str) -> tuple[int, str] | None:
    line = line.strip()
    m = _ROMAN.match(line)
    if m:
        rest = m.group(2)
        letters = [c for c in rest if c.isalpha()]
        if letters and sum(c.isupper() for c in letters) / len(letters) > 0.8 and len(rest) < 70:
            title = _fix_small_caps(rest)
            small = {"And", "Of", "The", "For", "With", "In", "To", "On"}
            words = title.split()
            title = " ".join(w if i == 0 or w not in small else w.lower() for i, w in enumerate(words))
            return 1, title
        return None
    m = _SUB.match(line)
    if m and not line.endswith(".") and len(line.split()) <= 8:
        return 2, m.group(2).strip()
    return None


_STOP = re.compile(r"^(?:[IVX]+\.\s+)?(?:R\s?EFERENCES|A\s?CKNOWLEDGE?MENTS?)$")


def pdf_text_sections(text: str) -> list[dict]:
    text = re.sub(r"-\n(?=[a-z])", "", text)
    lines = text.split("\n")
    sections: list[dict] = []
    cur: dict | None = None
    in_abstract = False
    in_caption = False
    for raw in lines:
        line = raw.strip()
        if _STOP.match(line):
            break
        if in_caption:
            in_caption = bool(line)
            continue
        if re.match(r"^(Figure|Fig\.|TABLE|Table)\s+[\dIVX]+[.:]", line):
            in_caption = True
            continue
        words = re.findall(r"[A-Za-z]{2,}", line)
        if line and len(words) < 2 and len(line) < 25 and not _ROMAN.match(line) and not _SUB.match(line):
            continue  # plot-axis residue, page numbers, stray symbols
        if line.startswith("Abstract"):
            cur = {"title": "Abstract", "level": 0, "lines": [re.sub(r"^Abstract\W*", "", line)]}
            sections.append(cur)
            in_abstract = True
            continue
        if in_abstract and line.startswith("Index Terms"):
            in_abstract = False
            cur = None
            continue
        h = parse_pdf_heading(line)
        if h:
            in_abstract = False
            cur = {"title": h[1], "level": h[0], "lines": []}
            sections.append(cur)
            continue
        if cur is not None and not re.fullmatch(r"\d{1,3}", line):
            cur["lines"].append(line)
    out = []
    for s in sections:
        body = "\n".join(s["lines"])
        body = re.sub(r"(?<!\n)\n(?!\n)", " ", body)
        out.append({"title": s["title"], "level": s["level"], "latex": body.strip()})
    return out


def pdf_sections(pdf: Path) -> list[dict]:
    txt = subprocess.run(["pdftotext", str(pdf), "-"], capture_output=True, text=True, check=True).stdout
    return pdf_text_sections(txt) or text_sections(txt)


def text_sections(text: str) -> list[dict]:
    sections = []
    title, level, lines = "Writing sample", 1, []
    def finish_section():
        body = "\n".join(lines).strip()
        if body:
            sections.append({"title": title, "level": level, "latex": body, "prose": body})

    for line in text.splitlines():
        heading = re.fullmatch(r"(#{1,6})[ \t]+(.*)", line)
        if heading is None:
            lines.append(line)
            continue
        finish_section()
        title, level, lines = heading[2], len(heading[1]), []
    finish_section()
    return sections


def docx_text(path: Path) -> str:
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    with ZipFile(path) as doc:
        root = ElementTree.fromstring(doc.read("word/document.xml"))
    return "\n\n".join(
        "".join(t.text or "" for t in paragraph.findall(".//w:t", ns))
        for paragraph in root.findall(".//w:body//w:p", ns)
    )


# -------------------------------------------------------------------- CLI ---


def find_main(latex_dir: Path) -> Path | None:
    for tex in sorted(latex_dir.glob("*.tex")):
        if "\\begin{document}" in strip_comments(_read(tex)):
            return tex
    return None


def extract_paper(paper_dir: Path) -> dict:
    main = find_main(paper_dir / "latex") if (paper_dir / "latex").is_dir() else None
    if main:
        full = load_latex(main)
        body = expand_acronyms(document_body(full), full)
        secs = latex_sections(body) or [{"title": "Writing sample", "level": 1, "latex": body}]
        fmt = "latex"
        for s in secs:
            s["prose"] = to_prose(s["latex"])
    elif (paper_dir / "paper.pdf").is_file():
        secs = pdf_sections(paper_dir / "paper.pdf")
        fmt = "pdf"
        for s in secs:
            s["prose"] = s["latex"]
    else:
        source = next((paper_dir / name for name in ("document.md", "document.txt", "document.docx")
                       if (paper_dir / name).is_file()), None)
        if source is None:
            raise SystemExit(f"{paper_dir}: supply latex/*.tex, paper.pdf, document.md, document.txt or document.docx")
        secs = text_sections(docx_text(source) if source.suffix == ".docx" else _read(source))
        fmt = "text"
    return {"paper": paper_dir.name, "format": fmt, "sections": secs}


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    paper_dir = Path(argv[0])
    data = extract_paper(paper_dir)
    (paper_dir / "sections.json").write_text(json.dumps(data, indent=1, ensure_ascii=False))
    for s in data["sections"]:
        print(f"{'  ' * s['level']}{s['title']}  ({len(s['prose'].split())} words)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

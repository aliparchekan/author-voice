#!/usr/bin/env python3
"""Find an author's papers on arXiv written before a cutoff.

Usage: collect.py --author "First Last" --out DIR [--cutoff 2024-01-01]
                  [--positions sole first] [--exclude ID ...] [--download]

Keeps papers whose first public version (arXiv v1) is strictly before the
cutoff and where the author holds one of the given positions. Writes
DIR/<id>/meta.json for each and prints a table. With --download it also
fetches the LaTeX e-print into DIR/<id>/latex/ (or DIR/<id>/paper.pdf when
arXiv only has a PDF). Never run this inside a sealed writing session.

Papers not on arXiv (journal copies, repository PDFs) are added by hand:
DIR/<id>/paper.pdf or DIR/<id>/latex/*.tex plus a meta.json that states how
the date was established ("date_basis").
"""
from __future__ import annotations

import argparse
import gzip
import io
import json
import ssl
import sys
import tarfile
import tempfile
import time
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import date

from sources import CUTOFF

API = "https://export.arxiv.org/api/query"
NS = {"a": "http://www.w3.org/2005/Atom", "x": "http://arxiv.org/schemas/atom",
      "o": "http://a9.com/-/spec/opensearch/1.1/"}
USER_AGENT = "author-voice-collect/0.1"


def _fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)).lower()


def same_person(a: str, b: str) -> bool:
    """Same surname and same first initial, ignoring accents and case."""
    pa, pb = _fold(a).replace(".", " ").split(), _fold(b).replace(".", " ").split()
    if not pa or not pb:
        return False
    return pa[-1] == pb[-1] and pa[0][0] == pb[0][0]


def _position(authors: list[str], author: str) -> str | None:
    hits = [i for i, name in enumerate(authors) if same_person(name, author)]
    if not hits:
        return None
    i = hits[0]
    if len(authors) == 1:
        return "sole"
    if i == 0:
        return "first"
    if i == len(authors) - 1:
        return "last"
    return "middle"


def parse_atom(xml: str, author: str) -> list[dict]:
    root = ET.fromstring(xml)
    out = []
    for e in root.findall("a:entry", NS):
        raw_id = e.find("a:id", NS).text.rsplit("/abs/", 1)[-1]
        pid = raw_id.rsplit("v", 1)[0] if "v" in raw_id.split("/")[-1] else raw_id
        authors = [a.find("a:name", NS).text.strip() for a in e.findall("a:author", NS)]
        cat = e.find("x:primary_category", NS)
        comment = e.find("x:comment", NS)
        out.append({
            "id": pid,
            "title": " ".join(e.find("a:title", NS).text.split()),
            "authors": authors,
            "n_authors": len(authors),
            "author_position": _position(authors, author),
            "first_version_date": e.find("a:published", NS).text[:10],
            "date_basis": "arXiv v1 submission date",
            "url": f"https://arxiv.org/abs/{pid}",
            "primary_category": cat.attrib.get("term") if cat is not None else None,
            "comment": " ".join(comment.text.split()) if comment is not None and comment.text else "",
        })
    return out


def select(entries: list[dict], cutoff: str = CUTOFF.isoformat(),
           positions: tuple[str, ...] = ("sole", "first"), exclude: tuple[str, ...] = ()) -> list[dict]:
    return [e for e in entries
            if e["first_version_date"] < cutoff and e["author_position"] in positions and e["id"] not in exclude]


def _tls_context() -> ssl.SSLContext:
    """Verified TLS even where Python ships without CA certificates."""
    ctx = ssl.create_default_context()
    try:
        import certifi

        ctx.load_verify_locations(certifi.where())
    except ImportError:
        for bundle in ("/etc/ssl/cert.pem", "/etc/ssl/certs/ca-certificates.crt"):
            if Path(bundle).is_file():
                ctx.load_verify_locations(bundle)
                break
    return ctx


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60, context=_tls_context()) as r:
        return r.read()


def fetch_entries(author: str, page: int = 200) -> list[dict]:
    surname = _fold(author).split()[-1]
    entries, start, total = [], 0, None
    while total is None or start < total:
        q = urllib.parse.urlencode({"search_query": f"au:{surname}", "start": start, "max_results": page,
                                    "sortBy": "submittedDate", "sortOrder": "ascending"})
        xml = _get(f"{API}?{q}").decode("utf-8")
        root = ET.fromstring(xml)
        total = int(root.find("o:totalResults", NS).text)
        batch = parse_atom(xml, author)
        if not batch:
            break
        entries += [e for e in batch if e["author_position"]]
        start += page
        time.sleep(3)  # arXiv API etiquette
    return entries


def safe_name(name: str) -> bool:
    p = Path(name)
    return not p.is_absolute() and ".." not in p.parts


def download(entry: dict, paper_dir: Path) -> str:
    data = _get(f"https://arxiv.org/e-print/{entry['id']}v1")
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as tar:
            members = [m for m in tar.getmembers() if (m.isfile() or m.isdir()) and safe_name(m.name)]
            (paper_dir / "latex").mkdir(parents=True, exist_ok=True)
            tar.extractall(paper_dir / "latex", members=members, filter="data")
            return "latex"
    except tarfile.TarError:
        pass
    if data[:4] == b"%PDF":
        (paper_dir / "paper.pdf").write_bytes(data)
        return "pdf"
    try:
        tex = gzip.decompress(data)
    except OSError:
        tex = data
    (paper_dir / "latex").mkdir(parents=True, exist_ok=True)
    (paper_dir / "latex" / "main.tex").write_bytes(tex)
    return "latex"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--author", required=True)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--cutoff", type=date.fromisoformat, default=CUTOFF, help="Exclusive upper bound for paper discovery")
    ap.add_argument("--positions", nargs="+", default=["sole", "first"])
    ap.add_argument("--exclude", nargs="*", default=[])
    ap.add_argument("--download", action="store_true")
    args = ap.parse_args(argv)
    if args.cutoff > CUTOFF:
        ap.error("For later papers, supply the copy the author confirms was written without AI.")
    entries = fetch_entries(args.author)
    chosen = select(entries, args.cutoff.isoformat(), tuple(args.positions), tuple(args.exclude))
    print(f"{len(entries)} arXiv papers list {args.author}; "
          f"{len(chosen)} are {'/'.join(args.positions)}-author before {args.cutoff}")
    for e in chosen:
        d = args.out / e["id"].replace("/", "_")
        d.mkdir(parents=True, exist_ok=True)
        if (d / "latex").exists() or (d / "paper.pdf").exists() or (d / "sections.json").exists():
            print(f"Keeping existing source {d}. Use a new output folder to collect v1.", file=sys.stderr)
            continue
        e["tentative"] = e["n_authors"] > 4
        e.update(source_kind="paper", source_version="v1", source_version_date=e["first_version_date"])
        kind = "-"
        if args.download:
            with tempfile.TemporaryDirectory(dir=d) as tmp:
                staging = Path(tmp)
                kind = download(e, staging)
                filename = "latex" if kind == "latex" else "paper.pdf"
                (staging / filename).rename(d / filename)
        (d / "meta.json").write_text(json.dumps(e, indent=1, ensure_ascii=False))
        print(f"{e['id']:12s} {e['first_version_date']} {e['author_position']:5s} n={e['n_authors']:<3d} {kind:5s} {e['title'][:70]}")
        if args.download:
            time.sleep(3)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

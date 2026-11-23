"""Release tests for the public skill's source policy and profile entry points."""

# ruff: noqa: E402
# Import the standalone scripts from the release layout exercised by agents.
from pathlib import Path
import json
import sys
from zipfile import ZipFile

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "author-voice" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import collect
import extract
import fingerprint
import long_exemplars
from sources import eligibility


def paper(date):
    return {
        "source_kind": "paper",
        "source_version_date": date,
        "date_basis": "publication record",
    }


@pytest.mark.parametrize(
    ("meta", "eligible"),
    [
        (paper("2023-12-31"), True),
        (paper("2023"), True),
        (paper("2024-01-01"), False),
        (dict(paper("2025-01-01"), first_version_date="2020-06-03"), False),
        (dict(paper("2024-01-01"), written_without_ai=True), True),
        ({"source_kind": "document", "written_without_ai": True}, True),
        ({"source_kind": "document", "written_without_ai": "false"}, False),
        (dict(paper("2022-02-02"), source_kind="document"), False),
        (paper("2023-02-30"), False),
        ({}, False),
    ],
)
def test_eligibility(meta, eligible):
    assert bool(eligibility(meta)) == eligible


def test_collect_downloads_the_version_whose_date_was_checked(tmp_path, monkeypatch):
    entry = dict(
        id="2312.12345",
        first_version_date="2023-12-31",
        author_position="first",
        date_basis="arXiv v1 submission date",
        n_authors=2,
        title="Example",
    )
    late = dict(entry, id="2401.12345", first_version_date="2024-01-01")
    calls = []
    monkeypatch.setattr(collect, "fetch_entries", lambda _: [entry, late])

    def fetch(url):
        calls.append(url)
        return (
            b"\\documentclass{article}\\begin{document}A dated sample.\\end{document}"
        )

    monkeypatch.setattr(collect, "_get", fetch)
    monkeypatch.setattr(collect.time, "sleep", lambda _: None)
    assert (
        collect.main(["--out", str(tmp_path), "--author", "Example", "--download"]) == 0
    )
    assert calls == ["https://arxiv.org/e-print/2312.12345v1"]
    meta = json.loads((tmp_path / "2312.12345/meta.json").read_text())
    assert eligibility(meta) == "paper before 2024"
    assert meta["source_version"] == "v1"
    assert not (tmp_path / "2401.12345").exists()


def test_profile_stages_share_only_eligible_inputs(tmp_path):
    root = tmp_path / "samples"
    for name, meta in {
        "paper": paper("2023-12-31"),
        "chapter": {"source_kind": "document", "written_without_ai": True},
        "later-unconfirmed": paper("2024-01-01"),
        "unspecified": {},
        "held-out": paper("2023-04-01"),
    }.items():
        d = root / name
        d.mkdir(parents=True)
        (d / "meta.json").write_text(json.dumps(meta))
        (d / "document.md").write_text(
            "# Results\n" + "We saw a 10% increase in Fig. 2. " * 24
        )
        assert extract.main([str(d)]) == 0
    args = ["--papers", str(root), "--exclude", "held-out", "--out"]
    assert fingerprint.main([*args, str(tmp_path / "fp.json")]) == 0
    fp = json.loads((tmp_path / "fp.json").read_text())
    assert fp["papers"] == ["chapter", "paper"]
    assert long_exemplars.main([*args, str(tmp_path / "long.md")]) == 0
    examples = (tmp_path / "long.md").read_text()
    assert (
        "## chapter" in examples
        and "## paper" in examples
        and "## later" not in examples
    )
    assert "10% increase in Fig. N" in examples


def test_word_document_without_a_paper_or_results_section(tmp_path):
    text = '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>My first paragraph.</w:t></w:r></w:p><w:p><w:r><w:t>My second paragraph.</w:t></w:r></w:p></w:body></w:document>'
    d = tmp_path / "chapter"
    d.mkdir()
    with ZipFile(d / "document.docx", "w") as z:
        z.writestr("word/document.xml", text)
    (d / "meta.json").write_text('{"source_kind":"document","written_without_ai":true}')
    assert extract.main([str(d)]) == 0
    result = json.loads((d / "sections.json").read_text())
    assert (
        result["sections"][0]["prose"] == "My first paragraph.\n\nMy second paragraph."
    )
    assert (
        fingerprint.main(
            ["--papers", str(tmp_path), "--out", str(tmp_path / "fp.json")]
        )
        == 0
    )
    fp = json.loads((tmp_path / "fp.json").read_text())
    assert fp["pooled"]["sentences"] == 2 and "results" not in fp
    assert (
        long_exemplars.main(
            ["--papers", str(tmp_path), "--out", str(tmp_path / "long.md")]
        )
        == 0
    )
    assert "short examples" in (tmp_path / "long.md").read_text()

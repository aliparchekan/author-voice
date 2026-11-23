"""Select writing samples for the profile. Extraction for manuscript revision is independent."""

from datetime import date
import json
from pathlib import Path
import sys


CUTOFF = date(2024, 1, 1)


def eligibility(meta: dict) -> str | None:
    if meta.get("written_without_ai") is True:
        return "author-confirmed writing without AI"
    # Older arXiv and journal manifests identified papers by author position.
    kind = meta.get("source_kind")
    if kind != "paper" and not (kind is None and meta.get("author_position")):
        return None
    stamp = meta.get("source_version_date", meta.get("first_version_date"))
    if not isinstance(stamp, str) or not meta.get("date_basis"):
        return None
    if len(stamp) == 4 and stamp.isascii() and stamp.isdigit():
        stamp += "-12-31"  # The whole recorded year precedes the January cutoff.
    try:
        before_cutoff = date.fromisoformat(stamp) < CUTOFF
    except ValueError:
        return None
    return "paper before 2024" if before_cutoff else None


def profile_sources(root: Path, exclude: list[str]):
    for sections in sorted(root.glob("*/sections.json")):
        if sections.parent.name in exclude:
            continue
        manifest = sections.parent / "meta.json"
        meta = json.loads(manifest.read_text()) if manifest.is_file() else {}
        if not isinstance(meta, dict):
            raise ValueError(f"{manifest}: expected a metadata object")
        reason = eligibility(meta)
        if reason:
            yield sections, meta, reason
        else:
            print(
                f"Skipped {sections.parent.name}: needs a dated pre-2024 paper "
                "or confirmation that the author wrote this text without AI.",
                file=sys.stderr,
            )

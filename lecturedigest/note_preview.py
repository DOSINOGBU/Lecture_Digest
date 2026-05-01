from __future__ import annotations

import re
from pathlib import Path

from lecturedigest.models import LectureRecord

SAFE_FILENAME_PATTERN = re.compile(r"[^A-Za-z0-9_.-]+")


def export_note_previews(
    record: LectureRecord,
    output_dir: Path,
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for index, candidate in enumerate(record.note_candidates, start=1):
        candidate_id = str(candidate.get("candidate_id") or f"candidate-{index:02d}")
        markdown = str(candidate.get("markdown") or "").strip()
        path = output_dir / f"{index:02d}-{_safe_filename(candidate_id)}.md"
        path.write_text(markdown + "\n", encoding="utf-8")
        paths.append(path)
    return paths


def _safe_filename(value: str) -> str:
    cleaned = SAFE_FILENAME_PATTERN.sub("-", value).strip(".-")
    return cleaned or "note-candidate"


__all__ = ["export_note_previews"]

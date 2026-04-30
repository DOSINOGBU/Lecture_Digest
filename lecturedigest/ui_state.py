from __future__ import annotations

import os
from dataclasses import dataclass

from lecturedigest.models import CorrectionLogEntry, LectureRecord
from lecturedigest.storage import JsonLectureRepository


@dataclass(frozen=True)
class LibraryState:
    lectures: list[LectureRecord]
    error_message: str | None = None

    @property
    def is_empty(self) -> bool:
        return not self.lectures and self.error_message is None


def load_library(repository: JsonLectureRepository) -> LibraryState:
    try:
        return LibraryState(lectures=repository.list_lectures())
    except Exception as exc:  # UI boundary: preserve context without crashing the app.
        return LibraryState(
            lectures=[],
            error_message=f"{exc.__class__.__name__}: {exc}",
        )


def lecture_label(record: LectureRecord) -> str:
    category = " / ".join(
        item
        for item in [
            record.lecture_title,
            record.major_category,
            record.middle_category,
        ]
        if item
    )
    suffix = f" | {category}" if category else ""
    return f"{record.title}{suffix} ({record.status})"


def status_counts(record: LectureRecord) -> dict[str, int]:
    return {
        "segments": len(record.segments),
        "chunks": len(record.chunks),
        "slides": len(record.slides),
        "issues": len(record.issues),
        "note_candidates": len(record.note_candidates),
        "review_corrections": len(correction_review_queue(record)),
        "cards": len(record.flashcards),
        "quizzes": len(record.quiz_items),
    }


def correction_review_queue(record: LectureRecord) -> list[CorrectionLogEntry]:
    return [
        entry
        for entry in record.correction_log
        if entry.status == "review_required"
    ]


def note_candidates(record: LectureRecord) -> list[dict[str, object]]:
    return [candidate for candidate in record.note_candidates if isinstance(candidate, dict)]


def cost_or_quota_issues(record: LectureRecord) -> list[str]:
    keywords = ("quota", "rate", "cost", "budget", "openai_rate_limited")
    messages = []
    for issue in record.issues:
        text = f"{issue.code} {issue.message}".lower()
        if any(keyword in text for keyword in keywords):
            messages.append(f"{issue.code}: {issue.message}")
    return messages


def has_openai_api_key(env: dict[str, str] | None = None) -> bool:
    source = env if env is not None else os.environ
    return bool(source.get("OPENAI_API_KEY", "").strip())


def paid_action_previews(record: LectureRecord) -> list[dict[str, object]]:
    return [
        {
            "name": "Transcript correction",
            "model": str(record.correction_metadata.get("model") or "gpt-4o"),
            "external_boundary": "selected transcript segment text",
            "input_size_bytes": _segments_size(record),
            "dry_run": (
                "python -m lecturedigest finalize-transcript "
                f"--lecture-id {record.lecture_id} --openai --dry-run"
            ),
        },
        {
            "name": "Embedding regeneration",
            "model": str(record.rag_metadata.get("embedding_model") or "text-embedding-3-large"),
            "external_boundary": "indexed transcript, OCR, and approved note text",
            "input_size_bytes": _search_index_size(record),
            "dry_run": (
                "python -m lecturedigest index "
                f"--lecture-id {record.lecture_id} --embed-openai --dry-run"
            ),
        },
        {
            "name": "Vision OCR",
            "model": "gpt-4o",
            "external_boundary": "selected representative frame images",
            "input_size_bytes": _slide_metadata_size(record),
            "dry_run": (
                "python -m lecturedigest ocr "
                f"--lecture-id {record.lecture_id} --dry-run"
            ),
        },
    ]


def _segments_size(record: LectureRecord) -> int:
    return len("\n".join(segment.text for segment in record.segments).encode("utf-8"))


def _search_index_size(record: LectureRecord) -> int:
    text = "\n".join(str(entry.get("indexed_text") or "") for entry in record.search_index)
    return len(text.encode("utf-8"))


def _slide_metadata_size(record: LectureRecord) -> int:
    return sum(len(str(slide.source_frame_ts).encode("utf-8")) for slide in record.slides)

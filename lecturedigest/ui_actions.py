from __future__ import annotations

from pathlib import Path

from lecturedigest.correction_review import (
    approve_correction_candidate,
    reject_correction_candidate,
)
from lecturedigest.auto_pipeline import AutoPipelineOptions, process_lecture_with_auto_ai
from lecturedigest.ingestion import register_lecture
from lecturedigest.note_generation import approve_note_candidate, reject_note_candidate
from lecturedigest.storage import JsonLectureRepository


def register_lecture_from_paths(
    repository: JsonLectureRepository,
    *,
    video_path: str,
    subtitle_path: str | None,
    title: str,
    instructor: str,
    category: str,
    auto_ai: bool = False,
    include_ocr: bool = False,
    time_budget_seconds: float | None = None,
) -> str:
    record = register_lecture(
        video_path=Path(video_path),
        subtitle_path=Path(subtitle_path) if subtitle_path else None,
        title=title,
        instructor=instructor,
        category=category,
    )
    repository.save(record)
    if auto_ai:
        process_lecture_with_auto_ai(
            repository,
            lecture_id=record.lecture_id,
            options=AutoPipelineOptions(
                openai=True,
                include_ocr=include_ocr,
                resume=True,
                time_budget_seconds=time_budget_seconds,
            ),
        )
    return record.lecture_id


def approve_note(
    repository: JsonLectureRepository,
    *,
    lecture_id: str,
    candidate_id: str,
) -> None:
    record = _require_record(repository, lecture_id)
    repository.save(approve_note_candidate(record, candidate_id=candidate_id))


def reject_note(
    repository: JsonLectureRepository,
    *,
    lecture_id: str,
    candidate_id: str,
    reason: str | None = None,
) -> None:
    record = _require_record(repository, lecture_id)
    repository.save(
        reject_note_candidate(record, candidate_id=candidate_id, reason=reason)
    )


def approve_correction(
    repository: JsonLectureRepository,
    *,
    lecture_id: str,
    segment_id: str,
) -> None:
    record = _require_record(repository, lecture_id)
    repository.save(approve_correction_candidate(record, segment_id=segment_id))


def reject_correction(
    repository: JsonLectureRepository,
    *,
    lecture_id: str,
    segment_id: str,
    reason: str | None = None,
) -> None:
    record = _require_record(repository, lecture_id)
    repository.save(
        reject_correction_candidate(record, segment_id=segment_id, reason=reason)
    )


def _require_record(repository: JsonLectureRepository, lecture_id: str):
    record = repository.get_lecture(lecture_id)
    if record is None:
        raise ValueError(f"Lecture not found: {lecture_id}")
    return record

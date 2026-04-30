from __future__ import annotations

import argparse

from lecturedigest.correction import finalize_transcript
from lecturedigest.errors import ErrorDetail, ValidationError
from lecturedigest.models import LectureRecord
from lecturedigest.storage import JsonLectureRepository


def finalize_transcript_command(
    args: argparse.Namespace,
    repository: JsonLectureRepository,
) -> int:
    lectures = repository.list_lectures()
    if not lectures:
        print("No lectures registered yet. Add one with `register`.")
        return 0

    print(
        "[LectureCorrection] finalize-transcript start "
        f"{{ lectureId={args.lecture_id}; "
        f"confidenceThreshold={args.confidence_threshold} }}"
    )
    record = repository.get_lecture(args.lecture_id)
    if record is None:
        raise ValidationError(
            ErrorDetail(
                code="lecture_not_found",
                message=f"Lecture not found: {args.lecture_id}",
                stage="correction",
                retryable=False,
            )
        )

    updated = finalize_transcript(
        record,
        correction_result_path=args.correction_result,
        confidence_threshold=args.confidence_threshold,
    )
    repository.save(updated)
    print(format_correction_result(updated))
    return 0


def format_correction_result(record: LectureRecord) -> str:
    applied = sum(1 for entry in record.correction_log if entry.applied)
    review_required = sum(
        1 for entry in record.correction_log if entry.status == "review_required"
    )
    failures = sum(1 for entry in record.correction_log if entry.status == "failed")
    correction_issues = sum(
        1 for issue in record.issues if issue.stage == "correction"
    )
    return (
        "[LectureCorrection] finalize-transcript success "
        f"{{ lectureId={record.lecture_id}; status={record.status}; "
        f"stage={record.stage}; segments={len(record.segments)}; "
        f"applied={applied}; reviewRequired={review_required}; "
        f"failures={failures}; issues={correction_issues} }}"
    )

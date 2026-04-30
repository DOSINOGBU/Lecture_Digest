from __future__ import annotations

import argparse

from lecturedigest.errors import ErrorDetail, ValidationError
from lecturedigest.note_generation import (
    DEFAULT_NOTE_MODEL,
    DEFAULT_NOTE_PROMPT_VERSION,
    DEFAULT_NOTE_TONE,
    approve_note_candidate,
    generate_note_candidates,
    reject_note_candidate,
)
from lecturedigest.storage import JsonLectureRepository


def generate_notes_command(
    args: argparse.Namespace,
    repository: JsonLectureRepository,
) -> int:
    record = _load_record(args.lecture_id, repository, stage="note_generation")
    if record is None:
        return 0

    print(
        "[LectureNotes] generate-notes start "
        f"{{ lectureId={args.lecture_id}; tone={args.tone}; "
        f"model={args.note_model}; promptVersion={args.prompt_version} }}"
    )
    updated = generate_note_candidates(
        record,
        tone=args.tone,
        model=args.note_model,
        prompt_version=args.prompt_version,
    )
    repository.save(updated)
    print(format_note_generation_result(updated))
    return 0


def approve_note_command(
    args: argparse.Namespace,
    repository: JsonLectureRepository,
) -> int:
    record = _load_record(args.lecture_id, repository, stage="note_approval")
    if record is None:
        return 0

    print(
        "[LectureNotes] approve-note start "
        f"{{ lectureId={args.lecture_id}; candidateId={args.candidate_id} }}"
    )
    updated = approve_note_candidate(record, candidate_id=args.candidate_id)
    repository.save(updated)
    print(format_note_approval_result(updated))
    return 0


def reject_note_command(
    args: argparse.Namespace,
    repository: JsonLectureRepository,
) -> int:
    record = _load_record(args.lecture_id, repository, stage="note_review")
    if record is None:
        return 0

    print(
        "[LectureNotes] reject-note start "
        f"{{ lectureId={args.lecture_id}; candidateId={args.candidate_id} }}"
    )
    updated = reject_note_candidate(
        record,
        candidate_id=args.candidate_id,
        reason=args.reason,
    )
    repository.save(updated)
    print(format_note_rejection_result(updated, args.candidate_id))
    return 0


def add_note_parsers(subparsers: argparse._SubParsersAction) -> None:
    generate_parser = subparsers.add_parser("generate-notes")
    generate_parser.add_argument("--lecture-id", required=True)
    generate_parser.add_argument(
        "--tone",
        default=DEFAULT_NOTE_TONE,
        choices=["formal", "casual", "keep_original"],
    )
    generate_parser.add_argument("--note-model", default=DEFAULT_NOTE_MODEL)
    generate_parser.add_argument(
        "--prompt-version",
        default=DEFAULT_NOTE_PROMPT_VERSION,
    )

    approve_parser = subparsers.add_parser("approve-note")
    approve_parser.add_argument("--lecture-id", required=True)
    approve_parser.add_argument("--candidate-id", required=True)

    reject_parser = subparsers.add_parser("reject-note")
    reject_parser.add_argument("--lecture-id", required=True)
    reject_parser.add_argument("--candidate-id", required=True)
    reject_parser.add_argument("--reason")


def format_note_generation_result(record) -> str:
    flagged = sum(
        1
        for candidate in record.note_candidates
        if _validation_status(candidate) == "flagged"
    )
    lines = [
        "[LectureNotes] generate-notes success "
        f"{{ lectureId={record.lecture_id}; status={record.status}; "
        f"stage={record.stage}; candidates={len(record.note_candidates)}; "
        f"flagged={flagged}; approved=False }}"
    ]
    for candidate in record.note_candidates:
        lines.append(
            "- "
            f"{candidate.get('candidate_id')} "
            f"status={candidate.get('status')} "
            f"variant={candidate.get('variant')} "
            f"validation={_validation_status(candidate)}"
        )
    return "\n".join(lines)


def format_note_approval_result(record) -> str:
    approved_id = record.note_metadata.get("approved_candidate_id", "")
    return (
        "[LectureNotes] approve-note success "
        f"{{ lectureId={record.lecture_id}; status={record.status}; "
        f"stage={record.stage}; candidateId={approved_id}; "
        f"noteSections={len(record.note_sections)} }}"
    )


def format_note_rejection_result(record, candidate_id: str) -> str:
    rejected = [
        candidate
        for candidate in record.note_candidates
        if str(candidate.get("candidate_id")) == candidate_id
    ]
    status = rejected[0].get("status") if rejected else "unknown"
    return (
        "[LectureNotes] reject-note success "
        f"{{ lectureId={record.lecture_id}; status={record.status}; "
        f"stage={record.stage}; candidateId={candidate_id}; "
        f"candidateStatus={status} }}"
    )


def _validation_status(candidate: dict[str, object]) -> str:
    validation = candidate.get("validation", {})
    if not isinstance(validation, dict):
        return "unknown"
    return str(validation.get("status", "unknown"))


def _load_record(
    lecture_id: str,
    repository: JsonLectureRepository,
    *,
    stage: str,
):
    lectures = repository.list_lectures()
    if not lectures:
        print("No lectures registered yet. Add one with `register`.")
        return None

    record = repository.get_lecture(lecture_id)
    if record is None:
        raise ValidationError(
            ErrorDetail(
                code="lecture_not_found",
                message=f"Lecture not found: {lecture_id}",
                stage=stage,
                retryable=False,
            )
        )
    return record

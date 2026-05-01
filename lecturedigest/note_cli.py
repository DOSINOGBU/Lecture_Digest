from __future__ import annotations

import argparse
from pathlib import Path

from lecturedigest.errors import ErrorDetail, ValidationError
from lecturedigest.note_generation import (
    DEFAULT_NOTE_MODEL,
    DEFAULT_NOTE_PROMPT_VERSION,
    DEFAULT_NOTE_TONE,
    approve_note_candidate,
    generate_note_candidates,
    reject_note_candidate,
)
from lecturedigest.openai_notes import (
    DEFAULT_OPENAI_NOTE_MODEL,
    DEFAULT_OPENAI_NOTE_PROMPT_VERSION,
    DEFAULT_OPENAI_NOTE_TIMEOUT_SECONDS,
    format_openai_note_dry_run,
    generate_note_candidates_with_openai,
)
from lecturedigest.note_quality import (
    format_note_quality_result,
    inspect_note_quality,
)
from lecturedigest.note_preview import export_note_previews
from lecturedigest.storage import JsonLectureRepository


def generate_notes_command(
    args: argparse.Namespace,
    repository: JsonLectureRepository,
) -> int:
    record = _load_record(args.lecture_id, repository, stage="note_generation")
    if record is None:
        return 0

    model = _note_model(args)
    prompt_version = _prompt_version(args)
    provider = "openai" if args.openai else "local"
    print(
        "[LectureNotes] generate-notes start "
        f"{{ lectureId={args.lecture_id}; provider={provider}; tone={args.tone}; "
        f"model={model}; promptVersion={prompt_version}; dryRun={args.dry_run}; "
        f"repair={args.repair}; variant={args.variant or 'all'}; "
        f"candidateLimit={args.candidate_limit or 'default'}; resume={args.resume}; "
        f"timeBudgetSeconds={args.time_budget_seconds or 'none'} }}"
    )
    if args.repair and not args.openai:
        raise ValidationError(
            ErrorDetail(
                code="openai_required_for_note_repair",
                message="Note repair is only available with `generate-notes --openai`.",
                stage="note_generation",
                retryable=False,
            )
        )
    if args.openai:
        if args.repair and args.max_repair_attempts > 1:
            print(
                "[LectureNotes] repair call warning "
                f"{{ maxRepairAttempts={args.max_repair_attempts}; "
                "use --candidate-limit 1 or --time-budget-seconds for safer runs }}"
            )
        result = generate_note_candidates_with_openai(
            record,
            tone=args.tone,
            model=model,
            prompt_version=prompt_version,
            dry_run=args.dry_run,
            repair=args.repair,
            max_repair_attempts=args.max_repair_attempts,
            timeout_seconds=args.openai_timeout_seconds,
            variants=[args.variant] if args.variant else None,
            candidate_limit=args.candidate_limit,
            resume=args.resume,
            time_budget_seconds=args.time_budget_seconds,
            checkpoint=_note_checkpoint(args, repository) if not args.dry_run else None,
        )
        if args.dry_run:
            print(format_openai_note_dry_run(result))
            return 0
        updated = result.record
    else:
        updated = generate_note_candidates(
            record,
            tone=args.tone,
            model=model,
            prompt_version=prompt_version,
        )
    preview_paths = []
    if args.export_preview_dir:
        preview_paths = export_note_previews(updated, args.export_preview_dir)
    repository.save(updated)
    print(format_note_generation_result(updated, preview_paths=preview_paths))
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


def inspect_note_quality_command(
    args: argparse.Namespace,
    repository: JsonLectureRepository,
) -> int:
    record = _load_record(args.lecture_id, repository, stage="note_quality")
    if record is None:
        return 0

    print(
        "[LectureNotes] inspect-note-quality start "
        f"{{ lectureId={args.lecture_id}; "
        f"candidateId={args.candidate_id or 'all'} }}"
    )
    result = inspect_note_quality(record, candidate_id=args.candidate_id)
    print(format_note_quality_result(result))
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
    generate_parser.add_argument("--openai", action="store_true")
    generate_parser.add_argument("--dry-run", action="store_true")
    generate_parser.add_argument("--repair", action="store_true")
    generate_parser.add_argument("--max-repair-attempts", type=int, default=1)
    generate_parser.add_argument(
        "--variant",
        choices=["balanced", "concept_focused", "action_focused"],
    )
    generate_parser.add_argument("--candidate-limit", type=int)
    generate_parser.add_argument("--resume", action="store_true")
    generate_parser.add_argument("--time-budget-seconds", type=float)
    generate_parser.add_argument(
        "--openai-timeout-seconds",
        type=float,
        default=DEFAULT_OPENAI_NOTE_TIMEOUT_SECONDS,
    )
    generate_parser.add_argument("--export-preview-dir", type=Path)

    approve_parser = subparsers.add_parser("approve-note")
    approve_parser.add_argument("--lecture-id", required=True)
    approve_parser.add_argument("--candidate-id", required=True)

    reject_parser = subparsers.add_parser("reject-note")
    reject_parser.add_argument("--lecture-id", required=True)
    reject_parser.add_argument("--candidate-id", required=True)
    reject_parser.add_argument("--reason")

    inspect_parser = subparsers.add_parser("inspect-note-quality")
    inspect_parser.add_argument("--lecture-id", required=True)
    inspect_parser.add_argument("--candidate-id")


def format_note_generation_result(record, *, preview_paths=None) -> str:
    preview_paths = preview_paths or []
    flagged = sum(
        1
        for candidate in record.note_candidates
        if _validation_status(candidate) == "flagged"
    )
    review_required = sum(
        1
        for candidate in record.note_candidates
        if _validation_status(candidate) == "review_required"
    )
    lines = [
        "[LectureNotes] generate-notes success "
        f"{{ lectureId={record.lecture_id}; status={record.status}; "
        f"stage={record.stage}; candidates={len(record.note_candidates)}; "
        f"flagged={flagged}; reviewRequired={review_required}; "
        f"previewExports={len(preview_paths)}; approved=False }}"
    ]
    for candidate in record.note_candidates:
        lines.append(
            "- "
            f"{candidate.get('candidate_id')} "
            f"status={candidate.get('status')} "
            f"variant={candidate.get('variant')} "
            f"validation={_validation_status(candidate)}"
        )
    for path in preview_paths:
        lines.append(f"- preview={path}")
    return "\n".join(lines)


def _note_checkpoint(args: argparse.Namespace, repository: JsonLectureRepository):
    def save_partial(record) -> None:
        repository.save(record)
        if args.export_preview_dir:
            export_note_previews(record, args.export_preview_dir)

    return save_partial


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


def _note_model(args: argparse.Namespace) -> str:
    if args.openai and args.note_model == DEFAULT_NOTE_MODEL:
        return DEFAULT_OPENAI_NOTE_MODEL
    return args.note_model


def _prompt_version(args: argparse.Namespace) -> str:
    if args.openai and args.prompt_version == DEFAULT_NOTE_PROMPT_VERSION:
        return DEFAULT_OPENAI_NOTE_PROMPT_VERSION
    return args.prompt_version


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

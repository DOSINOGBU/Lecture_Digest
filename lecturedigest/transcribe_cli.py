from __future__ import annotations

import argparse

from lecturedigest.errors import ErrorDetail, TranscriptionError, ValidationError
from lecturedigest.openai_transcription import (
    DEFAULT_STT_CHUNKING_STRATEGY,
    format_transcription_dry_run,
    transcribe_lecture_with_openai,
)
from lecturedigest.storage import JsonLectureRepository
from lecturedigest.transcription import DEFAULT_STT_MODEL, DEFAULT_STT_RESPONSE_FORMAT


def add_transcribe_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("transcribe")
    parser.add_argument("--lecture-id", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--model", default=DEFAULT_STT_MODEL)
    parser.add_argument("--response-format", default=DEFAULT_STT_RESPONSE_FORMAT)
    parser.add_argument(
        "--chunking-strategy",
        default=DEFAULT_STT_CHUNKING_STRATEGY,
    )


def transcribe_command(
    args: argparse.Namespace,
    repository: JsonLectureRepository,
) -> int:
    lectures = repository.list_lectures()
    if not lectures:
        print("No lectures registered yet. Add one with `register`.")
        return 0

    print(
        "[LectureTranscription] transcribe start "
        f"{{ lectureId={args.lecture_id}; dryRun={args.dry_run}; "
        f"model={args.model}; responseFormat={args.response_format}; "
        f"chunkingStrategy={args.chunking_strategy} }}"
    )
    record = repository.get_lecture(args.lecture_id)
    if record is None:
        raise ValidationError(
            ErrorDetail(
                code="lecture_not_found",
                message=f"Lecture was not found: {args.lecture_id}",
                stage="transcription",
                retryable=False,
            )
        )

    result = transcribe_lecture_with_openai(
        record,
        model=args.model,
        response_format=args.response_format,
        chunking_strategy=args.chunking_strategy,
        dry_run=args.dry_run,
    )
    if args.dry_run:
        print(format_transcription_dry_run(result))
        return 0

    repository.save(result.record)
    if not result.client_result.succeeded:
        issue = result.record.issues[-1]
        raise TranscriptionError(
            ErrorDetail(
                code=issue.code,
                message=issue.message,
                stage=issue.stage,
                retryable=issue.retryable,
            )
        )

    print(
        "[LectureTranscription] transcribe success "
        f"{{ lectureId={result.record.lecture_id}; "
        f"status={result.record.status}; stage={result.record.stage}; "
        f"transcriptSource={result.record.transcript_source}; "
        f"segments={len(result.record.segments)} }}"
    )
    return 0

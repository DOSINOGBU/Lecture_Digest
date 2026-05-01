from __future__ import annotations

import argparse

from lecturedigest.errors import ErrorDetail, TranscriptionError, ValidationError
from lecturedigest.media_transcription import (
    format_large_transcription_dry_run,
    should_route_to_large_media,
    transcribe_large_lecture_with_openai,
)
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

    try:
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
    except ValidationError as exc:
        if not should_route_to_large_media(exc):
            raise
        large_result = transcribe_large_lecture_with_openai(
            record,
            model=args.model,
            response_format=args.response_format,
            chunking_strategy=args.chunking_strategy,
            dry_run=args.dry_run,
        )
        if args.dry_run:
            print(format_large_transcription_dry_run(large_result))
            return 0
        result = large_result

    repository.save(result.record)
    if not _transcription_succeeded(result):
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


def _transcription_succeeded(result) -> bool:
    if hasattr(result, "client_result"):
        return result.client_result.succeeded
    return all(item.succeeded for item in result.client_results)

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from lecturedigest.anki_cli import (
    add_anki_parsers,
    export_anki_command,
    generate_cards_command,
)
from lecturedigest.chunking import chunk_lecture
from lecturedigest.correction import (
    DEFAULT_CORRECTION_CONFIDENCE_THRESHOLD,
    DEFAULT_CORRECTION_MODEL,
    DEFAULT_CORRECTION_PROMPT_VERSION,
)
from lecturedigest.enrichment import (
    DEFAULT_FRAME_SAMPLE_INTERVAL_SECONDS,
    DEFAULT_SLIDE_CHANGE_THRESHOLD,
    apply_ocr_enrichment,
)
from lecturedigest.errors import ErrorDetail, LectureDigestError, ValidationError
from lecturedigest.folder_ingestion import FolderIngestionResult, register_lecture_folder
from lecturedigest.ingestion import register_lecture
from lecturedigest.models import LectureRecord
from lecturedigest.note_cli import (
    add_note_parsers,
    approve_note_command,
    generate_notes_command,
    inspect_note_quality_command,
    reject_note_command,
)
from lecturedigest.ocr_cli import add_ocr_parser, ocr_command
from lecturedigest.openai_correction import DEFAULT_CORRECTION_BATCH_SIZE
from lecturedigest.quiz_cli import (
    add_quiz_parsers,
    generate_quizzes_command,
    grade_quiz_session_command,
    start_quiz_session_command,
    submit_quiz_answer_command,
)
from lecturedigest.rag_cli import (
    add_rag_parsers,
    ask_command,
    index_command,
    summarize_command,
)
from lecturedigest.storage import JsonLectureRepository
from lecturedigest.transcribe_cli import add_transcribe_parser, transcribe_command
from lecturedigest.transcription import apply_stt_result
from lecturedigest.transcript_cli import finalize_transcript_command

DEFAULT_STORE = Path(".lecturedigest") / "lectures.json"


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    repository = JsonLectureRepository(args.store)

    try:
        if args.command == "register":
            return _register(args, repository)
        if args.command == "register-folder":
            return _register_folder(args, repository)
        if args.command == "list":
            return _list(repository)
        if args.command == "transcribe":
            return transcribe_command(args, repository)
        if args.command == "import-stt":
            return _import_stt(args, repository)
        if args.command == "import-ocr":
            return _import_ocr(args, repository)
        if args.command == "ocr":
            return ocr_command(args, repository)
        if args.command == "finalize-transcript":
            return finalize_transcript_command(args, repository)
        if args.command == "chunk":
            return _chunk(args, repository)
        if args.command == "index":
            return index_command(args, repository)
        if args.command == "summarize":
            return summarize_command(args, repository)
        if args.command == "ask":
            return ask_command(args, repository)
        if args.command == "generate-notes":
            return generate_notes_command(args, repository)
        if args.command == "approve-note":
            return approve_note_command(args, repository)
        if args.command == "reject-note":
            return reject_note_command(args, repository)
        if args.command == "inspect-note-quality":
            return inspect_note_quality_command(args, repository)
        if args.command == "generate-cards":
            return generate_cards_command(args, repository)
        if args.command == "export-anki":
            return export_anki_command(args, repository)
        if args.command == "generate-quizzes":
            return generate_quizzes_command(args, repository)
        if args.command == "start-quiz-session":
            return start_quiz_session_command(args, repository)
        if args.command == "submit-quiz-answer":
            return submit_quiz_answer_command(args, repository)
        if args.command == "grade-quiz-session":
            return grade_quiz_session_command(args, repository)
    except LectureDigestError as exc:
        _print_error(exc)
        return 1

    parser.print_help()
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lecturedigest")
    parser.add_argument(
        "--store",
        default=DEFAULT_STORE,
        type=Path,
        help="Lecture state JSON path.",
    )
    subparsers = parser.add_subparsers(dest="command")

    register_parser = subparsers.add_parser("register")
    register_parser.add_argument("--video", required=True, type=Path)
    register_parser.add_argument("--subtitle", type=Path)
    register_parser.add_argument("--title", required=True)
    register_parser.add_argument("--instructor", required=True)
    register_parser.add_argument("--category", required=True)

    register_folder_parser = subparsers.add_parser("register-folder")
    register_folder_parser.add_argument("--folder", required=True, type=Path)
    register_folder_parser.add_argument("--instructor", required=True)

    chunk_parser = subparsers.add_parser("chunk")
    chunk_parser.add_argument("--lecture-id", required=True)
    chunk_parser.add_argument("--window-seconds", type=int, default=90)
    chunk_parser.add_argument("--overlap-seconds", type=int, default=15)
    chunk_parser.add_argument("--chapter", default="unassigned")

    import_stt_parser = subparsers.add_parser("import-stt")
    import_stt_parser.add_argument("--lecture-id", required=True)
    import_stt_parser.add_argument("--stt-result", required=True, type=Path)

    add_transcribe_parser(subparsers)

    import_ocr_parser = subparsers.add_parser("import-ocr")
    import_ocr_parser.add_argument("--lecture-id", required=True)
    import_ocr_parser.add_argument("--ocr-result", required=True, type=Path)
    import_ocr_parser.add_argument(
        "--sample-interval-seconds",
        type=int,
        default=DEFAULT_FRAME_SAMPLE_INTERVAL_SECONDS,
    )
    import_ocr_parser.add_argument(
        "--change-threshold",
        type=float,
        default=DEFAULT_SLIDE_CHANGE_THRESHOLD,
    )

    add_ocr_parser(subparsers)

    finalize_parser = subparsers.add_parser("finalize-transcript")
    finalize_parser.add_argument("--lecture-id", required=True)
    finalize_parser.add_argument("--correction-result", type=Path)
    finalize_parser.add_argument(
        "--confidence-threshold",
        type=float,
        default=DEFAULT_CORRECTION_CONFIDENCE_THRESHOLD,
    )
    finalize_parser.add_argument("--openai", action="store_true")
    finalize_parser.add_argument("--dry-run", action="store_true")
    finalize_parser.add_argument("--model", default=DEFAULT_CORRECTION_MODEL)
    finalize_parser.add_argument(
        "--prompt-version",
        default=DEFAULT_CORRECTION_PROMPT_VERSION,
    )
    finalize_parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_CORRECTION_BATCH_SIZE,
    )

    add_rag_parsers(subparsers)
    add_note_parsers(subparsers)
    add_anki_parsers(subparsers)
    add_quiz_parsers(subparsers)

    subparsers.add_parser("list")
    return parser


def _register(args: argparse.Namespace, repository: JsonLectureRepository) -> int:
    print(
        "[LectureIngestion] register start "
        f"{{ hasSubtitle={args.subtitle is not None} }}"
    )
    record = register_lecture(
        video_path=args.video,
        subtitle_path=args.subtitle,
        title=args.title,
        instructor=args.instructor,
        category=args.category,
    )
    repository.save(record)
    print(_format_record(record))
    return 0


def _register_folder(
    args: argparse.Namespace,
    repository: JsonLectureRepository,
) -> int:
    print(
        "[LectureIngestion] register-folder start "
        f"{{ folder={args.folder} }}"
    )
    result = register_lecture_folder(
        folder_path=args.folder,
        instructor=args.instructor,
    )
    if not result.records:
        print(_format_folder_empty(result))
        return 0

    for record in result.records:
        repository.save(record)
    print(_format_folder_result(result))
    return 0


def _list(repository: JsonLectureRepository) -> int:
    lectures = repository.list_lectures()
    if not lectures:
        print("No lectures registered yet. Add one with `register`.")
        return 0

    for lecture in lectures:
        print(_format_record(lecture))
    return 0


def _chunk(args: argparse.Namespace, repository: JsonLectureRepository) -> int:
    lectures = repository.list_lectures()
    if not lectures:
        print("No lectures registered yet. Add one with `register`.")
        return 0

    print(
        "[LectureIndexing] chunk start "
        f"{{ lectureId={args.lecture_id}; windowSeconds={args.window_seconds}; "
        f"overlapSeconds={args.overlap_seconds} }}"
    )
    record = repository.get_lecture(args.lecture_id)
    if record is None:
        raise ValidationError(
            ErrorDetail(
                code="lecture_not_found",
                message=f"강의를 찾을 수 없습니다: {args.lecture_id}",
                stage="chunking",
                retryable=False,
            )
        )

    updated = chunk_lecture(
        record,
        window_seconds=args.window_seconds,
        overlap_seconds=args.overlap_seconds,
        chapter=args.chapter,
    )
    repository.save(updated)
    print(_format_chunk_result(updated))
    return 0


def _import_stt(args: argparse.Namespace, repository: JsonLectureRepository) -> int:
    lectures = repository.list_lectures()
    if not lectures:
        print("No lectures registered yet. Add one with `register`.")
        return 0

    print(
        "[LectureTranscription] import-stt start "
        f"{{ lectureId={args.lecture_id} }}"
    )
    record = repository.get_lecture(args.lecture_id)
    if record is None:
        raise ValidationError(
            ErrorDetail(
                code="lecture_not_found",
                message=f"강의를 찾을 수 없습니다: {args.lecture_id}",
                stage="transcription",
                retryable=False,
            )
        )

    updated = apply_stt_result(record, stt_result_path=args.stt_result)
    repository.save(updated)
    print(_format_stt_result(updated))
    return 0


def _import_ocr(args: argparse.Namespace, repository: JsonLectureRepository) -> int:
    lectures = repository.list_lectures()
    if not lectures:
        print("No lectures registered yet. Add one with `register`.")
        return 0

    print(
        "[LectureEnrichment] import-ocr start "
        f"{{ lectureId={args.lecture_id}; "
        f"sampleIntervalSeconds={args.sample_interval_seconds}; "
        f"changeThreshold={args.change_threshold} }}"
    )
    record = repository.get_lecture(args.lecture_id)
    if record is None:
        raise ValidationError(
            ErrorDetail(
                code="lecture_not_found",
                message=f"媛뺤쓽瑜?李얠쓣 ???놁뒿?덈떎: {args.lecture_id}",
                stage="enrichment",
                retryable=False,
            )
        )

    updated = apply_ocr_enrichment(
        record,
        ocr_result_path=args.ocr_result,
        sample_interval_seconds=args.sample_interval_seconds,
        change_threshold=args.change_threshold,
    )
    repository.save(updated)
    print(_format_ocr_result(updated))
    return 0


def _format_record(record: LectureRecord) -> str:
    segment_count = len(record.segments)
    chunk_count = len(record.chunks)
    issue_count = len(record.issues)
    return (
        "[LectureIngestion] register success "
        f"{{ lectureId={record.lecture_id}; status={record.status}; "
        f"stage={record.stage}; transcriptSource={record.transcript_source}; "
        f"segments={segment_count}; chunks={chunk_count}; issues={issue_count} }}"
    )


def _format_folder_result(result: FolderIngestionResult) -> str:
    subtitle_ready = sum(
        1 for record in result.records if record.transcript_source == "subtitle"
    )
    stt_required = sum(
        1 for record in result.records if record.transcript_source == "stt_pending"
    )
    subtitle_unmatched = sum(
        1 for record in result.records if record.status == "subtitle_unmatched"
    )
    return (
        "[LectureIngestion] register-folder success "
        f"{{ lectureTitle={result.lecture_title}; records={len(result.records)}; "
        f"subtitleReady={subtitle_ready}; sttRequired={stt_required}; "
        f"subtitleUnmatched={subtitle_unmatched}; batchIssues={len(result.issues)} }}"
    )


def _format_folder_empty(result: FolderIngestionResult) -> str:
    return (
        "[LectureIngestion] register-folder empty "
        f"{{ lectureTitle={result.lecture_title}; records=0; "
        f"batchIssues={len(result.issues)} }}"
    )


def _format_chunk_result(record: LectureRecord) -> str:
    return (
        "[LectureIndexing] chunk success "
        f"{{ lectureId={record.lecture_id}; status={record.status}; "
        f"stage={record.stage}; chunks={len(record.chunks)} }}"
    )


def _format_stt_result(record: LectureRecord) -> str:
    return (
        "[LectureTranscription] import-stt success "
        f"{{ lectureId={record.lecture_id}; status={record.status}; "
        f"stage={record.stage}; transcriptSource={record.transcript_source}; "
        f"segments={len(record.segments)} }}"
    )


def _format_ocr_result(record: LectureRecord) -> str:
    enriched_segments = sum(1 for segment in record.segments if segment.ocr_text)
    enrichment_issues = sum(
        1 for issue in record.issues if issue.stage == "enrichment"
    )
    return (
        "[LectureEnrichment] import-ocr success "
        f"{{ lectureId={record.lecture_id}; status={record.status}; "
        f"stage={record.stage}; slides={len(record.slides)}; "
        f"enrichedSegments={enriched_segments}; issues={enrichment_issues} }}"
    )


def _print_error(exc: LectureDigestError) -> None:
    detail = exc.detail
    print(
        "[LectureDigest] command failed "
        f"{{ code={detail.code}; stage={detail.stage}; "
        f"retryable={detail.retryable} }}",
        file=sys.stderr,
    )
    print(detail.message, file=sys.stderr)

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from lecturedigest.chunking import chunk_lecture
from lecturedigest.errors import ErrorDetail, LectureDigestError, ValidationError
from lecturedigest.ingestion import register_lecture
from lecturedigest.models import LectureRecord
from lecturedigest.storage import JsonLectureRepository

DEFAULT_STORE = Path(".lecturedigest") / "lectures.json"


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    repository = JsonLectureRepository(args.store)

    try:
        if args.command == "register":
            return _register(args, repository)
        if args.command == "list":
            return _list(repository)
        if args.command == "chunk":
            return _chunk(args, repository)
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

    chunk_parser = subparsers.add_parser("chunk")
    chunk_parser.add_argument("--lecture-id", required=True)
    chunk_parser.add_argument("--window-seconds", type=int, default=90)
    chunk_parser.add_argument("--overlap-seconds", type=int, default=15)
    chunk_parser.add_argument("--chapter", default="unassigned")

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


def _format_chunk_result(record: LectureRecord) -> str:
    return (
        "[LectureIndexing] chunk success "
        f"{{ lectureId={record.lecture_id}; status={record.status}; "
        f"stage={record.stage}; chunks={len(record.chunks)} }}"
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

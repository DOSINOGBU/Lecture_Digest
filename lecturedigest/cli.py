from __future__ import annotations

import argparse
import sys
from pathlib import Path

from lecturedigest.errors import LectureDigestError
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


def _format_record(record: LectureRecord) -> str:
    segment_count = len(record.segments)
    issue_count = len(record.issues)
    return (
        "[LectureIngestion] register success "
        f"{{ lectureId={record.lecture_id}; status={record.status}; "
        f"stage={record.stage}; transcriptSource={record.transcript_source}; "
        f"segments={segment_count}; issues={issue_count} }}"
    )


def _print_error(exc: LectureDigestError) -> None:
    detail = exc.detail
    print(
        "[LectureIngestion] register failed "
        f"{{ code={detail.code}; stage={detail.stage}; "
        f"retryable={detail.retryable} }}",
        file=sys.stderr,
    )
    print(detail.message, file=sys.stderr)

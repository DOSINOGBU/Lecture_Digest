from __future__ import annotations

import argparse

from lecturedigest.errors import ErrorDetail, ValidationError
from lecturedigest.openai_quizzes import (
    DEFAULT_OPENAI_QUIZ_MODEL,
    DEFAULT_OPENAI_QUIZ_PROMPT_VERSION,
    DEFAULT_QUIZ_BATCH_SIZE_SECTIONS,
    format_openai_quiz_dry_run,
    generate_quizzes_with_openai,
)
from lecturedigest.quiz_generation import (
    DEFAULT_QUIZ_COUNT,
    DEFAULT_QUIZ_MODEL,
    DEFAULT_QUIZ_PROMPT_VERSION,
    DEFAULT_QUESTION_TYPES,
    generate_quizzes,
)
from lecturedigest.storage import JsonLectureRepository


def generate_quizzes_command(
    args: argparse.Namespace,
    repository: JsonLectureRepository,
) -> int:
    record = _load_record(args.lecture_id, repository, stage="quiz")
    if record is None:
        return 0

    print(
        "[LectureQuiz] generate-quizzes start "
        f"{{ lectureId={args.lecture_id}; quizCount={args.quiz_count}; "
        f"seed={args.seed}; questionTypes={','.join(_question_types(args))}; "
        f"openai={args.openai}; quizModel={_quiz_model(args)}; "
        f"promptVersion={_prompt_version(args)} }}"
    )
    if args.openai:
        result = generate_quizzes_with_openai(
            record,
            quiz_count=args.quiz_count,
            seed=args.seed,
            question_types=args.question_type,
            quiz_model=_quiz_model(args),
            prompt_version=_prompt_version(args),
            dry_run=args.dry_run,
            resume=args.resume,
            time_budget_seconds=args.time_budget_seconds,
            batch_size_sections=args.batch_size_sections,
            checkpoint=repository.save,
        )
        if result.dry_run:
            print(format_openai_quiz_dry_run(result))
            return 0
        repository.save(result.record)
        print(format_quiz_generation_result(result.record))
        return 0

    updated = generate_quizzes(
        record,
        quiz_count=args.quiz_count,
        seed=args.seed,
        question_types=args.question_type,
        quiz_model=_quiz_model(args),
        prompt_version=_prompt_version(args),
    )
    if args.dry_run:
        print(
            "[LectureQuiz] local dry-run "
            "{ externalDataBoundary=none; willUpload=false; willSave=false }"
        )
        print(format_quiz_generation_result(updated))
        return 0
    repository.save(updated)
    print(format_quiz_generation_result(updated))
    return 0


def add_quiz_parsers(subparsers: argparse._SubParsersAction) -> None:
    generate_parser = subparsers.add_parser("generate-quizzes")
    generate_parser.add_argument("--lecture-id", required=True)
    generate_parser.add_argument("--quiz-count", type=int, default=DEFAULT_QUIZ_COUNT)
    generate_parser.add_argument("--seed", type=int)
    generate_parser.add_argument(
        "--question-type",
        action="append",
        default=None,
        choices=["multiple_choice", "mcq", "written", "short_answer"],
    )
    generate_parser.add_argument("--quiz-model", default=None)
    generate_parser.add_argument(
        "--prompt-version",
        default=None,
    )
    generate_parser.add_argument("--openai", action="store_true")
    generate_parser.add_argument("--dry-run", action="store_true")
    generate_parser.add_argument("--resume", action="store_true")
    generate_parser.add_argument("--time-budget-seconds", type=float)
    generate_parser.add_argument(
        "--batch-size-sections",
        type=int,
        default=DEFAULT_QUIZ_BATCH_SIZE_SECTIONS,
    )


def format_quiz_generation_result(record) -> str:
    flagged = sum(1 for item in record.quiz_items if item.get("status") == "flagged")
    ready = len(record.quiz_items) - flagged
    plan = record.quiz_metadata.get("generation_plan", {})
    lines = [
        "[LectureQuiz] generate-quizzes success "
        f"{{ lectureId={record.lecture_id}; status={record.status}; "
        f"stage={record.stage}; quizzes={len(record.quiz_items)}; "
        f"ready={ready}; flagged={flagged}; "
        f"seed={record.quiz_metadata.get('seed', '')}; "
        f"source={record.quiz_metadata.get('source', 'unknown')}; "
        f"strategy={plan.get('strategy', 'unknown')}; "
        f"targetQuizzes={plan.get('target_quiz_count', len(record.quiz_items))} }}"
    ]
    for item in record.quiz_items:
        lines.append(
            "- "
            f"{item.get('quiz_id')} "
            f"type={item.get('question_type')} "
            f"status={item.get('status')}"
        )
    return "\n".join(lines)


def _question_types(args: argparse.Namespace) -> list[str]:
    return args.question_type or list(DEFAULT_QUESTION_TYPES)


def _quiz_model(args: argparse.Namespace) -> str:
    if args.quiz_model:
        return args.quiz_model
    return DEFAULT_OPENAI_QUIZ_MODEL if args.openai else DEFAULT_QUIZ_MODEL


def _prompt_version(args: argparse.Namespace) -> str:
    if args.prompt_version:
        return args.prompt_version
    return (
        DEFAULT_OPENAI_QUIZ_PROMPT_VERSION
        if args.openai
        else DEFAULT_QUIZ_PROMPT_VERSION
    )


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

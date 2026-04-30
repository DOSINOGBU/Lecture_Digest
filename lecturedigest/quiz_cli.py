from __future__ import annotations

import argparse

from lecturedigest.errors import ErrorDetail, ValidationError
from lecturedigest.openai_quiz_grading import (
    DEFAULT_OPENAI_QUIZ_GRADING_MODEL,
    DEFAULT_OPENAI_QUIZ_GRADING_PROMPT_VERSION,
    format_openai_quiz_grading_dry_run,
    format_quiz_grading_result,
    grade_quiz_session_with_openai,
)
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
from lecturedigest.quiz_session import (
    session_summary,
    start_quiz_session,
    submit_quiz_answer,
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


def start_quiz_session_command(
    args: argparse.Namespace,
    repository: JsonLectureRepository,
) -> int:
    record = _load_record(args.lecture_id, repository, stage="quiz_session")
    if record is None:
        return 0

    print(
        "[LectureQuiz] start-quiz-session start "
        f"{{ lectureId={args.lecture_id}; count={args.count}; seed={args.seed} }}"
    )
    updated = start_quiz_session(record, count=args.count, seed=args.seed)
    repository.save(updated)
    sessions = updated.quiz_metadata.get("sessions", [])
    session = sessions[-1] if isinstance(sessions, list) and sessions else {}
    print(format_quiz_session_result(updated, str(session.get("session_id") or "")))
    return 0


def submit_quiz_answer_command(
    args: argparse.Namespace,
    repository: JsonLectureRepository,
) -> int:
    record = _load_record(args.lecture_id, repository, stage="quiz_session")
    if record is None:
        return 0

    print(
        "[LectureQuiz] submit-quiz-answer start "
        f"{{ lectureId={args.lecture_id}; sessionId={args.session_id}; "
        f"quizId={args.quiz_id} }}"
    )
    updated = submit_quiz_answer(
        record,
        session_id=args.session_id,
        quiz_id=args.quiz_id,
        answer=args.answer,
    )
    repository.save(updated)
    print(format_quiz_session_result(updated, args.session_id))
    return 0


def grade_quiz_session_command(
    args: argparse.Namespace,
    repository: JsonLectureRepository,
) -> int:
    record = _load_record(args.lecture_id, repository, stage="quiz_grading")
    if record is None:
        return 0
    if not args.openai:
        raise ValidationError(
            ErrorDetail(
                code="openai_required_for_written_grading",
                message="Written quiz grading requires --openai.",
                stage="quiz_grading",
                retryable=False,
            )
        )

    print(
        "[LectureQuiz] grade-quiz-session start "
        f"{{ lectureId={args.lecture_id}; sessionId={args.session_id}; "
        f"openai={args.openai}; quizModel={_quiz_grading_model(args)}; "
        f"promptVersion={_quiz_grading_prompt_version(args)} }}"
    )
    result = grade_quiz_session_with_openai(
        record,
        session_id=args.session_id,
        quiz_model=_quiz_grading_model(args),
        prompt_version=_quiz_grading_prompt_version(args),
        dry_run=args.dry_run,
    )
    if result.dry_run:
        print(format_openai_quiz_grading_dry_run(result))
        return 0
    repository.save(result.record)
    print(format_quiz_grading_result(result.record, args.session_id))
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

    session_parser = subparsers.add_parser("start-quiz-session")
    session_parser.add_argument("--lecture-id", required=True)
    session_parser.add_argument("--count", type=int)
    session_parser.add_argument("--seed", type=int)

    answer_parser = subparsers.add_parser("submit-quiz-answer")
    answer_parser.add_argument("--lecture-id", required=True)
    answer_parser.add_argument("--session-id", required=True)
    answer_parser.add_argument("--quiz-id", required=True)
    answer_parser.add_argument("--answer", required=True)

    grade_parser = subparsers.add_parser("grade-quiz-session")
    grade_parser.add_argument("--lecture-id", required=True)
    grade_parser.add_argument("--session-id", required=True)
    grade_parser.add_argument("--openai", action="store_true")
    grade_parser.add_argument("--dry-run", action="store_true")
    grade_parser.add_argument("--quiz-model", default=None)
    grade_parser.add_argument("--prompt-version", default=None)


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


def format_quiz_session_result(record, session_id: str) -> str:
    summary = session_summary(record, session_id)
    score = summary.get("score", {})
    score_dict = score if isinstance(score, dict) else {}
    return (
        "[LectureQuiz] quiz-session success "
        f"{{ lectureId={record.lecture_id}; sessionId={summary['session_id']}; "
        f"status={summary['status']}; quizzes={summary['quiz_count']}; "
        f"answered={summary['answered_count']}; graded={score_dict.get('graded', 0)}; "
        f"percent={score_dict.get('percent', 0.0)} }}"
    )


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


def _quiz_grading_model(args: argparse.Namespace) -> str:
    if args.quiz_model:
        return args.quiz_model
    return DEFAULT_OPENAI_QUIZ_GRADING_MODEL


def _quiz_grading_prompt_version(args: argparse.Namespace) -> str:
    if args.prompt_version:
        return args.prompt_version
    return DEFAULT_OPENAI_QUIZ_GRADING_PROMPT_VERSION


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

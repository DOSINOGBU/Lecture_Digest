from __future__ import annotations

from dataclasses import dataclass

from lecturedigest.errors import ErrorDetail, QuizGenerationError, ValidationError
from lecturedigest.models import LectureRecord
from lecturedigest.openai_client import OpenAIClient, format_dry_run_result
from lecturedigest.openai_quiz_grading_parse import parse_quiz_grading_response
from lecturedigest.openai_quiz_grading_prompt import (
    DEFAULT_OPENAI_QUIZ_GRADING_MODEL,
    DEFAULT_OPENAI_QUIZ_GRADING_PROMPT_VERSION,
    QUIZ_GRADING_STAGE,
    build_quiz_grading_request,
)
from lecturedigest.openai_types import OpenAIClientResult
from lecturedigest.quiz_session import (
    apply_written_grades,
    mark_grading_failed,
    mark_no_written_answers,
    session_summary,
    written_answers_for_grading,
)

DEFAULT_OPENAI_QUIZ_GRADING_TIMEOUT_SECONDS = 240.0


@dataclass(frozen=True)
class OpenAIQuizGradingResult:
    record: LectureRecord
    client_result: OpenAIClientResult | None = None
    dry_run: bool = False


def grade_quiz_session_with_openai(
    record: LectureRecord,
    *,
    session_id: str,
    client: OpenAIClient | None = None,
    quiz_model: str = DEFAULT_OPENAI_QUIZ_GRADING_MODEL,
    prompt_version: str = DEFAULT_OPENAI_QUIZ_GRADING_PROMPT_VERSION,
    dry_run: bool = False,
    timeout_seconds: float = DEFAULT_OPENAI_QUIZ_GRADING_TIMEOUT_SECONDS,
) -> OpenAIQuizGradingResult:
    normalized_model = _require_text(quiz_model, "quiz_model")
    normalized_prompt = _require_text(prompt_version, "prompt_version")
    written_items = written_answers_for_grading(record, session_id)
    session = _session_payload(record, session_id)
    if not written_items:
        updated = mark_no_written_answers(
            record,
            session_id=session_id,
            grading_metadata={
                "provider": "openai_responses",
                "model": normalized_model,
                "prompt_version": normalized_prompt,
            },
        )
        return OpenAIQuizGradingResult(record=updated, dry_run=dry_run)

    request = build_quiz_grading_request(
        record,
        session=session,
        written_items=written_items,
        model=normalized_model,
        prompt_version=normalized_prompt,
    )
    openai_client = client or OpenAIClient(timeout_seconds=timeout_seconds)
    result = openai_client.send(request, dry_run=dry_run)
    if dry_run:
        return OpenAIQuizGradingResult(record=record, client_result=result, dry_run=True)
    if not result.succeeded:
        return OpenAIQuizGradingResult(
            record=mark_grading_failed(
                record,
                session_id=session_id,
                failure=_failure_payload(result, normalized_model, normalized_prompt),
            ),
            client_result=result,
        )

    grades = parse_quiz_grading_response(result.body)
    updated = apply_written_grades(
        record,
        session_id=session_id,
        grades=grades,
        grading_metadata={
            "provider": "openai_responses",
            "model": normalized_model,
            "prompt_version": normalized_prompt,
            "openai_call": result.metadata.to_dict(),
        },
    )
    return OpenAIQuizGradingResult(record=updated, client_result=result)


def format_openai_quiz_grading_dry_run(result: OpenAIQuizGradingResult) -> str:
    if result.client_result is None:
        return (
            "[LectureQuiz] grade-quiz-session dry-run "
            "{ requests=0; reason=no_written_answers; willUpload=false; willSave=false }"
        )
    return "\n".join(
        [
            format_dry_run_result(result.client_result),
            (
                "[LectureQuiz] grade-quiz-session dry-run "
                "{ requests=1; externalDataBoundary=written answers, expected answers, "
                "rubrics, and source snippets to OpenAI Responses API; "
                "willUpload=false; willSave=false }"
            ),
        ]
    )


def format_quiz_grading_result(record: LectureRecord, session_id: str) -> str:
    summary = session_summary(record, session_id)
    score = summary.get("score", {})
    score_dict = score if isinstance(score, dict) else {}
    return (
        "[LectureQuiz] grade-quiz-session success "
        f"{{ lectureId={record.lecture_id}; sessionId={summary['session_id']}; "
        f"status={summary['status']}; answered={summary['answered_count']}; "
        f"total={summary['quiz_count']}; graded={score_dict.get('graded', 0)}; "
        f"percent={score_dict.get('percent', 0.0)} }}"
    )


def _session_payload(record: LectureRecord, session_id: str) -> dict[str, object]:
    for session in _as_dict_list(record.quiz_metadata.get("sessions", [])):
        if str(session.get("session_id") or "") == session_id:
            return session
    raise QuizGenerationError(
        ErrorDetail(
            code="quiz_session_not_found",
            message=f"Quiz session not found: {session_id}",
            stage=QUIZ_GRADING_STAGE,
            retryable=False,
        )
    )


def _failure_payload(
    result: OpenAIClientResult,
    model: str,
    prompt_version: str,
) -> dict[str, object]:
    issue = result.to_processing_issue(stage=QUIZ_GRADING_STAGE)
    return {
        "provider": "openai_responses",
        "model": model,
        "prompt_version": prompt_version,
        "code": issue.code if issue else "openai_quiz_grading_failed",
        "message": issue.message if issue else "OpenAI quiz grading failed.",
        "retryable": issue.retryable if issue else False,
        "openai_call": result.metadata.to_dict(),
    }


def _require_text(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValidationError(
            ErrorDetail(
                code=f"{field_name}_required",
                message=f"{field_name} is required.",
                stage=QUIZ_GRADING_STAGE,
                retryable=False,
            )
        )
    return normalized


def _as_dict_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]

from __future__ import annotations

import random
from dataclasses import replace
from datetime import datetime, timezone

from lecturedigest.errors import ErrorDetail, QuizGenerationError, ValidationError
from lecturedigest.models import LectureRecord

QUIZ_SESSION_STAGE = "quiz_session"


def start_quiz_session(
    record: LectureRecord,
    *,
    count: int | None = None,
    seed: int | None = None,
) -> LectureRecord:
    ready_items = _ready_quiz_items(record)
    if count is not None and count < 1:
        raise _validation_error(
            "quiz_session_count_invalid",
            "Quiz session count must be at least 1.",
        )
    selected = _selected_quiz_ids(ready_items, count=count, seed=seed)
    session = {
        "session_id": _next_session_id(record),
        "status": "in_progress",
        "seed": seed,
        "quiz_ids": selected,
        "answers": [],
        "score": _score([], selected, record.quiz_items),
        "grading": {"status": "not_started"},
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    return _record_with_session(record, session)


def submit_quiz_answer(
    record: LectureRecord,
    *,
    session_id: str,
    quiz_id: str,
    answer: str,
) -> LectureRecord:
    normalized_answer = answer.strip()
    if not normalized_answer:
        raise _validation_error("quiz_answer_required", "Quiz answer is required.")
    session = _session(record, session_id)
    quiz_item = _quiz_item(record, quiz_id)
    if quiz_id not in _as_string_list(session.get("quiz_ids", [])):
        raise _validation_error(
            "quiz_not_in_session",
            f"Quiz item is not part of this session: {quiz_id}",
        )

    answers = [
        item
        for item in _as_dict_list(session.get("answers", []))
        if str(item.get("quiz_id") or "") != quiz_id
    ]
    answers.append(_answer_payload(quiz_item, normalized_answer))
    updated_session = {
        **session,
        "answers": answers,
        "status": _session_status(answers, _as_string_list(session.get("quiz_ids", []))),
        "score": _score(answers, _as_string_list(session.get("quiz_ids", [])), record.quiz_items),
        "updated_at": _now_iso(),
    }
    return _record_with_session(record, updated_session)


def apply_written_grades(
    record: LectureRecord,
    *,
    session_id: str,
    grades: list[dict[str, object]],
    grading_metadata: dict[str, object],
) -> LectureRecord:
    session = _session(record, session_id)
    grade_lookup = {str(item.get("quiz_id") or ""): item for item in grades}
    answers = []
    for answer in _as_dict_list(session.get("answers", [])):
        quiz_id = str(answer.get("quiz_id") or "")
        grade = grade_lookup.get(quiz_id)
        if grade is None:
            answers.append(answer)
            continue
        answers.append(
            {
                **answer,
                "grading_status": "graded",
                "score": _bounded_score(grade.get("score")),
                "feedback": str(grade.get("feedback") or ""),
                "rubric_results": _as_string_list(grade.get("rubric_results", [])),
                "provider_metadata": grading_metadata,
            }
        )
    updated_session = {
        **session,
        "answers": answers,
        "status": "graded",
        "score": _score(answers, _as_string_list(session.get("quiz_ids", [])), record.quiz_items),
        "grading": {"status": "completed", **grading_metadata},
        "updated_at": _now_iso(),
    }
    return _record_with_session(record, updated_session)


def mark_grading_failed(
    record: LectureRecord,
    *,
    session_id: str,
    failure: dict[str, object],
) -> LectureRecord:
    session = _session(record, session_id)
    updated_session = {
        **session,
        "status": "grading_failed",
        "grading": {"status": "failed", **failure},
        "updated_at": _now_iso(),
    }
    return _record_with_session(record, updated_session)


def mark_no_written_answers(
    record: LectureRecord,
    *,
    session_id: str,
    grading_metadata: dict[str, object],
) -> LectureRecord:
    session = _session(record, session_id)
    updated_session = {
        **session,
        "status": "graded",
        "grading": {"status": "no_written_answers", **grading_metadata},
        "score": _score(
            _as_dict_list(session.get("answers", [])),
            _as_string_list(session.get("quiz_ids", [])),
            record.quiz_items,
        ),
        "updated_at": _now_iso(),
    }
    return _record_with_session(record, updated_session)


def session_summary(record: LectureRecord, session_id: str) -> dict[str, object]:
    session = _session(record, session_id)
    quiz_ids = _as_string_list(session.get("quiz_ids", []))
    answers = _as_dict_list(session.get("answers", []))
    return {
        "session_id": str(session.get("session_id") or ""),
        "status": str(session.get("status") or ""),
        "quiz_count": len(quiz_ids),
        "answered_count": len(answers),
        "score": session.get("score", {}),
    }


def written_answers_for_grading(
    record: LectureRecord,
    session_id: str,
) -> list[dict[str, object]]:
    session = _session(record, session_id)
    quiz_lookup = _quiz_lookup(record)
    pending = []
    for answer in _as_dict_list(session.get("answers", [])):
        quiz_id = str(answer.get("quiz_id") or "")
        quiz_item = quiz_lookup.get(quiz_id)
        if not quiz_item or quiz_item.get("question_type") != "written":
            continue
        pending.append({"answer": answer, "quiz_item": quiz_item})
    return pending


def _ready_quiz_items(record: LectureRecord) -> list[dict[str, object]]:
    if not record.quiz_items:
        raise _quiz_error(
            "quizzes_required",
            "Generate quizzes before starting a quiz session.",
        )
    ready_items = [
        item
        for item in record.quiz_items
        if isinstance(item, dict) and item.get("status") == "ready"
    ]
    if not ready_items:
        raise _quiz_error(
            "ready_quizzes_required",
            "A quiz session requires at least one ready quiz item.",
        )
    return ready_items


def _selected_quiz_ids(
    ready_items: list[dict[str, object]],
    *,
    count: int | None,
    seed: int | None,
) -> list[str]:
    rng = random.Random(seed)
    items = list(ready_items)
    rng.shuffle(items)
    limit = min(count or len(items), len(items))
    return [str(item.get("quiz_id") or "") for item in items[:limit]]


def _answer_payload(quiz_item: dict[str, object], answer: str) -> dict[str, object]:
    question_type = str(quiz_item.get("question_type") or "")
    payload = {
        "quiz_id": str(quiz_item.get("quiz_id") or ""),
        "question_type": question_type,
        "answer": answer,
        "submitted_at": _now_iso(),
    }
    if question_type == "multiple_choice":
        correct = _is_correct_choice(quiz_item, answer)
        return {
            **payload,
            "grading_status": "graded",
            "is_correct": correct,
            "score": 1.0 if correct else 0.0,
            "feedback": "Correct." if correct else "Review the expected answer.",
        }
    return {
        **payload,
        "grading_status": "pending_ai_grading",
        "is_correct": None,
        "score": None,
        "feedback": "",
    }


def _is_correct_choice(quiz_item: dict[str, object], answer: str) -> bool:
    expected = str(quiz_item.get("correct_answer") or "").strip()
    normalized = answer.strip()
    if normalized.lower() == expected.lower():
        return True
    for choice in _as_dict_list(quiz_item.get("choices", [])):
        if str(choice.get("text") or "").strip().lower() == normalized.lower():
            return choice.get("is_correct") is True
    return False


def _session_status(answers: list[dict[str, object]], quiz_ids: list[str]) -> str:
    answered_ids = {str(item.get("quiz_id") or "") for item in answers}
    return "answered" if all(quiz_id in answered_ids for quiz_id in quiz_ids) else "in_progress"


def _score(
    answers: list[dict[str, object]],
    quiz_ids: list[str],
    quiz_items: list[dict[str, object]],
) -> dict[str, object]:
    quiz_lookup = {str(item.get("quiz_id") or ""): item for item in quiz_items}
    graded = [item for item in answers if item.get("score") is not None]
    total_points = sum(float(item.get("score") or 0.0) for item in graded)
    mcq_answers = [
        item
        for item in answers
        if quiz_lookup.get(str(item.get("quiz_id") or ""), {}).get("question_type")
        == "multiple_choice"
    ]
    written_graded = [
        item
        for item in answers
        if quiz_lookup.get(str(item.get("quiz_id") or ""), {}).get("question_type")
        == "written"
        and item.get("score") is not None
    ]
    return {
        "answered": len(answers),
        "graded": len(graded),
        "total": len(quiz_ids),
        "points": round(total_points, 3),
        "percent": round(total_points / len(quiz_ids) * 100, 1) if quiz_ids else 0.0,
        "multiple_choice_correct": sum(1 for item in mcq_answers if item.get("is_correct")),
        "written_graded": len(written_graded),
    }


def _record_with_session(
    record: LectureRecord,
    session: dict[str, object],
) -> LectureRecord:
    sessions = [
        item
        for item in _sessions(record)
        if str(item.get("session_id") or "") != str(session.get("session_id") or "")
    ]
    sessions.append(session)
    return replace(
        record,
        status="quiz_session_ready",
        stage=QUIZ_SESSION_STAGE,
        quiz_metadata={**record.quiz_metadata, "sessions": sessions},
    )


def _session(record: LectureRecord, session_id: str) -> dict[str, object]:
    for session in _sessions(record):
        if str(session.get("session_id") or "") == session_id:
            return session
    raise _validation_error("quiz_session_not_found", f"Quiz session not found: {session_id}")


def _sessions(record: LectureRecord) -> list[dict[str, object]]:
    sessions = record.quiz_metadata.get("sessions", [])
    return _as_dict_list(sessions)


def _quiz_item(record: LectureRecord, quiz_id: str) -> dict[str, object]:
    item = _quiz_lookup(record).get(quiz_id)
    if item is None:
        raise _validation_error("quiz_not_found", f"Quiz item not found: {quiz_id}")
    return item


def _quiz_lookup(record: LectureRecord) -> dict[str, dict[str, object]]:
    return {
        str(item.get("quiz_id") or ""): item
        for item in record.quiz_items
        if isinstance(item, dict)
    }


def _next_session_id(record: LectureRecord) -> str:
    return f"quiz-session-{len(_sessions(record)) + 1:03d}"


def _bounded_score(value: object) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        score = 0.0
    return max(0.0, min(1.0, score))


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _as_dict_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _as_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]


def _quiz_error(code: str, message: str) -> QuizGenerationError:
    return QuizGenerationError(
        ErrorDetail(code=code, message=message, stage=QUIZ_SESSION_STAGE, retryable=False)
    )


def _validation_error(code: str, message: str) -> ValidationError:
    return ValidationError(
        ErrorDetail(code=code, message=message, stage=QUIZ_SESSION_STAGE, retryable=False)
    )

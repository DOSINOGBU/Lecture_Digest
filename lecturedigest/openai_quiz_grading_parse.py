from __future__ import annotations

import json

from lecturedigest.errors import ErrorDetail, QuizGenerationError
from lecturedigest.openai_quiz_grading_prompt import QUIZ_GRADING_STAGE


def parse_quiz_grading_response(data: bytes | str) -> list[dict[str, object]]:
    payload = _decode_json(data)
    if "grades" not in payload:
        response_text = _extract_response_text(payload)
        if response_text is None:
            raise _grading_error(
                "openai_quiz_grading_response_malformed",
                "OpenAI quiz grading response did not include grades.",
            )
        payload = _decode_json(response_text)

    raw_grades = payload.get("grades")
    if not isinstance(raw_grades, list):
        raise _grading_error(
            "openai_quiz_grading_response_malformed",
            "OpenAI quiz grading response `grades` must be a list.",
        )
    return [_grade_payload(item) for item in raw_grades if isinstance(item, dict)]


def _grade_payload(item: dict[str, object]) -> dict[str, object]:
    return {
        "quiz_id": str(item.get("quiz_id") or "").strip(),
        "score": _bounded_score(item.get("score")),
        "feedback": str(item.get("feedback") or "").strip(),
        "rubric_results": _as_string_list(item.get("rubric_results", [])),
    }


def _decode_json(data: bytes | str) -> dict[str, object]:
    text = data.decode("utf-8", errors="replace") if isinstance(data, bytes) else data
    try:
        payload = json.loads(_strip_json_fence(text.strip()))
    except json.JSONDecodeError as exc:
        raise _grading_error(
            "openai_quiz_grading_response_invalid_json",
            f"OpenAI quiz grading response JSON could not be parsed: {exc.msg}",
        ) from exc
    if not isinstance(payload, dict):
        raise _grading_error(
            "openai_quiz_grading_response_malformed",
            "OpenAI quiz grading response must be a JSON object.",
        )
    return payload


def _extract_response_text(payload: dict[str, object]) -> str | None:
    output_text = payload.get("output_text")
    if isinstance(output_text, str):
        return output_text
    output = payload.get("output", [])
    if not isinstance(output, list):
        return None
    for item in output:
        if not isinstance(item, dict):
            continue
        content = item.get("content", [])
        if not isinstance(content, list):
            continue
        for content_item in content:
            if not isinstance(content_item, dict):
                continue
            text = content_item.get("text", content_item.get("output_text"))
            if isinstance(text, str):
                return text
    return None


def _strip_json_fence(text: str) -> str:
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if len(lines) >= 3 and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip()
    return text


def _bounded_score(value: object) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        score = 0.0
    return max(0.0, min(1.0, score))


def _as_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]


def _grading_error(code: str, message: str) -> QuizGenerationError:
    return QuizGenerationError(
        ErrorDetail(
            code=code,
            message=message,
            stage=QUIZ_GRADING_STAGE,
            retryable=False,
        )
    )

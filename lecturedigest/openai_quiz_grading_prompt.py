from __future__ import annotations

import json

from lecturedigest.models import LectureRecord
from lecturedigest.openai_client import json_body
from lecturedigest.openai_quiz_prompt import OPENAI_QUIZ_ENDPOINT
from lecturedigest.openai_types import OpenAIRequest

OPENAI_QUIZ_GRADING_USE_CASE = "quiz_written_grading"
DEFAULT_OPENAI_QUIZ_GRADING_MODEL = "gpt-4.1"
DEFAULT_OPENAI_QUIZ_GRADING_PROMPT_VERSION = "openai-quiz-grading-v1"
QUIZ_GRADING_STAGE = "quiz_grading"

OPENAI_QUIZ_GRADING_PROMPT = """You are LectureDigest's quiz tutor.
Grade written quiz answers as learning feedback, not as a high-stakes exam.
Return JSON only. Do not wrap the JSON in Markdown fences.

Hard requirements:
- Grade only the submitted answer against the expected answer and rubric.
- Use approved note/source context only; do not add new facts.
- Score must be between 0 and 1.
- Feedback must be concise, practical, and written in Korean.
- Mention what is correct and what to improve.
- Do not include source labels, segment ids, or timestamps in feedback.

Response shape:
{"grades":[{"quiz_id":"...","score":0.0,"feedback":"...","rubric_results":["..."]}]}"""


def build_quiz_grading_request(
    record: LectureRecord,
    *,
    session: dict[str, object],
    written_items: list[dict[str, object]],
    model: str = DEFAULT_OPENAI_QUIZ_GRADING_MODEL,
    prompt_version: str = DEFAULT_OPENAI_QUIZ_GRADING_PROMPT_VERSION,
) -> OpenAIRequest:
    payload = {
        "model": model,
        "input": [
            {
                "role": "system",
                "content": [{"type": "input_text", "text": OPENAI_QUIZ_GRADING_PROMPT}],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": json.dumps(
                            _grading_contract(record, session, written_items),
                            ensure_ascii=False,
                        ),
                    }
                ],
            },
        ],
        "text": {"format": {"type": "json_object"}},
        "max_output_tokens": _max_output_tokens(written_items),
    }
    body = json_body(payload)
    return OpenAIRequest(
        endpoint=OPENAI_QUIZ_ENDPOINT,
        use_case=OPENAI_QUIZ_GRADING_USE_CASE,
        model=model,
        prompt_version=prompt_version,
        body=body,
        input_size_bytes=len(body),
        external_data_boundary=(
            "written quiz answers, expected answers, rubrics, and source snippets "
            "to OpenAI Responses API"
        ),
    )


def _grading_contract(
    record: LectureRecord,
    session: dict[str, object],
    written_items: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "contract": {
            "language": "ko",
            "session_id": str(session.get("session_id") or ""),
            "grading_mode": "learning_feedback",
            "score_range": "0.0_to_1.0",
            "quality_rules": [
                "grade_against_expected_answer_and_rubric",
                "do_not_add_unsupported_facts",
                "feedback_must_not_include_source_or_timestamp",
            ],
        },
        "lecture": {
            "lecture_id": record.lecture_id,
            "title": record.title,
            "category": record.category,
        },
        "written_answers": [_written_payload(item) for item in written_items],
    }


def _written_payload(item: dict[str, object]) -> dict[str, object]:
    answer = item["answer"]
    quiz_item = item["quiz_item"]
    source = quiz_item.get("source", {})
    source_dict = source if isinstance(source, dict) else {}
    return {
        "quiz_id": str(quiz_item.get("quiz_id") or ""),
        "question": str(quiz_item.get("question") or ""),
        "student_answer": str(answer.get("answer") or ""),
        "expected_answer": str(quiz_item.get("expected_answer") or ""),
        "rubric": _as_string_list(quiz_item.get("rubric", [])),
        "explanation": str(quiz_item.get("explanation") or ""),
        "source_segment_ids": _as_string_list(source_dict.get("segment_ids", [])),
    }


def _max_output_tokens(written_items: list[dict[str, object]]) -> int:
    return min(4000, max(1200, len(written_items) * 500))


def _as_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]

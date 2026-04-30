from __future__ import annotations

import json
import re

from lecturedigest.errors import ErrorDetail, QuizGenerationError
from lecturedigest.models import LectureRecord, TranscriptSegment
from lecturedigest.openai_quiz_prompt import (
    OPENAI_QUIZ_ENDPOINT,
    OPENAI_QUIZ_USE_CASE,
    QUIZ_STAGE,
)
from lecturedigest.openai_types import OpenAIClientResult
from lecturedigest.quiz_policy import SUPPORTED_QUESTION_TYPES
from lecturedigest.quiz_validation import validate_quiz_item

SEGMENT_ID_PATTERN = re.compile(r"seg-[0-9A-Za-z_-]+", re.IGNORECASE)
DIFFICULTIES = {"beginner", "intermediate", "advanced"}


def parse_quiz_response(
    data: bytes | str,
    *,
    record: LectureRecord,
    sections: list[dict[str, object]],
    ready_cards: list[dict[str, object]],
    question_types: list[str],
    model: str,
    prompt_version: str,
    client_result: OpenAIClientResult,
) -> list[dict[str, object]]:
    payload = _decode_json(data)
    if "quizzes" not in payload:
        response_text = _extract_response_text(payload)
        if response_text is None:
            raise _quiz_error(
                "openai_quiz_response_malformed",
                "OpenAI quiz response did not include quizzes.",
            )
        payload = _decode_json(response_text)

    raw_items = payload.get("quizzes")
    if not isinstance(raw_items, list):
        raise _quiz_error(
            "openai_quiz_response_malformed",
            "OpenAI quiz response `quizzes` must be a list.",
        )

    section_lookup = _sections_by_id(sections)
    card_lookup = _cards_by_id(ready_cards)
    segment_lookup = {segment.segment_id: segment for segment in record.segments}
    return [
        _quiz_from_payload(
            item,
            record=record,
            section_lookup=section_lookup,
            card_lookup=card_lookup,
            segment_lookup=segment_lookup,
            question_types=question_types,
            model=model,
            prompt_version=prompt_version,
            client_result=client_result,
        )
        for item in raw_items
        if isinstance(item, dict)
    ]


def _quiz_from_payload(
    item: dict[str, object],
    *,
    record: LectureRecord,
    section_lookup: dict[str, dict[str, object]],
    card_lookup: dict[str, dict[str, object]],
    segment_lookup: dict[str, TranscriptSegment],
    question_types: list[str],
    model: str,
    prompt_version: str,
    client_result: OpenAIClientResult,
) -> dict[str, object]:
    question_type = str(item.get("question_type") or "multiple_choice").strip()
    unsupported_type = (
        question_type not in SUPPORTED_QUESTION_TYPES or question_type not in question_types
    )
    if unsupported_type:
        question_type = "multiple_choice"
    note_section_id = str(item.get("note_section_id") or "").strip()
    source_card_ids = _source_card_ids(item, card_lookup)
    section = section_lookup.get(note_section_id, {})
    source_ids = _source_segment_ids(item)
    source = _source_payload(record, source_ids, segment_lookup, section)
    difficulty = _difficulty(item.get("difficulty"))
    quiz_item = {
        "quiz_id": _quiz_id(record, question_type, item),
        "question_type": question_type,
        "question": str(item.get("question") or "").strip(),
        "choices": _choices(item, question_type),
        "correct_answer": str(item.get("correct_answer") or "").strip(),
        "expected_answer": str(item.get("expected_answer") or "").strip(),
        "rubric": _string_list(item.get("rubric", [])),
        "explanation": str(item.get("explanation") or "").strip(),
        "source": source,
        "source_card_ids": source_card_ids,
        "source_note_candidate_id": str(record.approved_note.get("candidate_id") or ""),
        "difficulty": difficulty,
        "tags": _tags(record, question_type, difficulty, source_card_ids),
        "input_origin": "openai",
        "model": model,
        "prompt_version": prompt_version,
        "provider_metadata": {
            "provider": "openai_responses",
            "endpoint": client_result.metadata.endpoint or OPENAI_QUIZ_ENDPOINT,
            "use_case": client_result.metadata.use_case or OPENAI_QUIZ_USE_CASE,
            "openai_call": client_result.metadata.to_dict(),
        },
    }
    if unsupported_type:
        quiz_item["unsupported_fact"] = True
    return validate_quiz_item(quiz_item)


def _choices(item: dict[str, object], question_type: str) -> list[dict[str, object]]:
    if question_type != "multiple_choice":
        return []
    raw_choices = item.get("choices", [])
    if not isinstance(raw_choices, list):
        return []
    choices = []
    labels = ["A", "B", "C", "D"]
    for index, raw in enumerate(raw_choices[:4]):
        if isinstance(raw, dict):
            choice_id = str(raw.get("id") or labels[index]).strip() or labels[index]
            text = str(raw.get("text") or "").strip()
            is_correct = raw.get("is_correct") is True
        else:
            choice_id = labels[index]
            text = str(raw).strip()
            is_correct = False
        choices.append({"id": choice_id, "text": text, "is_correct": is_correct})
    return choices


def _source_segment_ids(item: dict[str, object]) -> list[str]:
    found = []
    raw_ids = item.get("source_segment_ids", [])
    if isinstance(raw_ids, list):
        for raw in raw_ids:
            matches = SEGMENT_ID_PATTERN.findall(str(raw))
            found.extend(matches or [str(raw)])
    unique = []
    for segment_id in found:
        if segment_id and segment_id not in unique:
            unique.append(segment_id)
    return unique


def _source_card_ids(
    item: dict[str, object],
    card_lookup: dict[str, dict[str, object]],
) -> list[str]:
    raw_ids = item.get("source_card_ids", [])
    if not isinstance(raw_ids, list):
        return []
    unique = []
    for raw in raw_ids:
        card_id = str(raw or "").strip()
        if card_id and card_id in card_lookup and card_id not in unique:
            unique.append(card_id)
    return unique


def _source_payload(
    record: LectureRecord,
    segment_ids: list[str],
    segment_lookup: dict[str, TranscriptSegment],
    section: dict[str, object],
) -> dict[str, object]:
    mapped_segments = [segment_lookup[item] for item in segment_ids if item in segment_lookup]
    start_ts = ""
    end_ts = ""
    if mapped_segments:
        start_ts = mapped_segments[0].start_ts
        end_ts = mapped_segments[-1].end_ts
    return {
        "lecture_id": record.lecture_id,
        "lecture_title": record.lecture_title or record.title,
        "title": record.title,
        "chapter": str(section.get("chapter") or "unassigned"),
        "segment_ids": segment_ids,
        "start_ts": start_ts,
        "end_ts": end_ts,
        "jump_link": _jump_link(record, start_ts),
        "mapping_status": "mapped" if segment_ids and start_ts else "flagged",
    }


def _sections_by_id(sections: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    result = {}
    for section in sections:
        for key in ("note_section_id", "section_key"):
            value = str(section.get(key) or "")
            if value and value not in result:
                result[value] = section
    return result


def _cards_by_id(cards: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    result = {}
    for card in cards:
        card_id = str(card.get("card_id") or "")
        if card_id:
            result[card_id] = card
    return result


def _difficulty(value: object) -> str:
    normalized = str(value or "beginner").strip()
    return normalized if normalized in DIFFICULTIES else "beginner"


def _tags(
    record: LectureRecord,
    question_type: str,
    difficulty: str,
    source_card_ids: list[str],
) -> list[str]:
    tags = [
        "lecturedigest",
        "quiz",
        question_type,
        f"difficulty_{difficulty}",
        "source_ready_cards" if source_card_ids else "source_approved_note",
        record.category,
    ]
    return [tag.replace(" ", "_") for tag in tags if tag]


def _quiz_id(record: LectureRecord, question_type: str, item: dict[str, object]) -> str:
    explicit = str(item.get("quiz_id") or "").strip()
    if explicit:
        return explicit
    seed = f"{question_type}:{item.get('note_section_id', '')}:{item.get('question', '')}"
    safe = re.sub(r"[^0-9A-Za-z_-]+", "-", seed)[:90].strip("-")
    return f"{record.lecture_id}:openai-quiz:{safe or question_type}"


def _jump_link(record: LectureRecord, start_ts: str) -> str:
    seconds = 0
    if start_ts:
        parts = start_ts.replace(",", ".").split(":")
        if len(parts) == 3:
            try:
                seconds = (
                    int(parts[0]) * 3600
                    + int(parts[1]) * 60
                    + round(float(parts[2]))
                )
            except ValueError:
                seconds = 0
    return f"lecturedigest://lecture/{record.lecture_id}?t={seconds}"


def _decode_json(data: bytes | str) -> dict[str, object]:
    text = data.decode("utf-8", errors="replace") if isinstance(data, bytes) else data
    try:
        payload = json.loads(_strip_json_fence(text.strip()))
    except json.JSONDecodeError as exc:
        raise _quiz_error(
            "openai_quiz_response_invalid_json",
            f"OpenAI quiz response JSON could not be parsed: {exc.msg}",
        ) from exc
    if not isinstance(payload, dict):
        raise _quiz_error(
            "openai_quiz_response_malformed",
            "OpenAI quiz response must be a JSON object.",
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


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]


def _quiz_error(code: str, message: str) -> QuizGenerationError:
    return QuizGenerationError(
        ErrorDetail(
            code=code,
            message=message,
            stage=QUIZ_STAGE,
            retryable=False,
        )
    )

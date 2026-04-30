from __future__ import annotations

import random
import re
from dataclasses import replace

from lecturedigest.errors import ErrorDetail, QuizGenerationError, ValidationError
from lecturedigest.models import LectureRecord, TranscriptSegment

DEFAULT_QUIZ_MODEL = "local-quiz-v1"
DEFAULT_QUIZ_PROMPT_VERSION = "random-quiz-v1"
DEFAULT_QUIZ_COUNT = 8
DEFAULT_QUESTION_TYPES = ("multiple_choice", "written")
QUESTION_TYPE_ALIASES = {
    "mcq": "multiple_choice",
    "multiple_choice": "multiple_choice",
    "written": "written",
    "short_answer": "written",
}
def generate_quizzes(
    record: LectureRecord,
    *,
    quiz_count: int = DEFAULT_QUIZ_COUNT,
    seed: int | None = None,
    question_types: list[str] | None = None,
    quiz_model: str = DEFAULT_QUIZ_MODEL,
    prompt_version: str = DEFAULT_QUIZ_PROMPT_VERSION,
) -> LectureRecord:
    if quiz_count <= 0:
        raise ValidationError(
            ErrorDetail(
                code="quiz_count_invalid",
                message="quiz_count must be at least 1.",
                stage="quiz",
                retryable=False,
            )
        )
    normalized_types = _normalize_question_types(question_types)
    normalized_model = _require_text(quiz_model, "quiz_model")
    normalized_prompt = _require_text(prompt_version, "prompt_version")
    sections = _approved_note_sections(record)
    segment_lookup = {segment.segment_id: segment for segment in record.segments}
    rng = random.Random(seed)

    candidates: list[dict[str, object]] = []
    for section in sections:
        if "multiple_choice" in normalized_types:
            candidates.append(_multiple_choice_item(record, section, segment_lookup, rng))
        if "written" in normalized_types:
            candidates.append(_written_item(record, section, segment_lookup))

    rng.shuffle(candidates)
    quiz_items = candidates[:quiz_count]
    ready_count = sum(1 for item in quiz_items if item["status"] == "ready")
    flagged_count = len(quiz_items) - ready_count
    return replace(
        record,
        status="quizzes_ready",
        stage="quiz",
        quiz_items=quiz_items,
        quiz_metadata={
            "model": normalized_model,
            "prompt_version": normalized_prompt,
            "quiz_count": len(quiz_items),
            "ready_count": ready_count,
            "flagged_count": flagged_count,
            "seed": seed,
            "question_types": normalized_types,
            "source": "approved_note",
        },
    )


def _multiple_choice_item(
    record: LectureRecord,
    section: dict[str, object],
    segment_lookup: dict[str, TranscriptSegment],
    rng: random.Random,
) -> dict[str, object]:
    source = _source_payload(record, section, segment_lookup)
    correct = _answer_text(section)
    choices = _choice_payloads(correct, _distractors(section, record.note_sections), rng)
    item = {
        "quiz_id": _quiz_id(record, section, "multiple_choice"),
        "question_type": "multiple_choice",
        "question": f"Which statement best matches {_section_title(section)}?",
        "choices": choices,
        "correct_answer": _correct_choice_id(choices),
        "expected_answer": correct,
        "explanation": _explanation(section, source),
        "source": source,
    }
    return _with_validation(item)


def _written_item(
    record: LectureRecord,
    section: dict[str, object],
    segment_lookup: dict[str, TranscriptSegment],
) -> dict[str, object]:
    source = _source_payload(record, section, segment_lookup)
    answer = _answer_text(section)
    item = {
        "quiz_id": _quiz_id(record, section, "written"),
        "question_type": "written",
        "question": f"Explain the key idea of {_section_title(section)} in your own words.",
        "choices": [],
        "correct_answer": "",
        "expected_answer": answer,
        "rubric": [
            "mentions the core concept",
            "uses the cited lecture context",
            "does not add unsupported claims",
        ],
        "explanation": _explanation(section, source),
        "source": source,
    }
    return _with_validation(item)


def _approved_note_sections(record: LectureRecord) -> list[dict[str, object]]:
    if record.approved_note.get("status") != "approved":
        raise QuizGenerationError(
            ErrorDetail(
                code="approved_note_required",
                message="An approved note is required before generating quizzes.",
                stage="quiz",
                retryable=False,
            )
        )
    sections = record.note_sections or _as_dict_list(record.approved_note.get("sections", []))
    if not sections:
        raise QuizGenerationError(
            ErrorDetail(
                code="note_sections_required",
                message="Approved note sections are required before generating quizzes.",
                stage="quiz",
                retryable=False,
            )
        )
    return sections


def _normalize_question_types(question_types: list[str] | None) -> list[str]:
    raw_types = question_types or list(DEFAULT_QUESTION_TYPES)
    normalized = []
    for item in raw_types:
        key = item.strip().lower()
        if key not in QUESTION_TYPE_ALIASES:
            raise ValidationError(
                ErrorDetail(
                    code="quiz_question_type_invalid",
                    message="question_types must include multiple_choice and/or written.",
                    stage="quiz",
                    retryable=False,
                )
            )
        mapped = QUESTION_TYPE_ALIASES[key]
        if mapped not in normalized:
            normalized.append(mapped)
    if not normalized:
        raise ValidationError(
            ErrorDetail(
                code="quiz_question_type_required",
                message="At least one question type is required.",
                stage="quiz",
                retryable=False,
            )
        )
    return normalized


def _choice_payloads(
    correct: str,
    distractors: list[str],
    rng: random.Random,
) -> list[dict[str, object]]:
    texts = [correct, *_unique_distractors(correct, distractors)]
    while len(texts) < 4:
        texts.append(f"Review the cited segment before choosing option {len(texts) + 1}.")
    texts = texts[:4]
    rng.shuffle(texts)
    labels = ["A", "B", "C", "D"]
    return [
        {
            "id": label,
            "text": text,
            "is_correct": text == correct,
        }
        for label, text in zip(labels, texts)
    ]


def _unique_distractors(correct: str, candidates: list[str]) -> list[str]:
    result = []
    normalized_correct = correct.strip().lower()
    for candidate in candidates:
        text = candidate.strip()
        if not text or text.lower() == normalized_correct or text in result:
            continue
        result.append(text)
        if len(result) == 3:
            break
    return result


def _distractors(
    section: dict[str, object],
    sections: list[dict[str, object]],
) -> list[str]:
    section_id = str(section.get("note_section_id") or section.get("section_key") or "")
    candidates = []
    for other in sections:
        other_id = str(other.get("note_section_id") or other.get("section_key") or "")
        if other_id == section_id:
            continue
        candidates.append(_answer_text(other))
    candidates.extend(
        [
            "The lecture does not provide enough evidence for this choice.",
            "This choice is unrelated to the cited section.",
            "This choice only repeats the title without explaining the concept.",
        ]
    )
    return candidates


def _source_payload(
    record: LectureRecord,
    section: dict[str, object],
    segment_lookup: dict[str, TranscriptSegment],
) -> dict[str, object]:
    segment_ids = [str(value) for value in _as_list(section.get("segment_ids", []))]
    mapped_segments = [segment_lookup[item] for item in segment_ids if item in segment_lookup]
    start_ts = str(section.get("start_ts") or "")
    end_ts = str(section.get("end_ts") or "")
    if mapped_segments:
        start_ts = start_ts or mapped_segments[0].start_ts
        end_ts = end_ts or mapped_segments[-1].end_ts
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


def _with_validation(item: dict[str, object]) -> dict[str, object]:
    failed = []
    if not str(item.get("question") or "").strip():
        failed.append("question_required")
    source = item.get("source", {})
    if not isinstance(source, dict) or source.get("mapping_status") != "mapped":
        failed.append("source_mapping_required")
    if item.get("question_type") == "multiple_choice":
        choices = _as_dict_list(item.get("choices", []))
        correct_count = sum(1 for choice in choices if choice.get("is_correct") is True)
        if len(choices) != 4:
            failed.append("four_choices_required")
        if correct_count != 1:
            failed.append("single_correct_choice_required")
    if item.get("question_type") == "written":
        if not str(item.get("expected_answer") or "").strip():
            failed.append("expected_answer_required")
        if not _as_list(item.get("rubric", [])):
            failed.append("rubric_required")
    return {
        **item,
        "status": "ready" if not failed else "flagged",
        "validation": {
            "status": "passed" if not failed else "flagged",
            "failed_rules": failed,
        },
    }


def _correct_choice_id(choices: list[dict[str, object]]) -> str:
    for choice in choices:
        if choice["is_correct"]:
            return str(choice["id"])
    return ""


def _quiz_id(record: LectureRecord, section: dict[str, object], question_type: str) -> str:
    section_id = str(section.get("note_section_id") or section.get("section_key"))
    safe_section = re.sub(r"[^0-9A-Za-z_-]+", "-", section_id).strip("-")
    return f"{record.lecture_id}:{safe_section}:{question_type}"


def _section_title(section: dict[str, object]) -> str:
    return str(section.get("title") or section.get("section_key") or "note section")


def _section_text(section: dict[str, object]) -> str:
    return str(section.get("text") or section.get("body") or "").strip()


def _answer_text(section: dict[str, object]) -> str:
    text = _section_text(section)
    first_sentence = _first_sentence(text)
    return _snippet(first_sentence or text or _section_title(section), 240)


def _first_sentence(text: str) -> str:
    for part in re.split(r"(?<=[.!?])\s+", text):
        cleaned = part.strip(" -")
        if cleaned:
            return cleaned
    return ""


def _explanation(section: dict[str, object], source: dict[str, object]) -> str:
    return f"{_snippet(_section_text(section), 320)}\n\n{_source_label(source)}"


def _source_label(source: object) -> str:
    if not isinstance(source, dict):
        return "source: unmapped"
    segment_ids = ", ".join(str(item) for item in _as_list(source.get("segment_ids", [])))
    if not segment_ids:
        return "source: unmapped"
    return (
        f"source: {segment_ids} @ {source.get('start_ts', '')}-"
        f"{source.get('end_ts', '')}"
    )


def _jump_link(record: LectureRecord, start_ts: str) -> str:
    seconds = 0
    if start_ts:
        parts = start_ts.replace(",", ".").split(":")
        if len(parts) == 3:
            try:
                seconds = int(parts[0]) * 3600 + int(parts[1]) * 60 + round(float(parts[2]))
            except ValueError:
                seconds = 0
    return f"lecturedigest://lecture/{record.lecture_id}?t={seconds}"


def _snippet(text: str, max_chars: int) -> str:
    compact = " ".join(text.split())
    if len(compact) <= max_chars:
        return compact
    trimmed = compact[: max_chars + 1].rsplit(" ", maxsplit=1)[0]
    return f"{trimmed or compact[:max_chars]}..."


def _require_text(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValidationError(
            ErrorDetail(
                code=f"{field_name}_required",
                message=f"{field_name} is required.",
                stage="quiz",
                retryable=False,
            )
        )
    return normalized


def _as_dict_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _as_list(value: object) -> list[object]:
    if not isinstance(value, list):
        return []
    return value

from __future__ import annotations

import re

SOURCE_ARTIFACT_PATTERN = re.compile(r"\bsource:\s*|seg-\d+|@\s*\d{2}:\d{2}:\d{2}", re.IGNORECASE)
WORD_PATTERN = re.compile(r"[0-9A-Za-z\uac00-\ud7a3]+")
BROAD_QUESTION_PATTERNS = (
    "summarize the whole",
    "explain everything",
    "what is the key idea",
    "what are the main points",
    "what should you remember",
)


def validate_quiz_item(item: dict[str, object]) -> dict[str, object]:
    failed = []
    question = _text(item.get("question"))
    expected_answer = _text(item.get("expected_answer"))

    if not question:
        failed.append("question_required")
    if SOURCE_ARTIFACT_PATTERN.search(question):
        failed.append("source_visible_in_question")

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
        if not expected_answer:
            failed.append("expected_answer_required")
    elif item.get("question_type") == "written":
        if not expected_answer:
            failed.append("expected_answer_required")
        if not _as_list(item.get("rubric", [])):
            failed.append("rubric_required")

    if _answer_leaked_in_question(question, expected_answer):
        failed.append("answer_leaked_in_question")
    if _too_broad(question):
        failed.append("too_broad")
    if item.get("unsupported_fact"):
        failed.append("unsupported_fact")

    return _with_status(item, _unique(failed))


def remove_duplicate_quiz_items(
    items: list[dict[str, object]],
) -> tuple[list[dict[str, object]], int]:
    seen = set()
    unique_items = []
    duplicate_count = 0
    for item in items:
        signature = quiz_signature(item)
        if signature in seen:
            duplicate_count += 1
            continue
        seen.add(signature)
        unique_items.append(item)
    return unique_items, duplicate_count


def quiz_signature(item: dict[str, object]) -> str:
    question_type = str(item.get("question_type") or "")
    question = _normalize_for_match(item.get("question") or "")
    source = item.get("source", {})
    segment_ids = []
    if isinstance(source, dict):
        segment_ids = [str(value) for value in _as_list(source.get("segment_ids", []))]
    return f"{question_type}:{question}:{','.join(segment_ids)}"


def _with_status(
    item: dict[str, object],
    failed_rules: list[str],
) -> dict[str, object]:
    status = "ready" if not failed_rules else "flagged"
    return {
        **item,
        "status": status,
        "validation": {
            "status": "passed" if not failed_rules else "flagged",
            "failed_rules": failed_rules,
        },
    }


def _answer_leaked_in_question(question: str, expected_answer: str) -> bool:
    normalized_question = _normalize_for_match(question)
    normalized_answer = _normalize_for_match(expected_answer)
    if not normalized_question or not normalized_answer:
        return False
    answer_words = normalized_answer.split()
    if len(answer_words) < 4:
        return False
    answer_phrase = " ".join(answer_words[:10])
    return len(answer_phrase) >= 24 and answer_phrase in normalized_question


def _too_broad(question: str) -> bool:
    lower = question.lower()
    return any(pattern in lower for pattern in BROAD_QUESTION_PATTERNS)


def _text(value: object) -> str:
    return str(value or "").strip()


def _normalize_for_match(value: object) -> str:
    tokens = WORD_PATTERN.findall(str(value).lower())
    return " ".join(tokens)


def _as_dict_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _as_list(value: object) -> list[object]:
    if not isinstance(value, list):
        return []
    return value


def _unique(values: list[str]) -> list[str]:
    result = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result

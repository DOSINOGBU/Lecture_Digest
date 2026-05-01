from __future__ import annotations

import re
from dataclasses import dataclass

from lecturedigest.errors import ErrorDetail, ValidationError
from lecturedigest.models import LectureRecord

SUPPORTED_QUESTION_TYPES = ("multiple_choice", "written")
DEFAULT_QUESTION_TYPES = SUPPORTED_QUESTION_TYPES
DEFAULT_QUIZ_COUNT: int | None = None
QUESTION_TYPE_ALIASES = {
    "mcq": "multiple_choice",
    "multiple_choice": "multiple_choice",
    "written": "written",
    "short_answer": "written",
}
QUIZ_COUNT_RANGES = {
    "tiny": (3, 6),
    "compact": (6, 10),
    "short": (10, 18),
    "standard": (18, 35),
    "expanded": (30, 70),
    "chaptered": (15, 30),
}
WORD_PATTERN = re.compile(r"[0-9A-Za-z\uac00-\ud7a3]+")


@dataclass(frozen=True)
class QuizGenerationPlan:
    strategy: str
    target_quiz_count: int
    min_quiz_count: int
    max_quiz_count: int
    estimated_tokens: int
    section_count: int
    ready_card_count: int
    requested_quiz_count: int | None
    question_types: list[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "strategy": self.strategy,
            "target_quiz_count": self.target_quiz_count,
            "min_quiz_count": self.min_quiz_count,
            "max_quiz_count": self.max_quiz_count,
            "estimated_tokens": self.estimated_tokens,
            "section_count": self.section_count,
            "ready_card_count": self.ready_card_count,
            "requested_quiz_count": self.requested_quiz_count,
            "question_types": self.question_types,
        }


def normalize_question_types(question_types: list[str] | None) -> list[str]:
    raw_types = question_types or list(DEFAULT_QUESTION_TYPES)
    normalized = []
    for item in raw_types:
        key = str(item).strip().lower()
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


def resolve_quiz_generation_plan(
    record: LectureRecord,
    sections: list[dict[str, object]],
    ready_cards: list[dict[str, object]],
    *,
    quiz_count: int | None,
    question_types: list[str],
) -> QuizGenerationPlan:
    if quiz_count is not None and quiz_count <= 0:
        raise ValidationError(
            ErrorDetail(
                code="quiz_count_invalid",
                message="quiz_count must be at least 1.",
                stage="quiz",
                retryable=False,
            )
        )

    estimated_tokens = _estimated_tokens(record, sections)
    strategy = _strategy(record, estimated_tokens)
    min_count, max_count = _range_for_strategy(strategy, sections)
    section_count = len(sections)
    ready_card_count = len(ready_cards)
    raw_target = round(
        section_count * len(question_types)
        + ready_card_count * 0.6
        + estimated_tokens / 420
    )
    target = _clamp(raw_target, min_count, max_count)
    if quiz_count is not None:
        target = min(target, quiz_count)
    target = max(1, target)

    return QuizGenerationPlan(
        strategy=strategy,
        target_quiz_count=target,
        min_quiz_count=min_count,
        max_quiz_count=max_count,
        estimated_tokens=estimated_tokens,
        section_count=section_count,
        ready_card_count=ready_card_count,
        requested_quiz_count=quiz_count,
        question_types=question_types,
    )


def _estimated_tokens(
    record: LectureRecord,
    sections: list[dict[str, object]],
) -> int:
    profile = record.note_metadata.get("content_profile", {})
    if isinstance(profile, dict):
        value = profile.get("estimated_tokens")
        if isinstance(value, (int, float)) and value > 0:
            return int(value)

    text = " ".join(str(section.get("text") or "") for section in sections)
    word_count = len(WORD_PATTERN.findall(text))
    non_space_count = len(re.sub(r"\s+", "", text))
    return max(word_count, round(non_space_count / 3))


def _strategy(record: LectureRecord, estimated_tokens: int) -> str:
    profile = record.note_metadata.get("content_profile", {})
    if isinstance(profile, dict):
        strategy = str(profile.get("strategy") or "")
        if strategy in QUIZ_COUNT_RANGES:
            return strategy

    if estimated_tokens > 12000:
        return "chaptered"
    if estimated_tokens > 4500:
        return "expanded"
    if estimated_tokens >= 1800:
        return "standard"
    if estimated_tokens >= 700:
        return "short"
    if estimated_tokens >= 300:
        return "compact"
    return "tiny"


def _range_for_strategy(
    strategy: str,
    sections: list[dict[str, object]],
) -> tuple[int, int]:
    min_count, max_count = QUIZ_COUNT_RANGES.get(strategy, QUIZ_COUNT_RANGES["standard"])
    if strategy != "chaptered":
        return min_count, max_count

    chapters = {
        str(section.get("chapter") or "unassigned")
        for section in sections
        if str(section.get("chapter") or "").strip()
    }
    chapter_count = max(1, len(chapters))
    return min_count * chapter_count, max_count * chapter_count


def _clamp(value: int, lower: int, upper: int) -> int:
    return min(max(value, lower), upper)

from __future__ import annotations

import random
from dataclasses import replace

from lecturedigest.errors import ErrorDetail, QuizGenerationError, ValidationError
from lecturedigest.models import LectureRecord
from lecturedigest.quiz_factory import build_quiz_candidates
from lecturedigest.quiz_policy import (
    DEFAULT_QUESTION_TYPES,
    DEFAULT_QUIZ_COUNT,
    QUESTION_TYPE_ALIASES,
    normalize_question_types,
    resolve_quiz_generation_plan,
)
from lecturedigest.quiz_validation import remove_duplicate_quiz_items

DEFAULT_QUIZ_MODEL = "local-quiz-v2"
DEFAULT_QUIZ_PROMPT_VERSION = "quiz-prd-v1"


def generate_quizzes(
    record: LectureRecord,
    *,
    quiz_count: int | None = DEFAULT_QUIZ_COUNT,
    seed: int | None = None,
    question_types: list[str] | None = None,
    quiz_model: str = DEFAULT_QUIZ_MODEL,
    prompt_version: str = DEFAULT_QUIZ_PROMPT_VERSION,
) -> LectureRecord:
    normalized_types = normalize_question_types(question_types)
    normalized_model = _require_text(quiz_model, "quiz_model")
    normalized_prompt = _require_text(prompt_version, "prompt_version")
    sections = _approved_note_sections(record)
    ready_cards = _ready_cards(record)
    plan = resolve_quiz_generation_plan(
        record,
        sections,
        ready_cards,
        quiz_count=quiz_count,
        question_types=normalized_types,
    )

    rng = random.Random(seed)
    candidates = build_quiz_candidates(
        record,
        sections,
        ready_cards,
        question_types=normalized_types,
        target_quiz_count=plan.target_quiz_count,
        rng=rng,
    )
    candidates, duplicate_count = remove_duplicate_quiz_items(candidates)
    rng.shuffle(candidates)
    quiz_items = candidates[: plan.target_quiz_count]
    ready_count = sum(1 for item in quiz_items if item["status"] == "ready")
    flagged_count = len(quiz_items) - ready_count
    input_source = _selected_input_source(quiz_items)

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
            "removed_duplicate_count": duplicate_count,
            "seed": seed,
            "question_types": normalized_types,
            "source": input_source,
            "generation_plan": plan.to_dict(),
        },
    )


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


def _ready_cards(record: LectureRecord) -> list[dict[str, object]]:
    return [
        card
        for card in record.flashcards
        if isinstance(card, dict) and card.get("status") == "ready"
    ]


def _selected_input_source(items: list[dict[str, object]]) -> str:
    origins = {str(item.get("input_origin") or "") for item in items}
    if "ready_card" in origins and "approved_note" in origins:
        return "mixed"
    if "ready_card" in origins:
        return "ready_cards"
    return "approved_note"


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

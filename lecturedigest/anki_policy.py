from __future__ import annotations

import re
from dataclasses import dataclass

from lecturedigest.errors import ErrorDetail, ValidationError
from lecturedigest.models import LectureRecord

SUPPORTED_CARD_TYPES = ("qa", "cloze", "code", "application")
DEFAULT_CARD_TYPES = SUPPORTED_CARD_TYPES

CARD_COUNT_RANGES = {
    "tiny": (3, 8),
    "compact": (6, 14),
    "short": (12, 28),
    "standard": (24, 60),
    "expanded": (20, 40),
    "chaptered": (20, 40),
}

WORD_PATTERN = re.compile(r"[0-9A-Za-z\uac00-\ud7a3]+")
CORE_CONCEPT_MARKER = re.compile(
    r"(?i)(core|concept|key|term|definition|topic|"
    r"\ud575\uc2ec|\uac1c\ub150|\uc6a9\uc5b4|\uc815\uc758)"
)


@dataclass(frozen=True)
class CardGenerationPlan:
    strategy: str
    target_card_count: int
    min_card_count: int
    max_card_count: int
    estimated_tokens: int
    section_count: int
    concept_count: int
    requested_max_cards: int | None
    card_types: list[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "strategy": self.strategy,
            "target_card_count": self.target_card_count,
            "min_card_count": self.min_card_count,
            "max_card_count": self.max_card_count,
            "estimated_tokens": self.estimated_tokens,
            "section_count": self.section_count,
            "concept_count": self.concept_count,
            "requested_max_cards": self.requested_max_cards,
            "card_types": self.card_types,
        }


def normalize_card_types(card_types: list[str] | str | None) -> list[str]:
    if card_types is None:
        values = list(DEFAULT_CARD_TYPES)
    elif isinstance(card_types, str):
        values = [item.strip() for item in card_types.split(",")]
    else:
        values = [str(item).strip() for item in card_types]

    normalized = []
    for value in values:
        if not value:
            continue
        if value not in SUPPORTED_CARD_TYPES:
            allowed = ", ".join(SUPPORTED_CARD_TYPES)
            raise ValidationError(
                ErrorDetail(
                    code="card_type_invalid",
                    message=f"card type must be one of: {allowed}.",
                    stage="anki",
                    retryable=False,
                )
            )
        if value not in normalized:
            normalized.append(value)

    if not normalized:
        raise ValidationError(
            ErrorDetail(
                code="card_types_required",
                message="At least one card type is required.",
                stage="anki",
                retryable=False,
            )
        )
    return normalized


def resolve_card_generation_plan(
    record: LectureRecord,
    sections: list[dict[str, object]],
    *,
    max_cards: int | None,
    card_types: list[str],
) -> CardGenerationPlan:
    if max_cards is not None and max_cards <= 0:
        raise ValidationError(
            ErrorDetail(
                code="max_cards_invalid",
                message="max_cards must be at least 1.",
                stage="anki",
                retryable=False,
            )
        )

    estimated_tokens = _estimated_tokens(record, sections)
    strategy = _strategy(record, estimated_tokens)
    min_cards, max_cards_for_strategy = _range_for_strategy(strategy, sections)
    concept_count = _concept_count(sections)
    section_count = len(sections)
    raw_target = round(
        section_count * 2.2
        + concept_count * 1.4
        + estimated_tokens / 220
    )
    if strategy in {"expanded", "chaptered"}:
        raw_target = max(raw_target, min_cards)

    target = _clamp(raw_target, min_cards, max_cards_for_strategy)
    if max_cards is not None:
        target = min(target, max_cards)
    target = max(1, target)

    return CardGenerationPlan(
        strategy=strategy,
        target_card_count=target,
        min_card_count=min_cards,
        max_card_count=max_cards_for_strategy,
        estimated_tokens=estimated_tokens,
        section_count=section_count,
        concept_count=concept_count,
        requested_max_cards=max_cards,
        card_types=card_types,
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
        if strategy in CARD_COUNT_RANGES:
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
    min_cards, max_cards = CARD_COUNT_RANGES.get(strategy, CARD_COUNT_RANGES["standard"])
    if strategy not in {"expanded", "chaptered"}:
        return min_cards, max_cards

    chapters = {
        str(section.get("chapter") or "unassigned")
        for section in sections
        if str(section.get("chapter") or "").strip()
    }
    chapter_count = max(1, len(chapters))
    return min_cards * chapter_count, max_cards * chapter_count


def _concept_count(sections: list[dict[str, object]]) -> int:
    count = 0
    for section in sections:
        key = str(section.get("section_key") or "")
        title = str(section.get("title") or "")
        if key.startswith("topic_") or CORE_CONCEPT_MARKER.search(title):
            count += 1
    return max(count, min(len(sections), 1))


def _clamp(value: int, lower: int, upper: int) -> int:
    return min(max(value, lower), upper)

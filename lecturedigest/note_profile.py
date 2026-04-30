from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

WORD_PATTERN = re.compile(r"[0-9A-Za-z가-힣]+")
CODE_PATTERN = re.compile(
    r"```|`[^`]+`|\b(?:function|const|let|var|class|import|export|return)\b|"
    r"\b(?:npm|pip|python|node|git)\s+|[{};=<>]|\b[A-Za-z]+[A-Z][A-Za-z0-9]*\b"
)
PROCESS_PATTERN = re.compile(
    r"단계|순서|흐름|먼저|다음|이후|마지막|처리|실행|파싱|렌더|빌드|요청|응답|->|→"
)
COMPARISON_PATTERN = re.compile(r"비교|차이|다르|구분|반면|대신|versus|\bvs\.?\b", re.IGNORECASE)
TOPIC_MARKER_PATTERN = re.compile(
    r"(?:^|\s)(?:먼저|다음|이후|마지막|첫 번째|두 번째|세 번째|\d+\s*[.)]|[0-9]+단계)"
)


@dataclass(frozen=True)
class NoteContentProfile:
    estimated_tokens: int
    word_count: int
    non_space_character_count: int
    segment_count: int
    topic_shift_count: int
    has_code_or_commands: bool
    has_process_flow: bool
    has_comparison: bool
    strategy: str
    source_insufficient_for_full_note: bool
    target_counts: dict[str, tuple[int, int]]

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["target_counts"] = {
            key: {"min": value[0], "max": value[1]}
            for key, value in self.target_counts.items()
        }
        return payload


def build_content_profile(
    source_units: list[Any],
    *,
    chunks: list[Any] | None = None,
) -> NoteContentProfile:
    text = _source_text(source_units)
    word_count = len(WORD_PATTERN.findall(text))
    non_space_count = len(re.sub(r"\s+", "", text))
    estimated_tokens = max(word_count, round(non_space_count / 3))
    segment_count = len(source_units)
    topic_shift_count = _topic_shift_count(text, chunks or [])
    has_code_or_commands = bool(CODE_PATTERN.search(text))
    has_process_flow = bool(PROCESS_PATTERN.search(text))
    has_comparison = bool(COMPARISON_PATTERN.search(text))
    strategy = _strategy(estimated_tokens, topic_shift_count)
    return NoteContentProfile(
        estimated_tokens=estimated_tokens,
        word_count=word_count,
        non_space_character_count=non_space_count,
        segment_count=segment_count,
        topic_shift_count=topic_shift_count,
        has_code_or_commands=has_code_or_commands,
        has_process_flow=has_process_flow,
        has_comparison=has_comparison,
        strategy=strategy,
        source_insufficient_for_full_note=strategy == "compact",
        target_counts=_target_counts(strategy),
    )


def _source_text(source_units: list[Any]) -> str:
    parts = []
    for unit in source_units:
        parts.append(str(getattr(unit, "text", "") or ""))
        ocr_text = str(getattr(unit, "ocr_text", "") or "")
        if ocr_text:
            parts.append(ocr_text)
    return " ".join(parts)


def _topic_shift_count(text: str, chunks: list[Any]) -> int:
    chapter_names = []
    for chunk in chunks:
        chapter = str(getattr(chunk, "chapter", "") or "").strip()
        if chapter and chapter not in chapter_names:
            chapter_names.append(chapter)
    chunk_shifts = max(0, len(chapter_names) - 1)
    marker_shifts = len(TOPIC_MARKER_PATTERN.findall(text))
    return max(chunk_shifts, marker_shifts)


def _strategy(estimated_tokens: int, topic_shift_count: int) -> str:
    if estimated_tokens > 12000 or topic_shift_count >= 12:
        return "chaptered"
    if estimated_tokens > 4500:
        return "expanded"
    if estimated_tokens >= 700:
        return "standard"
    return "compact"


def _target_counts(strategy: str) -> dict[str, tuple[int, int]]:
    if strategy == "compact":
        return {
            "learning_goals": (1, 3),
            "core_topics": (1, 2),
            "key_terms": (1, 7),
            "review_questions": (1, 7),
        }
    if strategy == "standard":
        return {
            "learning_goals": (4, 7),
            "core_topics": (3, 6),
            "key_terms": (8, 15),
            "review_questions": (8, 15),
        }
    if strategy == "expanded":
        return {
            "learning_goals": (5, 7),
            "core_topics": (5, 10),
            "key_terms": (10, 20),
            "review_questions": (10, 15),
        }
    return {
        "learning_goals": (5, 7),
        "core_topics": (6, 12),
        "key_terms": (12, 20),
        "review_questions": (12, 15),
    }

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime

from lecturedigest.models import LectureRecord, TranscriptSegment
from lecturedigest.note_difficulty import (
    beginner_explanation_for,
    detect_difficult_concepts,
)
from lecturedigest.note_prd import (
    CORE_TOPIC_PREFIX,
    default_section_title,
    markdown_from_sections,
    validate_prd_candidate,
)
from lecturedigest.note_profile import build_content_profile

TOKEN_PATTERN = re.compile(r"[0-9A-Za-z가-힣]+")
SENTENCE_PATTERN = re.compile(r"(?<=[.!?。！？])\s+")
FILLER_PATTERNS = (
    re.compile(r"\b(um+|uh+|er+|ah+)\b", re.IGNORECASE),
    re.compile(r"\b(you know|kind of|sort of)\b", re.IGNORECASE),
    re.compile(r"\b(like)\b", re.IGNORECASE),
    re.compile(r"(?:^|\s)(음+|어+|그+|저+|그러니까|이제|약간)(?=\s|$)"),
)
STOPWORDS = {
    "the",
    "and",
    "that",
    "this",
    "with",
    "from",
    "lecture",
    "source",
    "components",
    "강의",
    "내용",
    "합니다",
    "있습니다",
}


@dataclass(frozen=True)
class NoteSourceUnit:
    segment_id: str
    start_ts: str
    end_ts: str
    text: str
    ocr_text: str | None = None


def build_note_candidate(
    *,
    record: LectureRecord,
    source_units: list[NoteSourceUnit],
    tone: str,
    model: str,
    prompt_version: str,
    variant_index: int,
) -> dict[str, object]:
    content_profile = build_content_profile(source_units, chunks=record.chunks)
    sections = _section_rows(record, source_units, variant_index)
    candidate_id = _candidate_id(record, source_units, prompt_version, variant_index)
    markdown = markdown_from_sections(title=record.title, sections=sections)
    generator_notes = {
        "difficulty_explanations": _local_difficulty_explanations(source_units, sections)
    }
    validation = validate_prd_candidate(
        markdown=markdown,
        sections=sections,
        source_units=source_units,
        content_profile=content_profile,
        generator_notes=generator_notes,
    )
    return {
        "candidate_id": candidate_id,
        "status": "pending_approval",
        "tone": tone,
        "model": model,
        "prompt_version": prompt_version,
        "variant": _variant_name(variant_index),
        "created_at": datetime.now(UTC).isoformat(),
        "markdown": markdown,
        "sections": sections,
        "generator_notes": generator_notes,
        "source_segment_ids": _union_segment_ids(sections),
        "content_profile": content_profile.to_dict(),
        "validation": validation,
    }


def source_units(segments: list[TranscriptSegment]) -> list[NoteSourceUnit]:
    units = []
    for segment in segments:
        cleaned = clean_note_text(segment.text)
        if not cleaned:
            continue
        units.append(
            NoteSourceUnit(
                segment_id=segment.segment_id,
                start_ts=segment.start_ts,
                end_ts=segment.end_ts,
                text=cleaned,
                ocr_text=segment.ocr_text.strip() if segment.ocr_text else None,
            )
        )
    return units


def clean_note_text(text: str) -> str:
    cleaned = text
    for pattern in FILLER_PATTERNS:
        cleaned = pattern.sub(" ", cleaned)
    cleaned = re.sub(r"\b([0-9A-Za-z가-힣]{2,})(?:\s+\1\b)+", r"\1", cleaned)
    cleaned = re.sub(r"\s*,\s*,", ",", cleaned)
    cleaned = re.sub(r"\s+([,.;:!?])", r"\1", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def source_hash(source_units: list[NoteSourceUnit]) -> str:
    payload = "|".join(
        f"{unit.segment_id}:{unit.start_ts}:{unit.end_ts}:{unit.text}:{unit.ocr_text}"
        for unit in source_units
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _section_rows(
    record: LectureRecord,
    source_units: list[NoteSourceUnit],
    variant_index: int,
) -> list[dict[str, object]]:
    content_profile = build_content_profile(source_units, chunks=record.chunks)
    source_text = " ".join(unit.text for unit in source_units)
    keywords = _keywords(source_text, limit=content_profile.target_counts["key_terms"][1])
    concepts = keywords or ["핵심 개념"]
    topic_units = _topic_unit_groups(source_units, content_profile.target_counts["core_topics"][1])
    sections = [
        _section(
            record=record,
            key="one_line_summary",
            text="\n".join(_one_line_summary(source_units, variant_index)),
            order=1,
            source_units=source_units,
        ),
        _section(
            record=record,
            key="learning_goals",
            text="\n".join(_learning_goal_lines(concepts, source_units, content_profile)),
            order=2,
            source_units=source_units,
        ),
    ]
    for index, units in enumerate(topic_units, start=1):
        concept = concepts[min(index - 1, len(concepts) - 1)]
        sections.append(
            _section(
                record=record,
                key=f"{CORE_TOPIC_PREFIX}{index}",
                title=f"## {index}. {concept}",
                text="\n".join(_topic_lines(concept, units, content_profile, index)),
                order=2 + index,
                source_units=units,
            )
        )
    sections.extend(
        [
            _section(
                record=record,
                key="practical_takeaways",
                text="\n".join(_practical_lines(concepts, source_units, content_profile)),
                order=40,
                source_units=source_units,
            ),
            _section(
                record=record,
                key="key_terms",
                text="\n".join(_key_term_lines(concepts, source_units, content_profile)),
                order=50,
                source_units=source_units,
            ),
            _section(
                record=record,
                key="review_questions",
                text="\n".join(_review_question_lines(concepts, source_units, content_profile)),
                order=60,
                source_units=source_units,
            ),
            _section(
                record=record,
                key="final_summary",
                text="\n\n".join(_final_summary(source_units, content_profile)),
                order=70,
                source_units=source_units,
            ),
        ]
    )
    return sections


def _section(
    *,
    record: LectureRecord,
    key: str,
    text: str,
    order: int,
    source_units: list[NoteSourceUnit],
    title: str | None = None,
) -> dict[str, object]:
    start_ts, end_ts = _time_range(source_units)
    return {
        "note_section_id": f"{record.lecture_id}:note:{key}",
        "title": title or default_section_title(key),
        "section_key": key,
        "order": order,
        "chapter": _chapter(record),
        "text": text,
        "segment_ids": [unit.segment_id for unit in source_units],
        "start_ts": start_ts,
        "end_ts": end_ts,
        "flagged": not text or not source_units,
    }


def _one_line_summary(
    source_units: list[NoteSourceUnit],
    variant_index: int,
) -> list[str]:
    sentences = _sentences(" ".join(unit.text for unit in source_units))
    if variant_index == 2:
        selected = sentences[:1]
    elif variant_index == 3:
        selected = sentences[-1:] if sentences else []
    else:
        selected = sentences[:2]
    return [_snippet(sentence, 180) for sentence in selected[:3]]


def _learning_goal_lines(
    concepts: list[str],
    source_units: list[NoteSourceUnit],
    content_profile,
) -> list[str]:
    count = min(len(concepts), content_profile.target_counts["learning_goals"][1])
    count = max(1, count)
    verbs = ["설명할 수 있다", "구분할 수 있다", "판단할 수 있다", "이해한다"]
    return [
        f"- {concepts[index % len(concepts)]}의 역할을 {verbs[index % len(verbs)]}."
        for index in range(count)
    ]


def _topic_lines(
    concept: str,
    source_units: list[NoteSourceUnit],
    content_profile,
    topic_index: int,
) -> list[str]:
    evidence = _representative_text(source_units, topic_index)
    lines = [
        f"{concept}은 이 구간에서 다루는 핵심 주제입니다. {_snippet(evidence, 180)}",
        "강의 흐름을 유지하되, 반복되는 구어체 표현은 복습하기 쉬운 문장으로 정리합니다.",
    ]
    easy_explanation = _easy_explanation_for_units(source_units)
    if easy_explanation:
        lines.extend(["", easy_explanation])
    if content_profile.has_process_flow:
        lines.extend(
            [
                "",
                "```text",
                "핵심 입력",
                "  -> 처리 흐름",
                "  -> 결과 확인",
                "```",
            ]
        )
    if content_profile.has_comparison:
        lines.extend(
            [
                "",
                "| 항목 | 설명 |",
                "| --- | --- |",
                f"| {concept} | 강의에서 비교하거나 구분해야 하는 개념입니다. |",
            ]
        )
    if content_profile.has_code_or_commands:
        lines.extend(
            [
                "",
                "```text",
                _snippet(evidence, 120),
                "```",
            ]
        )
    return lines


def _easy_explanation_for_units(source_units: list[NoteSourceUnit]) -> str:
    concepts = detect_difficult_concepts(source_units, limit=1)
    if not concepts:
        return ""
    return beginner_explanation_for(str(concepts[0].get("term") or "핵심 개념"))


def _local_difficulty_explanations(
    source_units: list[NoteSourceUnit],
    sections: list[dict[str, object]],
) -> list[dict[str, object]]:
    explanations = []
    for item in detect_difficult_concepts(source_units, sections=sections):
        term = str(item.get("term") or "")
        explanations.append(
            {
                **item,
                "plain_explanation": beginner_explanation_for(term),
                "analogy_used": False,
            }
        )
    return explanations


def _practical_lines(
    concepts: list[str],
    source_units: list[NoteSourceUnit],
    content_profile,
) -> list[str]:
    lines = [
        f"- {concepts[0]}를 원본 출처와 연결된 내부 메타데이터로 다시 확인한다.",
        "- 출처가 확인되지 않는 내용은 학습 노트나 카드로 확정하지 않는다.",
    ]
    if content_profile.strategy in {"expanded", "chaptered"}:
        lines.append("- 긴 강의는 챕터별로 나눠 부분 노트와 전체 요약을 함께 검토한다.")
    return lines


def _key_term_lines(
    concepts: list[str],
    source_units: list[NoteSourceUnit],
    content_profile,
) -> list[str]:
    limit = min(len(concepts), content_profile.target_counts["key_terms"][1])
    rows = ["| 용어 | 의미 |", "| --- | --- |"]
    for concept in concepts[: max(1, limit)]:
        rows.append(f"| {concept} | 강의 원문에서 확인되는 핵심 표현입니다. |")
    return rows


def _review_question_lines(
    concepts: list[str],
    source_units: list[NoteSourceUnit],
    content_profile,
) -> list[str]:
    limit = min(len(concepts), content_profile.target_counts["review_questions"][1])
    return [
        f"{index}. {concept}이 이 강의 흐름에서 왜 중요한지 설명할 수 있는가?"
        for index, concept in enumerate(concepts[: max(1, limit)], start=1)
    ]


def _final_summary(
    source_units: list[NoteSourceUnit],
    content_profile,
) -> list[str]:
    first = _snippet(source_units[0].text, 180)
    last = _snippet(source_units[-1].text, 180)
    return [
        f"이 강의는 {first}에서 출발해 핵심 개념을 학습 흐름에 맞게 정리한다.",
        (
            f"마지막으로 {last}까지 이어지는 내용을 복습 질문과 용어 정리로 다시 확인한다. "
            f"생성 전략은 `{content_profile.strategy}`이다."
        ),
    ]


def _topic_unit_groups(
    source_units: list[NoteSourceUnit],
    max_topics: int,
) -> list[list[NoteSourceUnit]]:
    if not source_units:
        return []
    topic_count = max(1, min(len(source_units), max_topics))
    groups = []
    for index in range(topic_count):
        start = round(index * len(source_units) / topic_count)
        end = round((index + 1) * len(source_units) / topic_count)
        groups.append(source_units[start:end] or [source_units[min(index, len(source_units) - 1)]])
    return groups


def _sentences(text: str) -> list[str]:
    sentences = [item.strip() for item in SENTENCE_PATTERN.split(text) if item.strip()]
    if sentences:
        return sentences
    return [text.strip()] if text.strip() else []


def _keywords(text: str, *, limit: int) -> list[str]:
    seen = set()
    keywords = []
    for token in TOKEN_PATTERN.findall(text):
        normalized = token.lower()
        if normalized in STOPWORDS or normalized in seen or len(normalized) < 3:
            continue
        seen.add(normalized)
        keywords.append(token)
        if len(keywords) >= limit:
            break
    return keywords


def _representative_text(
    source_units: list[NoteSourceUnit],
    variant_index: int,
) -> str:
    index = min(len(source_units) - 1, max(0, variant_index - 1))
    return _snippet(source_units[index].text, 180)


def _time_range(source_units: list[NoteSourceUnit]) -> tuple[str | None, str | None]:
    if not source_units:
        return None, None
    return source_units[0].start_ts, source_units[-1].end_ts


def _union_segment_ids(sections: list[dict[str, object]]) -> list[str]:
    ordered = []
    for section in sections:
        for segment_id in section.get("segment_ids", []):
            value = str(segment_id)
            if value not in ordered:
                ordered.append(value)
    return ordered


def _snippet(text: str, max_chars: int) -> str:
    compact = " ".join(text.split())
    if len(compact) <= max_chars:
        return compact
    trimmed = compact[: max_chars + 1].rsplit(" ", maxsplit=1)[0]
    return f"{trimmed or compact[:max_chars]}..."


def _candidate_id(
    record: LectureRecord,
    source_units: list[NoteSourceUnit],
    prompt_version: str,
    variant_index: int,
) -> str:
    digest = hashlib.sha256(
        f"{record.lecture_id}:{source_hash(source_units)}:{prompt_version}".encode(
            "utf-8"
        )
    ).hexdigest()[:10]
    return f"note-candidate-{digest}-{variant_index:02d}"


def _variant_name(variant_index: int) -> str:
    return {
        1: "balanced",
        2: "concept_focused",
        3: "action_focused",
    }.get(variant_index, "balanced")


def _chapter(record: LectureRecord) -> str:
    if record.chunks:
        return record.chunks[0].chapter
    return record.middle_category or record.category or "unassigned"

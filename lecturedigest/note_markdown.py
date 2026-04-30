from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime

from lecturedigest.models import LectureRecord, TranscriptSegment

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
    sections = _section_rows(record, source_units, variant_index)
    candidate_id = _candidate_id(record, source_units, prompt_version, variant_index)
    markdown = _markdown(
        record=record,
        candidate_id=candidate_id,
        status="pending_approval",
        tone=tone,
        model=model,
        prompt_version=prompt_version,
        sections=sections,
        source_units=source_units,
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
        "source_segment_ids": [unit.segment_id for unit in source_units],
        "validation": _validate_candidate(markdown, sections, source_units),
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
    source_text = " ".join(unit.text for unit in source_units)
    keywords = _keywords(source_text)
    primary = keywords[:3] or ["핵심 개념"]
    rows = [
        ("summary", "[1] 강의 요약 (3~5줄)", _summary_lines(source_units, variant_index)),
        (
            "key_concepts",
            "[2] 핵심 개념 (Key Concepts)",
            _concept_lines(primary, source_units, variant_index),
        ),
        ("flow", "[3] 구조 / 흐름 (Flow)", _flow_lines(record, source_units, variant_index)),
        ("action", "[4] 실행 (Action)", _action_lines(primary, source_units, variant_index)),
    ]
    return [
        _section(
            record=record,
            key=key,
            title=title,
            text="\n".join(lines),
            order=index,
            source_units=source_units,
        )
        for index, (key, title, lines) in enumerate(rows, start=1)
    ]


def _section(
    *,
    record: LectureRecord,
    key: str,
    title: str,
    text: str,
    order: int,
    source_units: list[NoteSourceUnit],
) -> dict[str, object]:
    return {
        "note_section_id": f"{record.lecture_id}:note:{key}",
        "title": title,
        "section_key": key,
        "order": order,
        "chapter": _chapter(record),
        "text": text,
        "segment_ids": [unit.segment_id for unit in source_units],
        "start_ts": source_units[0].start_ts,
        "end_ts": source_units[-1].end_ts,
        "flagged": False,
    }


def _markdown(
    *,
    record: LectureRecord,
    candidate_id: str,
    status: str,
    tone: str,
    model: str,
    prompt_version: str,
    sections: list[dict[str, object]],
    source_units: list[NoteSourceUnit],
) -> str:
    frontmatter = [
        "---",
        f"lecture_id: {record.lecture_id}",
        f"title: {_yaml_value(record.title)}",
        f"candidate_id: {candidate_id}",
        f"status: {status}",
        f"tone: {tone}",
        f"model: {model}",
        f"prompt_version: {prompt_version}",
        f"source_start_ts: {source_units[0].start_ts}",
        f"source_end_ts: {source_units[-1].end_ts}",
        f"source_segment_count: {len(source_units)}",
        "---",
    ]
    body = []
    for section in sections:
        body.append(str(section["title"]))
        body.append(str(section["text"]))
        body.append("")
    return "\n".join(frontmatter + [""] + body).rstrip() + "\n"


def _summary_lines(
    source_units: list[NoteSourceUnit],
    variant_index: int,
) -> list[str]:
    sentences = _sentences(" ".join(unit.text for unit in source_units))
    selected = sentences[:5]
    if variant_index == 2:
        selected = sentences[:3]
    if variant_index == 3:
        selected = sentences[-3:] if len(sentences) >= 3 else sentences
    return [f"- {_with_citation(sentence, source_units)}" for sentence in selected[:5]]


def _concept_lines(
    concepts: list[str],
    source_units: list[NoteSourceUnit],
    variant_index: int,
) -> list[str]:
    lines = []
    evidence = _representative_text(source_units, variant_index)
    for concept in concepts:
        lines.extend(
            [
                f"- {concept}:",
                f"  정의: (추론) {_with_citation(evidence, source_units)}",
                "  왜 중요한가: 강의에서 반복적으로 연결되는 핵심 표현입니다.",
                "  어디에 쓰나: 원문 근거를 다시 보며 실습/복습 항목으로 전환합니다.",
            ]
        )
    return lines


def _flow_lines(
    record: LectureRecord,
    source_units: list[NoteSourceUnit],
    variant_index: int,
) -> list[str]:
    chapter = _chapter(record)
    lines = [
        f"- {chapter} 구간은 {_with_citation(source_units[0].text, source_units)}에서 시작합니다.",
        f"- 이후 핵심 설명은 {_with_citation(source_units[-1].text, source_units)}로 이어집니다.",
    ]
    ocr_lines = [unit.ocr_text for unit in source_units if unit.ocr_text]
    if ocr_lines:
        lines.append(f"- 화면 메모: {_snippet(' '.join(ocr_lines), 160)}")
    if variant_index == 3:
        lines.append("- 흐름을 실행 단위로 다시 확인합니다.")
    return lines


def _action_lines(
    concepts: list[str],
    source_units: list[NoteSourceUnit],
    variant_index: int,
) -> list[str]:
    lines = [
        f"- {concepts[0]}를 원문 타임스탬프와 함께 다시 확인합니다. {_citation(source_units)}",
        "- 모르는 용어는 원문 근거가 있는 항목과 `(추론)` 항목으로 분리합니다.",
    ]
    if variant_index >= 2:
        lines.append("- 다음 단계에서 승인된 노트만 카드/퀴즈 입력으로 사용합니다.")
    return lines


def _validate_candidate(
    markdown: str,
    sections: list[dict[str, object]],
    source_units: list[NoteSourceUnit],
) -> dict[str, object]:
    source_length = max(1, len(" ".join(unit.text for unit in source_units)))
    ratio = round(len(markdown) / source_length, 3)
    unmapped = [
        str(section["section_key"])
        for section in sections
        if not section.get("segment_ids")
    ]
    failed = []
    if ratio < 0.4 or ratio > 0.7:
        failed.append("note_length_ratio_out_of_target")
    if unmapped:
        failed.append("source_mapping_missing")
    return {
        "status": "passed" if not failed else "flagged",
        "length_ratio": ratio,
        "target_length_ratio": "0.4-0.7",
        "failed_rules": failed,
        "unmapped_sections": unmapped,
    }


def _sentences(text: str) -> list[str]:
    sentences = [item.strip() for item in SENTENCE_PATTERN.split(text) if item.strip()]
    if sentences:
        return sentences
    return [text.strip()] if text.strip() else []


def _keywords(text: str) -> list[str]:
    seen = set()
    keywords = []
    for token in TOKEN_PATTERN.findall(text):
        normalized = token.lower()
        if normalized in STOPWORDS or normalized in seen or len(normalized) < 3:
            continue
        seen.add(normalized)
        keywords.append(token)
    return keywords[:5]


def _representative_text(
    source_units: list[NoteSourceUnit],
    variant_index: int,
) -> str:
    index = min(len(source_units) - 1, variant_index - 1)
    return _snippet(source_units[index].text, 180)


def _with_citation(text: str, source_units: list[NoteSourceUnit]) -> str:
    return f"{_snippet(text, 180)} {_citation(source_units)}"


def _citation(source_units: list[NoteSourceUnit]) -> str:
    first = source_units[0]
    last = source_units[-1]
    if first.segment_id == last.segment_id:
        return f"(source: {first.segment_id} @ {first.start_ts})"
    return (
        f"(source: {first.segment_id}..{last.segment_id} "
        f"@ {first.start_ts}-{last.end_ts})"
    )


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


def _yaml_value(value: str) -> str:
    escaped = value.replace('"', '\\"')
    return f'"{escaped}"'

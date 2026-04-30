from __future__ import annotations

import json

from lecturedigest.models import LectureRecord
from lecturedigest.note_markdown import NoteSourceUnit
from lecturedigest.note_profile import NoteContentProfile, build_content_profile
from lecturedigest.note_prd import FIXED_SECTION_TITLES
from lecturedigest.openai_client import json_body
from lecturedigest.openai_types import OpenAIRequest

OPENAI_NOTE_ENDPOINT = "/v1/responses"
OPENAI_NOTE_USE_CASE = "note_generation"
DEFAULT_OPENAI_NOTE_MODEL = "gpt-4o"
DEFAULT_OPENAI_NOTE_PROMPT_VERSION = "openai-markdown-note-prd-v2"
OPENAI_NOTE_CANDIDATE_COUNT = 3
NOTE_STAGE = "note_generation"
EXAMPLE_SEGMENT_IDS = ["seg-000001", "seg-000038"]
EXAMPLE_CITATION = "(source: seg-000001..seg-000038 @ 00:00:00.000-00:01:30.000)"

REQUIRED_NOTE_SECTIONS = tuple(FIXED_SECTION_TITLES.items())
NOTE_VARIANTS = ("balanced", "concept_focused", "action_focused")

OPENAI_NOTE_PROMPT = """You are LectureDigest's expert learning-note writer.
Write high-quality Korean Markdown study notes from the provided lecture chunks only.
Do not add facts that are not supported by the source chunks.
Every bullet or paragraph must include a source citation using the provided segment IDs and timestamps.
The first rendered Markdown line must be the lecture title as an H1.
Follow the Lecture Note PRD structure: one-line summary, learning goals, numbered core topics, practical takeaways, key terms, review questions, and final summary.
Use compact notes for short sources without inventing missing concepts. Use expanded or chaptered structure for long sources.
Preserve technical terms, code terms, URLs, browser/API names, and English keywords exactly when important.
Return JSON only. Do not wrap the JSON in Markdown fences."""


def build_note_request(
    record: LectureRecord,
    *,
    source_units: list[NoteSourceUnit],
    tone: str,
    model: str = DEFAULT_OPENAI_NOTE_MODEL,
    prompt_version: str = DEFAULT_OPENAI_NOTE_PROMPT_VERSION,
    variant: str | None = None,
) -> OpenAIRequest:
    content_profile = build_content_profile(source_units, chunks=record.chunks)
    prompt_payload = _prompt_contract(
        record,
        source_units,
        tone,
        content_profile=content_profile,
        variant=variant,
    )
    payload = {
        "model": model,
        "input": [
            {
                "role": "system",
                "content": [{"type": "input_text", "text": OPENAI_NOTE_PROMPT}],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": json.dumps(prompt_payload, ensure_ascii=False),
                    }
                ],
            },
        ],
        "text": {"format": {"type": "json_object"}},
        "max_output_tokens": _max_output_tokens(content_profile),
    }
    body = json_body(payload)
    return OpenAIRequest(
        endpoint=OPENAI_NOTE_ENDPOINT,
        use_case=OPENAI_NOTE_USE_CASE,
        model=model,
        prompt_version=prompt_version,
        body=body,
        input_size_bytes=len(body),
        external_data_boundary="lecture transcript chunks to OpenAI Responses API",
    )


def _prompt_contract(
    record: LectureRecord,
    units: list[NoteSourceUnit],
    tone: str,
    *,
    content_profile: NoteContentProfile,
    variant: str | None = None,
) -> dict[str, object]:
    variants = [variant] if variant else list(NOTE_VARIANTS)
    return {
        "contract": {
            "language": "ko",
            "tone": tone,
            "candidate_count": len(variants),
            "variants": variants,
            "content_profile": content_profile.to_dict(),
            "required_markdown_order": [
                "# 강의 제목",
                "## 강의 한 줄 요약",
                "## 학습 목표",
                "## 1. 첫 번째 핵심 주제",
                "## 2. 두 번째 핵심 주제",
                "## 실무 관점에서 기억할 것",
                "## 핵심 용어 정리",
                "## 복습 질문",
                "## 최종 정리",
            ],
            "section_keys": {
                "one_line_summary": "1-3 supported sentences",
                "learning_goals": "measurable bullet goals",
                "topic_N": "numbered core topic sections, e.g. topic_1, topic_2",
                "practical_takeaways": "practice or work-context takeaways",
                "key_terms": "Markdown table of source-backed terms",
                "review_questions": "numbered self-check questions",
                "final_summary": "2-4 paragraphs when enough source exists",
            },
            "adaptive_policy": _adaptive_policy(content_profile),
            "hard_requirements": [
                "Return exactly one candidate for the requested variant.",
                "The candidate must include one_line_summary, learning_goals, at least one topic_N section, practical_takeaways, key_terms, review_questions, and final_summary.",
                "Do not omit source_segment_ids for any section.",
                "Do not invent goals, terms, examples, tables, code, or diagrams just to satisfy counts.",
                "If the source is too short for PRD minimums, keep the compact note concise and set source_insufficient_for_full_note in notes.",
            ],
            "citation_format": (
                "(source: seg-000001..seg-000038 @ "
                "00:00:00.000-00:01:30.000)"
            ),
            "response_shape": {
                "candidates": [
                    {
                        "variant": variants[0],
                        "sections": _example_sections(),
                        "notes": {
                            "source_insufficient_for_full_note": (
                                content_profile.source_insufficient_for_full_note
                            )
                        },
                    }
                ]
            },
        },
        "lecture": {
            "lecture_id": record.lecture_id,
            "title": record.title,
            "category": record.category,
            "transcript_source": record.transcript_source,
        },
        "source_chunks": _source_chunks(record, units),
    }


def _adaptive_policy(content_profile: NoteContentProfile) -> dict[str, object]:
    return {
        "strategy": content_profile.strategy,
        "target_counts": content_profile.to_dict()["target_counts"],
        "compact_rule": "For short sources, preserve PRD order but do not fabricate missing items.",
        "standard_rule": "For normal sources, satisfy PRD counts where evidence supports them.",
        "expanded_rule": "For long sources, use numbered topics and subsections instead of one huge section.",
        "chaptered_rule": "For very long sources, produce chapter-level sections and a master summary.",
    }


def _max_output_tokens(content_profile: NoteContentProfile) -> int:
    if content_profile.strategy == "chaptered":
        return 12000
    if content_profile.strategy == "expanded":
        return 9000
    return 6000


def _source_chunks(
    record: LectureRecord,
    units: list[NoteSourceUnit],
) -> list[dict[str, object]]:
    unit_by_id = {unit.segment_id: unit for unit in units}
    if record.chunks:
        chunks = []
        for chunk in record.chunks:
            segment_ids = [
                segment_id for segment_id in chunk.segment_ids if segment_id in unit_by_id
            ]
            if not segment_ids:
                continue
            chunks.append(
                {
                    "chunk_id": chunk.chunk_id,
                    "chapter": chunk.chapter,
                    "start_ts": chunk.start_ts,
                    "end_ts": chunk.end_ts,
                    "segment_ids": [segment_ids[0], segment_ids[-1]],
                    "text": chunk.text,
                    "ocr_text": chunk.ocr_text or "",
                }
            )
        if chunks:
            return chunks

    grouped = []
    batch_size = 40
    for start in range(0, len(units), batch_size):
        batch = units[start : start + batch_size]
        grouped.append(
            {
                "chunk_id": f"segments-{start + 1:06d}",
                "chapter": record.middle_category or record.category or "unassigned",
                "start_ts": batch[0].start_ts,
                "end_ts": batch[-1].end_ts,
                "segment_ids": [batch[0].segment_id, batch[-1].segment_id],
                "text": " ".join(unit.text for unit in batch),
                "ocr_text": " ".join(unit.ocr_text or "" for unit in batch).strip(),
            }
        )
    return grouped


def _example_sections() -> list[dict[str, object]]:
    return [
        _example_section(
            "one_line_summary",
            "## 강의 한 줄 요약",
            f"Markdown body for the section {EXAMPLE_CITATION}",
        ),
        _example_section(
            "learning_goals",
            "## 학습 목표",
            f"- 학습자가 설명할 수 있는 목표 {EXAMPLE_CITATION}",
        ),
        _example_section(
            "topic_1",
            "## 1. 첫 번째 핵심 주제",
            f"Core topic body with supported explanation. {EXAMPLE_CITATION}",
        ),
        _example_section(
            "practical_takeaways",
            "## 실무 관점에서 기억할 것",
            f"- 실무 연결 포인트 {EXAMPLE_CITATION}",
        ),
        _example_section(
            "key_terms",
            "## 핵심 용어 정리",
            f"| 용어 | 의미 |\n| --- | --- |\n| 용어 | 의미 {EXAMPLE_CITATION} |",
        ),
        _example_section(
            "review_questions",
            "## 복습 질문",
            f"1. 무엇을 설명할 수 있는가? {EXAMPLE_CITATION}",
        ),
        _example_section(
            "final_summary",
            "## 최종 정리",
            f"Final summary paragraph. {EXAMPLE_CITATION}",
        ),
    ]


def _example_section(section_key: str, title: str, text: str) -> dict[str, object]:
    return {
        "section_key": section_key,
        "title": title,
        "text": text,
        "source_segment_ids": EXAMPLE_SEGMENT_IDS,
    }

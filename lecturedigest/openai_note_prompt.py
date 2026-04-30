from __future__ import annotations

import json

from lecturedigest.models import LectureRecord
from lecturedigest.note_markdown import NoteSourceUnit
from lecturedigest.openai_client import json_body
from lecturedigest.openai_types import OpenAIRequest

OPENAI_NOTE_ENDPOINT = "/v1/responses"
OPENAI_NOTE_USE_CASE = "note_generation"
DEFAULT_OPENAI_NOTE_MODEL = "gpt-4o"
DEFAULT_OPENAI_NOTE_PROMPT_VERSION = "openai-markdown-note-v1"
OPENAI_NOTE_CANDIDATE_COUNT = 3
NOTE_STAGE = "note_generation"

REQUIRED_NOTE_SECTIONS = (
    ("summary", "[1] 강의 요약 (3~5줄)"),
    ("key_concepts", "[2] 핵심 개념 (Key Concepts)"),
    ("flow", "[3] 구조 / 흐름 (Flow)"),
    ("action", "[4] 실행 (Action)"),
)
NOTE_VARIANTS = ("balanced", "concept_focused", "action_focused")

OPENAI_NOTE_PROMPT = """You are LectureDigest's expert learning-note writer.
Write high-quality Korean Markdown study notes from the provided lecture chunks only.
Do not add facts that are not supported by the source chunks.
Every bullet or paragraph must include a source citation using the provided segment IDs and timestamps.
Each candidate must include all four required sections exactly once: summary, key_concepts, flow, action.
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
    prompt_payload = _prompt_contract(record, source_units, tone, variant=variant)
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
        "max_output_tokens": 6000 if variant else 12000,
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
    variant: str | None = None,
) -> dict[str, object]:
    variants = [variant] if variant else list(NOTE_VARIANTS)
    return {
        "contract": {
            "language": "ko",
            "tone": tone,
            "candidate_count": len(variants),
            "variants": variants,
            "required_sections": [
                {
                    "section_key": key,
                    "title": title,
                    "source_segment_ids": (
                        "Use segment IDs that directly support this section."
                    ),
                }
                for key, title in REQUIRED_NOTE_SECTIONS
            ],
            "note_format": {
                "summary": "3 to 5 concise lines",
                "key_concepts": "definition, why important, where used",
                "flow": "lecture logic and step-by-step structure",
                "action": "concrete tasks the learner can do now",
            },
            "hard_requirements": [
                "Return exactly one candidate for the requested variant.",
                "The candidate must contain exactly four sections.",
                "Use section_key values exactly as: summary, key_concepts, flow, action.",
                "Do not omit source_segment_ids for any section.",
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
        {
            "section_key": "summary",
            "text": (
                "- Markdown body for the section "
                "(source: seg-000001..seg-000038 @ 00:00:00.000-00:01:30.000)"
            ),
            "source_segment_ids": ["seg-000001", "seg-000038"],
        },
        {
            "section_key": "key_concepts",
            "text": (
                "- 개념 1:\n"
                "  정의: ... (source: seg-000001..seg-000038 @ 00:00:00.000-00:01:30.000)\n"
                "  왜 중요한가: ... (source: seg-000001..seg-000038 @ 00:00:00.000-00:01:30.000)\n"
                "  어디에 쓰나: ... (source: seg-000001..seg-000038 @ 00:00:00.000-00:01:30.000)"
            ),
            "source_segment_ids": ["seg-000001", "seg-000038"],
        },
        {
            "section_key": "flow",
            "text": (
                "- Step 1: ... "
                "(source: seg-000001..seg-000038 @ 00:00:00.000-00:01:30.000)"
            ),
            "source_segment_ids": ["seg-000001", "seg-000038"],
        },
        {
            "section_key": "action",
            "text": (
                "- 지금 할 일: ... "
                "(source: seg-000001..seg-000038 @ 00:00:00.000-00:01:30.000)"
            ),
            "source_segment_ids": ["seg-000001", "seg-000038"],
        },
    ]

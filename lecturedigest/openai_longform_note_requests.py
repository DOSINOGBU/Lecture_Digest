from __future__ import annotations

import json

from lecturedigest.models import LectureRecord
from lecturedigest.note_markdown import NoteSourceUnit
from lecturedigest.note_profile import NoteContentProfile
from lecturedigest.openai_client import json_body
from lecturedigest.openai_note_prompt import (
    DEFAULT_OPENAI_NOTE_MODEL,
    OPENAI_NOTE_ENDPOINT,
    _max_output_tokens,
    _source_chunks,
)
from lecturedigest.openai_types import OpenAIRequest

LONGFORM_NOTE_PROMPT_VERSION = "openai-markdown-note-prd-v7-longform"
LONGFORM_PLAN_USE_CASE = "note_generation_longform_plan"
LONGFORM_SECTION_USE_CASE = "note_generation_longform_section"
LONGFORM_ASSEMBLY_USE_CASE = "note_generation_longform_assembly"
LONGFORM_TOPIC_BATCH_SIZE = 4

LONGFORM_PLAN_PROMPT = """You plan a long Korean LectureDigest study note.
Use only the supplied lecture chunks.
Return JSON only.
Create a source-backed note plan with enough distinct topics for an expanded or chaptered note.
Do not invent topics, citations, acronyms, examples, code, tables, or diagrams.
Each topic must include section_key, title, purpose, style_hint, and source_segment_ids."""

LONGFORM_SECTION_PROMPT = """You write long Korean Markdown topic sections for LectureDigest.
Use only the supplied source chunks and plan topics.
Return JSON only with a sections array.
Write deep textbook-style body text, not outline bullets.
Do not include visible source citations, segment IDs, or timestamps in rendered text.
Use varied natural structure per topic and beginner explanations where useful.
Preserve source traceability only in source_segment_ids."""

LONGFORM_ASSEMBLY_PROMPT = """You assemble one complete Korean LectureDigest Markdown note candidate.
Use only the supplied source chunks, note plan, and topic section drafts.
Return JSON only with candidates containing exactly one candidate.
Include the fixed PRD sections in order plus all topic sections.
Do not include visible source citations, segment IDs, or timestamps in rendered text.
Known acronyms must use correct expanded_form metadata. Unknown acronyms must not get invented expanded forms.
The final note must be detailed enough to pass the supplied body_depth_policy."""


def build_longform_plan_request(
    record: LectureRecord,
    *,
    source_units: list[NoteSourceUnit],
    content_profile: NoteContentProfile,
    tone: str,
    model: str = DEFAULT_OPENAI_NOTE_MODEL,
    prompt_version: str = LONGFORM_NOTE_PROMPT_VERSION,
    variant: str,
) -> OpenAIRequest:
    return _json_request(
        use_case=LONGFORM_PLAN_USE_CASE,
        model=model,
        prompt_version=prompt_version,
        system_prompt=LONGFORM_PLAN_PROMPT,
        payload={
            "contract": {
                "language": "ko",
                "tone": tone,
                "variant": variant,
                "content_profile": content_profile.to_dict(),
                "target_topic_count": content_profile.target_counts["core_topics"],
                "batch_size_after_plan": LONGFORM_TOPIC_BATCH_SIZE,
                "visible_citations": False,
                "source_segment_ids_required": True,
                "response_shape": {
                    "plan": {
                        "topics": [
                            {
                                "section_key": "topic_1",
                                "title": "## 1. source-backed topic title",
                                "purpose": "why this topic matters in the lecture",
                                "style_hint": "narrative|table|flow|checklist|comparison",
                                "source_segment_ids": ["seg-000001", "seg-000020"],
                            }
                        ]
                    }
                },
            },
            "lecture": lecture_payload(record),
            "source_chunks": _source_chunks(record, source_units),
        },
    )


def build_longform_section_request(
    record: LectureRecord,
    *,
    source_units: list[NoteSourceUnit],
    content_profile: NoteContentProfile,
    tone: str,
    model: str = DEFAULT_OPENAI_NOTE_MODEL,
    prompt_version: str = LONGFORM_NOTE_PROMPT_VERSION,
    variant: str,
    plan: dict[str, object],
    topics: list[dict[str, object]],
    batch_index: int,
) -> OpenAIRequest:
    return _json_request(
        use_case=LONGFORM_SECTION_USE_CASE,
        model=model,
        prompt_version=prompt_version,
        system_prompt=LONGFORM_SECTION_PROMPT,
        payload={
            "contract": {
                "language": "ko",
                "tone": tone,
                "variant": variant,
                "content_profile": content_profile.to_dict(),
                "batch_index": batch_index,
                "body_requirements": "Each topic text should contain supported paragraphs, not one-line summaries.",
                "visible_citations": False,
                "source_segment_ids_required": True,
            },
            "lecture": lecture_payload(record),
            "plan_summary": plan_summary(plan),
            "topics": topics,
            "source_chunks": _source_chunks_for_topics(record, source_units, topics),
        },
    )


def build_longform_assembly_request(
    record: LectureRecord,
    *,
    source_units: list[NoteSourceUnit],
    content_profile: NoteContentProfile,
    tone: str,
    model: str = DEFAULT_OPENAI_NOTE_MODEL,
    prompt_version: str = LONGFORM_NOTE_PROMPT_VERSION,
    variant: str,
    plan: dict[str, object],
    topic_sections: list[dict[str, object]],
) -> OpenAIRequest:
    return _json_request(
        use_case=LONGFORM_ASSEMBLY_USE_CASE,
        model=model,
        prompt_version=prompt_version,
        system_prompt=LONGFORM_ASSEMBLY_PROMPT,
        payload={
            "contract": {
                "language": "ko",
                "tone": tone,
                "candidate_count": 1,
                "variant": variant,
                "content_profile": content_profile.to_dict(),
                "required_sections": [
                    "one_line_summary",
                    "learning_goals",
                    "topic_N",
                    "practical_takeaways",
                    "key_terms",
                    "review_questions",
                    "final_summary",
                ],
                "response_shape": {
                    "candidates": [
                        {
                            "variant": variant,
                            "sections": [
                                {
                                    "section_key": "one_line_summary",
                                    "title": "## lecture summary",
                                    "text": "source-backed Markdown body",
                                    "source_segment_ids": ["seg-000001"],
                                },
                                {
                                    "section_key": "topic_1",
                                    "title": "## 1. source-backed topic",
                                    "text": "deep source-backed Markdown body",
                                    "source_segment_ids": ["seg-000001"],
                                },
                            ],
                            "notes": {
                                "difficulty_explanations": [],
                            },
                        }
                    ]
                },
                "visible_citations": False,
                "source_segment_ids_required": True,
            },
            "lecture": lecture_payload(record),
            "plan": plan,
            "topic_section_drafts": topic_sections,
            "source_chunks": _source_chunks(record, source_units),
        },
    )


def lecture_payload(record: LectureRecord) -> dict[str, object]:
    return {
        "lecture_id": record.lecture_id,
        "title": record.title,
        "category": record.category,
        "transcript_source": record.transcript_source,
    }


def plan_summary(plan: dict[str, object]) -> dict[str, object]:
    topics = _dict_list(plan.get("topics"))
    return {"topic_count": len(topics), "topics": topics}


def _source_chunks_for_topics(
    record: LectureRecord,
    source_units: list[NoteSourceUnit],
    topics: list[dict[str, object]],
) -> list[dict[str, object]]:
    ids = {
        str(segment_id)
        for topic in topics
        for segment_id in _list(topic.get("source_segment_ids"))
        if str(segment_id)
    }
    if not ids:
        return _source_chunks(record, source_units)
    if record.chunks:
        chunks = [
            {
                "chunk_id": chunk.chunk_id,
                "chapter": chunk.chapter,
                "start_ts": chunk.start_ts,
                "end_ts": chunk.end_ts,
                "segment_ids": [chunk.segment_ids[0], chunk.segment_ids[-1]],
                "text": chunk.text,
                "ocr_text": chunk.ocr_text or "",
            }
            for chunk in record.chunks
            if chunk.segment_ids and set(chunk.segment_ids).intersection(ids)
        ]
        if chunks:
            return chunks
    units = [unit for unit in source_units if unit.segment_id in ids]
    if not units:
        return _source_chunks(record, source_units)
    return [
        {
            "chunk_id": f"topic-source-{index:03d}",
            "chapter": record.middle_category or record.category or "unassigned",
            "start_ts": unit.start_ts,
            "end_ts": unit.end_ts,
            "segment_ids": [unit.segment_id],
            "text": unit.text,
            "ocr_text": unit.ocr_text or "",
        }
        for index, unit in enumerate(units, start=1)
    ]


def _json_request(
    *,
    use_case: str,
    model: str,
    prompt_version: str,
    system_prompt: str,
    payload: dict[str, object],
) -> OpenAIRequest:
    body = json_body(
        {
            "model": model,
            "input": [
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": system_prompt}],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": json.dumps(payload, ensure_ascii=False),
                        }
                    ],
                },
            ],
            "text": {"format": {"type": "json_object"}},
            "max_output_tokens": _max_output_tokens_from_payload(payload),
        }
    )
    return OpenAIRequest(
        endpoint=OPENAI_NOTE_ENDPOINT,
        use_case=use_case,
        model=model,
        prompt_version=prompt_version,
        body=body,
        input_size_bytes=len(body),
        external_data_boundary="lecture transcript chunks to OpenAI Responses API",
    )


def _max_output_tokens_from_payload(payload: dict[str, object]) -> int:
    contract = payload.get("contract")
    profile_payload = contract.get("content_profile") if isinstance(contract, dict) else {}
    strategy = ""
    if isinstance(profile_payload, dict):
        strategy = str(profile_payload.get("strategy") or "")

    class Profile:
        def __init__(self, strategy: str) -> None:
            self.strategy = strategy

    return _max_output_tokens(Profile(strategy))  # type: ignore[arg-type]


def _dict_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _list(value: object) -> list[object]:
    return value if isinstance(value, list) else []

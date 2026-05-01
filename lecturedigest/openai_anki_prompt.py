from __future__ import annotations

import json

from lecturedigest.anki_policy import CardGenerationPlan
from lecturedigest.models import LectureRecord, TranscriptSegment
from lecturedigest.openai_client import json_body
from lecturedigest.openai_types import OpenAIRequest

OPENAI_CARD_ENDPOINT = "/v1/responses"
OPENAI_CARD_USE_CASE = "anki_card_generation"
DEFAULT_OPENAI_CARD_MODEL = "gpt-4.1"
DEFAULT_OPENAI_CARD_PROMPT_VERSION = "openai-anki-card-prd-v1"
CARD_STAGE = "anki"

OPENAI_CARD_PROMPT = """You are LectureDigest's expert Anki card writer.
Create high-quality long-term memory cards from the approved Korean study note only.
Use the source transcript snippets only for evidence and traceability.
Return JSON only. Do not wrap the JSON in Markdown fences.

Hard requirements:
- Create one learning point per card.
- Use only supported card types: qa, cloze, code, application.
- Do not reveal the answer directly in front.
- Do not create broad summary questions.
- Preserve beginner-friendly explanations for acronyms and difficult concepts from the approved note.
- Generate code cards only when the note contains code, command, file name, function, or API evidence.
- Generate application cards from practical/action sections only.
- Do not add facts unsupported by the approved note or source snippets.
- Include source_segment_ids on every card.
- Do not write visible source labels, segment ids, or timestamps in front/back/cloze_text.
- Keep source and timestamps in metadata only.

Response shape:
{"cards":[{"card_type":"qa","note_section_id":"...","front":"...","back":"...","cloze_text":"","extra":"","difficulty":"beginner","source_segment_ids":["seg-1"]}]}"""


def build_card_request(
    record: LectureRecord,
    *,
    sections: list[dict[str, object]],
    batch_id: str,
    card_types: list[str],
    plan: CardGenerationPlan,
    model: str = DEFAULT_OPENAI_CARD_MODEL,
    prompt_version: str = DEFAULT_OPENAI_CARD_PROMPT_VERSION,
) -> OpenAIRequest:
    payload = {
        "model": model,
        "input": [
            {
                "role": "system",
                "content": [{"type": "input_text", "text": OPENAI_CARD_PROMPT}],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": json.dumps(
                            _prompt_contract(record, sections, batch_id, card_types, plan),
                            ensure_ascii=False,
                        ),
                    }
                ],
            },
        ],
        "text": {"format": {"type": "json_object"}},
        "max_output_tokens": _max_output_tokens(plan),
    }
    body = json_body(payload)
    return OpenAIRequest(
        endpoint=OPENAI_CARD_ENDPOINT,
        use_case=OPENAI_CARD_USE_CASE,
        model=model,
        prompt_version=prompt_version,
        body=body,
        input_size_bytes=len(body),
        external_data_boundary="approved note sections and source snippets to OpenAI Responses API",
    )


def _prompt_contract(
    record: LectureRecord,
    sections: list[dict[str, object]],
    batch_id: str,
    card_types: list[str],
    plan: CardGenerationPlan,
) -> dict[str, object]:
    return {
        "contract": {
            "language": "ko",
            "batch_id": batch_id,
            "allowed_card_types": card_types,
            "target_card_count_for_whole_note": plan.target_card_count,
            "adaptive_strategy": plan.strategy,
            "source_note_candidate_id": record.approved_note.get("candidate_id", ""),
            "quality_rules": [
                "one_card_one_learning_point",
                "front_must_not_contain_answer",
                "front_must_not_contain_source_or_timestamp",
                "source_segment_ids_required",
                "no_unsupported_facts",
                "flag_or_omit_weak_cards",
            ],
        },
        "lecture": {
            "lecture_id": record.lecture_id,
            "title": record.title,
            "category": record.category,
        },
        "approved_note": {
            "candidate_id": record.approved_note.get("candidate_id", ""),
            "sections": [_section_payload(record, section) for section in sections],
        },
    }


def _section_payload(
    record: LectureRecord,
    section: dict[str, object],
) -> dict[str, object]:
    source_ids = [str(item) for item in _as_list(section.get("segment_ids", []))]
    source_lookup = {segment.segment_id: segment for segment in record.segments}
    return {
        "note_section_id": str(section.get("note_section_id") or section.get("section_key") or ""),
        "section_key": str(section.get("section_key") or ""),
        "title": str(section.get("title") or ""),
        "text": str(section.get("text") or ""),
        "source_segment_ids": source_ids,
        "source_snippets": [
            _segment_payload(source_lookup[segment_id])
            for segment_id in source_ids
            if segment_id in source_lookup
        ],
    }


def _segment_payload(segment: TranscriptSegment) -> dict[str, object]:
    return {
        "segment_id": segment.segment_id,
        "start_ts": segment.start_ts,
        "end_ts": segment.end_ts,
        "text": segment.text[:500],
        "ocr_text": (segment.ocr_text or "")[:300],
    }


def _max_output_tokens(plan: CardGenerationPlan) -> int:
    if plan.strategy in {"expanded", "chaptered"}:
        return 8000
    if plan.strategy == "standard":
        return 6000
    return 4000


def _as_list(value: object) -> list[object]:
    if not isinstance(value, list):
        return []
    return value

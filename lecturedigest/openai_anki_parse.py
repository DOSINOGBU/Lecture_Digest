from __future__ import annotations

import json
import re

from lecturedigest.anki_card_factory import source_label
from lecturedigest.anki_policy import SUPPORTED_CARD_TYPES
from lecturedigest.anki_validation import validate_card
from lecturedigest.errors import AnkiExportError, ErrorDetail
from lecturedigest.models import LectureRecord, TranscriptSegment
from lecturedigest.openai_anki_prompt import (
    CARD_STAGE,
    OPENAI_CARD_ENDPOINT,
    OPENAI_CARD_USE_CASE,
)
from lecturedigest.openai_types import OpenAIClientResult

SEGMENT_ID_PATTERN = re.compile(r"seg-[0-9A-Za-z_-]+", re.IGNORECASE)
DIFFICULTIES = {"beginner", "intermediate", "advanced"}


def parse_card_response(
    data: bytes | str,
    *,
    record: LectureRecord,
    sections: list[dict[str, object]],
    card_types: list[str],
    model: str,
    prompt_version: str,
    client_result: OpenAIClientResult,
) -> list[dict[str, object]]:
    payload = _decode_json(data)
    if "cards" not in payload:
        response_text = _extract_response_text(payload)
        if response_text is None:
            raise _card_error(
                "openai_card_response_malformed",
                "OpenAI card response did not include cards.",
            )
        payload = _decode_json(response_text)

    raw_cards = payload.get("cards")
    if not isinstance(raw_cards, list):
        raise _card_error(
            "openai_card_response_malformed",
            "OpenAI card response `cards` must be a list.",
        )

    section_lookup = _sections_by_id(sections)
    segment_lookup = {segment.segment_id: segment for segment in record.segments}
    return [
        _card_from_payload(
            item,
            record=record,
            section_lookup=section_lookup,
            segment_lookup=segment_lookup,
            card_types=card_types,
            model=model,
            prompt_version=prompt_version,
            client_result=client_result,
        )
        for item in raw_cards
        if isinstance(item, dict)
    ]


def _card_from_payload(
    item: dict[str, object],
    *,
    record: LectureRecord,
    section_lookup: dict[str, dict[str, object]],
    segment_lookup: dict[str, TranscriptSegment],
    card_types: list[str],
    model: str,
    prompt_version: str,
    client_result: OpenAIClientResult,
) -> dict[str, object]:
    card_type = str(item.get("card_type") or "qa").strip()
    unsupported_type = card_type not in SUPPORTED_CARD_TYPES or card_type not in card_types
    if unsupported_type:
        card_type = "qa"
    note_section_id = str(item.get("note_section_id") or "").strip()
    section = section_lookup.get(note_section_id, {})
    source_ids = _source_segment_ids(item)
    source = _source_payload(record, source_ids, segment_lookup, section)
    difficulty = _difficulty(item.get("difficulty"))
    card = {
        "card_id": _card_id(record, note_section_id, card_type, item),
        "lecture_id": record.lecture_id,
        "note_section_id": note_section_id,
        "card_type": card_type,
        "front": str(item.get("front") or "").strip(),
        "back": str(item.get("back") or "").strip(),
        "cloze_text": str(item.get("cloze_text") or "").strip(),
        "extra": str(item.get("extra") or source_label(source)),
        "tags": _tags(record, card_type, difficulty),
        "difficulty": difficulty,
        "source_segment_ids": source_ids,
        "start_ts": source["start_ts"],
        "end_ts": source["end_ts"],
        "jump_link": source["jump_link"],
        "source_note_candidate_id": str(record.approved_note.get("candidate_id") or ""),
        "model": model,
        "prompt_version": prompt_version,
        "source": source,
        "provider_metadata": {
            "provider": "openai_responses",
            "endpoint": client_result.metadata.endpoint or OPENAI_CARD_ENDPOINT,
            "use_case": client_result.metadata.use_case or OPENAI_CARD_USE_CASE,
            "openai_call": client_result.metadata.to_dict(),
        },
    }
    if unsupported_type:
        card["unsupported_fact"] = True
    return validate_card(card)


def _source_segment_ids(item: dict[str, object]) -> list[str]:
    found = []
    raw_ids = item.get("source_segment_ids", [])
    if isinstance(raw_ids, list):
        for raw in raw_ids:
            matches = SEGMENT_ID_PATTERN.findall(str(raw))
            found.extend(matches or [str(raw)])
    unique = []
    for segment_id in found:
        if segment_id and segment_id not in unique:
            unique.append(segment_id)
    return unique


def _source_payload(
    record: LectureRecord,
    segment_ids: list[str],
    segment_lookup: dict[str, TranscriptSegment],
    section: dict[str, object],
) -> dict[str, object]:
    mapped_segments = [segment_lookup[item] for item in segment_ids if item in segment_lookup]
    start_ts = ""
    end_ts = ""
    if mapped_segments:
        start_ts = mapped_segments[0].start_ts
        end_ts = mapped_segments[-1].end_ts
    return {
        "lecture_id": record.lecture_id,
        "lecture_title": record.lecture_title or record.title,
        "title": record.title,
        "chapter": str(section.get("chapter") or "unassigned"),
        "segment_ids": segment_ids,
        "start_ts": start_ts,
        "end_ts": end_ts,
        "jump_link": _jump_link(record, start_ts),
        "mapping_status": "mapped" if segment_ids and start_ts else "flagged",
    }


def _sections_by_id(sections: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    result = {}
    for section in sections:
        for key in ("note_section_id", "section_key"):
            value = str(section.get(key) or "")
            if value and value not in result:
                result[value] = section
    return result


def _difficulty(value: object) -> str:
    normalized = str(value or "beginner").strip()
    return normalized if normalized in DIFFICULTIES else "beginner"


def _tags(record: LectureRecord, card_type: str, difficulty: str) -> list[str]:
    tags = [
        "lecturedigest",
        card_type,
        f"difficulty_{difficulty}",
        "source_approved_note",
        record.category,
    ]
    if record.major_category:
        tags.append(record.major_category)
    if record.middle_category:
        tags.append(record.middle_category)
    return [tag.replace(" ", "_") for tag in tags if tag]


def _card_id(
    record: LectureRecord,
    note_section_id: str,
    card_type: str,
    item: dict[str, object],
) -> str:
    explicit = str(item.get("card_id") or "").strip()
    if explicit:
        return explicit
    seed = f"{note_section_id}:{card_type}:{item.get('front', '')}"
    safe = re.sub(r"[^0-9A-Za-z_-]+", "-", seed)[:80].strip("-")
    return f"{record.lecture_id}:openai:{safe or card_type}"


def _jump_link(record: LectureRecord, start_ts: str) -> str:
    seconds = 0
    if start_ts:
        parts = start_ts.replace(",", ".").split(":")
        if len(parts) == 3:
            try:
                seconds = (
                    int(parts[0]) * 3600
                    + int(parts[1]) * 60
                    + round(float(parts[2]))
                )
            except ValueError:
                seconds = 0
    return f"lecturedigest://lecture/{record.lecture_id}?t={seconds}"


def _decode_json(data: bytes | str) -> dict[str, object]:
    text = data.decode("utf-8", errors="replace") if isinstance(data, bytes) else data
    try:
        payload = json.loads(_strip_json_fence(text.strip()))
    except json.JSONDecodeError as exc:
        raise _card_error(
            "openai_card_response_invalid_json",
            f"OpenAI card response JSON could not be parsed: {exc.msg}",
        ) from exc
    if not isinstance(payload, dict):
        raise _card_error(
            "openai_card_response_malformed",
            "OpenAI card response must be a JSON object.",
        )
    return payload


def _extract_response_text(payload: dict[str, object]) -> str | None:
    output_text = payload.get("output_text")
    if isinstance(output_text, str):
        return output_text
    output = payload.get("output", [])
    if not isinstance(output, list):
        return None
    for item in output:
        if not isinstance(item, dict):
            continue
        content = item.get("content", [])
        if not isinstance(content, list):
            continue
        for content_item in content:
            if not isinstance(content_item, dict):
                continue
            text = content_item.get("text", content_item.get("output_text"))
            if isinstance(text, str):
                return text
    return None


def _strip_json_fence(text: str) -> str:
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if len(lines) >= 3 and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip()
    return text


def _card_error(code: str, message: str) -> AnkiExportError:
    return AnkiExportError(
        ErrorDetail(
            code=code,
            message=message,
            stage=CARD_STAGE,
            retryable=False,
        )
    )

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from hashlib import sha256

from lecturedigest.errors import ErrorDetail, NoteGenerationError
from lecturedigest.models import LectureRecord
from lecturedigest.note_markdown import NoteSourceUnit, source_hash
from lecturedigest.note_prd import (
    CORE_TOPIC_PREFIX,
    REQUIRED_FIXED_SECTION_KEYS,
    default_section_title,
    markdown_from_sections,
    normalize_section_key,
    section_sort_key,
    validate_prd_candidate,
)
from lecturedigest.note_profile import NoteContentProfile, build_content_profile
from lecturedigest.openai_note_prompt import (
    NOTE_STAGE,
    NOTE_VARIANTS,
    OPENAI_NOTE_CANDIDATE_COUNT,
    OPENAI_NOTE_ENDPOINT,
    OPENAI_NOTE_USE_CASE,
)
from lecturedigest.openai_types import OpenAIClientResult

SEGMENT_ID_PATTERN = re.compile(r"seg-\d+")


def parse_note_response(
    data: bytes | str,
    *,
    record: LectureRecord,
    source_units: list[NoteSourceUnit],
    tone: str,
    model: str,
    prompt_version: str,
    client_result: OpenAIClientResult,
    content_profile: NoteContentProfile | None = None,
    expected_count: int = OPENAI_NOTE_CANDIDATE_COUNT,
    variant_index_start: int = 1,
) -> list[dict[str, object]]:
    payload = _decode_json(data)
    if "candidates" not in payload:
        response_text = _extract_response_text(payload)
        if response_text is None:
            raise _note_error(
                "note_response_malformed",
                "OpenAI note response did not include candidates.",
            )
        payload = _decode_json(response_text)

    raw_candidates = payload.get("candidates")
    if not isinstance(raw_candidates, list):
        raise _note_error(
            "note_response_malformed",
            "OpenAI note response `candidates` must be a list.",
        )
    if len(raw_candidates) < expected_count:
        raise _note_error(
            "note_response_incomplete",
            f"OpenAI note response must include {expected_count} candidate(s).",
        )

    return [
        _candidate_from_payload(
            item,
            record=record,
            source_units=source_units,
            tone=tone,
            model=model,
            prompt_version=prompt_version,
            variant_index=index,
            client_result=client_result,
            content_profile=(
                content_profile or build_content_profile(source_units, chunks=record.chunks)
            ),
        )
        for index, item in enumerate(
            raw_candidates[:expected_count],
            start=variant_index_start,
        )
    ]


def _candidate_from_payload(
    item: object,
    *,
    record: LectureRecord,
    source_units: list[NoteSourceUnit],
    tone: str,
    model: str,
    prompt_version: str,
    variant_index: int,
    client_result: OpenAIClientResult,
    content_profile: NoteContentProfile,
) -> dict[str, object]:
    if not isinstance(item, dict):
        raise _note_error(
            "note_response_malformed",
            "Each OpenAI note candidate must be an object.",
        )
    variant = _variant_name(item.get("variant"), variant_index)
    sections = _sections_from_payload(
        item.get("sections"),
        record=record,
        source_units=source_units,
        content_profile=content_profile,
    )
    candidate_id = _candidate_id(
        record,
        source_units,
        model=model,
        prompt_version=prompt_version,
        variant_index=variant_index,
    )
    markdown = markdown_from_sections(title=record.title, sections=sections)
    return {
        "candidate_id": candidate_id,
        "status": "pending_approval",
        "tone": tone,
        "model": model,
        "prompt_version": prompt_version,
        "variant": variant,
        "created_at": datetime.now(UTC).isoformat(),
        "markdown": markdown,
        "sections": sections,
        "generator_notes": _dict_or_empty(item.get("notes")),
        "source_segment_ids": _union_segment_ids(sections),
        "content_profile": content_profile.to_dict(),
        "validation": validate_prd_candidate(
            markdown=markdown,
            sections=sections,
            source_units=source_units,
            content_profile=content_profile,
        ),
        "provider_metadata": {
            "provider": "openai_responses",
            "endpoint": client_result.metadata.endpoint or OPENAI_NOTE_ENDPOINT,
            "use_case": client_result.metadata.use_case or OPENAI_NOTE_USE_CASE,
            "openai_call": client_result.metadata.to_dict(),
        },
    }


def _sections_from_payload(
    raw_sections: object,
    *,
    record: LectureRecord,
    source_units: list[NoteSourceUnit],
    content_profile: NoteContentProfile,
) -> list[dict[str, object]]:
    if not isinstance(raw_sections, list):
        raise _note_error(
            "note_response_malformed",
            "Each OpenAI note candidate must include sections.",
        )
    sections = []
    topic_index = 1
    for order, raw in enumerate(raw_sections, start=1):
        if not isinstance(raw, dict):
            continue
        raw_key = raw.get("section_key")
        raw_role = str(raw.get("section_role") or "").strip().lower()
        fallback_topic_index = topic_index if raw_role == "core_topic" else None
        key = normalize_section_key(raw_key, fallback_topic_index=fallback_topic_index)
        if not key:
            continue
        if key.startswith(CORE_TOPIC_PREFIX):
            topic_index += 1
        text = str(raw.get("text") or "").strip()
        segment_ids = _section_segment_ids(raw, text, source_units)
        start_ts, end_ts = _section_time_range(segment_ids, source_units)
        sections.append(
            {
                "note_section_id": f"{record.lecture_id}:note:{key}",
                "title": str(raw.get("title") or default_section_title(key)),
                "section_key": key,
                "order": order,
                "chapter": _chapter(record),
                "text": text,
                "segment_ids": segment_ids,
                "start_ts": start_ts,
                "end_ts": end_ts,
                "flagged": not text or not segment_ids,
            }
        )
    sections = _with_missing_placeholders(record, sections, source_units, content_profile)
    return sorted(sections, key=section_sort_key)


def _with_missing_placeholders(
    record: LectureRecord,
    sections: list[dict[str, object]],
    source_units: list[NoteSourceUnit],
    content_profile: NoteContentProfile,
) -> list[dict[str, object]]:
    keys = {str(section.get("section_key") or "") for section in sections}
    next_order = len(sections) + 1
    for key in REQUIRED_FIXED_SECTION_KEYS:
        if key in keys:
            continue
        sections.append(
            _placeholder_section(record, key, next_order, source_units, content_profile)
        )
        next_order += 1
    if not any(key.startswith(CORE_TOPIC_PREFIX) for key in keys):
        sections.append(
            _placeholder_section(record, "topic_1", next_order, source_units, content_profile)
        )
    return sections


def _placeholder_section(
    record: LectureRecord,
    key: str,
    order: int,
    source_units: list[NoteSourceUnit],
    content_profile: NoteContentProfile,
) -> dict[str, object]:
    return {
        "note_section_id": f"{record.lecture_id}:note:{key}",
        "title": default_section_title(key),
        "section_key": key,
        "order": order,
        "chapter": _chapter(record),
        "text": "",
        "segment_ids": [],
        "start_ts": None,
        "end_ts": None,
        "flagged": True,
        "flag_reason": "missing_from_openai_response",
        "content_strategy": content_profile.strategy,
    }


def _section_segment_ids(
    raw: dict[str, object],
    text: str,
    source_units: list[NoteSourceUnit],
) -> list[str]:
    valid_ids = {unit.segment_id for unit in source_units}
    found = []
    raw_ids = raw.get("source_segment_ids", [])
    if isinstance(raw_ids, list):
        for item in raw_ids:
            found.extend(SEGMENT_ID_PATTERN.findall(str(item)))
    found.extend(SEGMENT_ID_PATTERN.findall(text))

    unique = []
    for segment_id in found:
        if segment_id in valid_ids and segment_id not in unique:
            unique.append(segment_id)
    return unique


def _section_time_range(
    segment_ids: list[str],
    source_units: list[NoteSourceUnit],
) -> tuple[str | None, str | None]:
    if not segment_ids:
        return None, None
    ordered = [unit for unit in source_units if unit.segment_id in set(segment_ids)]
    if not ordered:
        return None, None
    return ordered[0].start_ts, ordered[-1].end_ts


def _decode_json(data: bytes | str) -> dict[str, object]:
    text = data.decode("utf-8", errors="replace") if isinstance(data, bytes) else data
    try:
        payload = json.loads(_strip_json_fence(text.strip()))
    except json.JSONDecodeError as exc:
        raise _note_error(
            "note_response_invalid_json",
            f"OpenAI note response JSON could not be parsed: {exc.msg}",
        ) from exc
    if not isinstance(payload, dict):
        raise _note_error(
            "note_response_malformed",
            "OpenAI note response must be a JSON object.",
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


def _union_segment_ids(sections: list[dict[str, object]]) -> list[str]:
    ordered = []
    for section in sections:
        ids = section.get("segment_ids", [])
        if not isinstance(ids, list):
            continue
        for segment_id in ids:
            value = str(segment_id)
            if value not in ordered:
                ordered.append(value)
    return ordered


def _dict_or_empty(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _candidate_id(
    record: LectureRecord,
    source_units: list[NoteSourceUnit],
    *,
    model: str,
    prompt_version: str,
    variant_index: int,
) -> str:
    digest = sha256(
        (
            f"{record.lecture_id}:{source_hash(source_units)}:"
            f"{model}:{prompt_version}:{variant_index}"
        ).encode("utf-8")
    ).hexdigest()[:10]
    return f"note-candidate-openai-{digest}-{variant_index:02d}"


def _variant_name(value: object, variant_index: int) -> str:
    normalized = str(value or "").strip()
    if normalized in NOTE_VARIANTS:
        return normalized
    return NOTE_VARIANTS[min(variant_index - 1, len(NOTE_VARIANTS) - 1)]


def _chapter(record: LectureRecord) -> str:
    if record.chunks:
        return record.chunks[0].chapter
    return record.middle_category or record.category or "unassigned"


def _note_error(code: str, message: str) -> NoteGenerationError:
    return NoteGenerationError(
        ErrorDetail(
            code=code,
            message=message,
            stage=NOTE_STAGE,
            retryable=False,
        )
    )

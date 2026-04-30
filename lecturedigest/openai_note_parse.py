from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from hashlib import sha256

from lecturedigest.errors import ErrorDetail, NoteGenerationError
from lecturedigest.models import LectureRecord
from lecturedigest.note_markdown import NoteSourceUnit, source_hash
from lecturedigest.openai_note_prompt import (
    NOTE_STAGE,
    NOTE_VARIANTS,
    OPENAI_NOTE_CANDIDATE_COUNT,
    OPENAI_NOTE_ENDPOINT,
    OPENAI_NOTE_USE_CASE,
    REQUIRED_NOTE_SECTIONS,
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
    )
    candidate_id = _candidate_id(
        record,
        source_units,
        model=model,
        prompt_version=prompt_version,
        variant_index=variant_index,
    )
    markdown = _markdown(
        record=record,
        candidate_id=candidate_id,
        status="pending_approval",
        tone=tone,
        model=model,
        prompt_version=prompt_version,
        provider="openai_responses",
        sections=sections,
        source_units=source_units,
    )
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
        "source_segment_ids": _union_segment_ids(sections),
        "validation": _validate_candidate(markdown, sections, source_units),
        "provider_metadata": {
            "provider": "openai_responses",
            "endpoint": OPENAI_NOTE_ENDPOINT,
            "use_case": OPENAI_NOTE_USE_CASE,
            "openai_call": client_result.metadata.to_dict(),
        },
    }


def _sections_from_payload(
    raw_sections: object,
    *,
    record: LectureRecord,
    source_units: list[NoteSourceUnit],
) -> list[dict[str, object]]:
    if not isinstance(raw_sections, list):
        raise _note_error(
            "note_response_malformed",
            "Each OpenAI note candidate must include sections.",
        )
    section_by_key = {
        str(section.get("section_key") or ""): section
        for section in raw_sections
        if isinstance(section, dict)
    }
    sections = []
    for order, (key, title) in enumerate(REQUIRED_NOTE_SECTIONS, start=1):
        raw = section_by_key.get(key)
        text = str(raw.get("text") or "").strip() if raw else ""
        segment_ids = _section_segment_ids(raw, text, source_units) if raw else []
        start_ts, end_ts = _section_time_range(segment_ids, source_units)
        sections.append(
            {
                "note_section_id": f"{record.lecture_id}:note:{key}",
                "title": title,
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
    return sections


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


def _markdown(
    *,
    record: LectureRecord,
    candidate_id: str,
    status: str,
    tone: str,
    model: str,
    prompt_version: str,
    provider: str,
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
        f"provider: {provider}",
        f"source_start_ts: {source_units[0].start_ts}",
        f"source_end_ts: {source_units[-1].end_ts}",
        f"source_segment_count: {len(source_units)}",
        "---",
    ]
    body = []
    for section in sections:
        body.append(str(section["title"]))
        body.append(str(section.get("text") or ""))
        body.append("")
    return "\n".join(frontmatter + [""] + body).rstrip() + "\n"


def _validate_candidate(
    markdown: str,
    sections: list[dict[str, object]],
    source_units: list[NoteSourceUnit],
) -> dict[str, object]:
    source_length = max(1, len(" ".join(unit.text for unit in source_units)))
    ratio = round(len(markdown) / source_length, 3)
    failed = []
    warnings = []
    missing_sections = [
        str(section["section_key"])
        for section in sections
        if not str(section.get("text") or "").strip()
    ]
    unmapped = [
        str(section["section_key"])
        for section in sections
        if not section.get("segment_ids")
    ]
    if len(sections) != len(REQUIRED_NOTE_SECTIONS):
        failed.append("section_count_mismatch")
    if missing_sections:
        failed.append("required_section_empty")
    if unmapped:
        failed.append("source_mapping_missing")
    if "(source:" not in markdown:
        failed.append("citation_text_missing")
    if ratio < 0.1:
        warnings.append("note_may_be_too_short_for_golden_review")
    return {
        "status": "flagged" if failed else "review_required",
        "length_ratio": ratio,
        "target_length_ratio": "human review required",
        "failed_rules": failed,
        "warnings": warnings,
        "unmapped_sections": unmapped,
        "missing_sections": missing_sections,
        "human_review_required": True,
    }


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


def _yaml_value(value: str) -> str:
    escaped = value.replace('"', '\\"')
    return f'"{escaped}"'


def _note_error(code: str, message: str) -> NoteGenerationError:
    return NoteGenerationError(
        ErrorDetail(
            code=code,
            message=message,
            stage=NOTE_STAGE,
            retryable=False,
        )
    )

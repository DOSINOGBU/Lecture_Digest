from __future__ import annotations

import json

from lecturedigest.errors import ErrorDetail, NoteGenerationError
from lecturedigest.note_markdown import NoteSourceUnit
from lecturedigest.note_profile import NoteContentProfile
from lecturedigest.openai_note_prompt import NOTE_STAGE


def parse_longform_plan(
    data: bytes,
    *,
    source_units: list[NoteSourceUnit],
    content_profile: NoteContentProfile,
) -> dict[str, object]:
    payload = decode_longform_json(data)
    plan = _dict(payload.get("plan") if "plan" in payload else payload)
    raw_topics = _dict_list(plan.get("topics"))
    topics = _normalized_topics(raw_topics, source_units, content_profile)
    if not topics:
        topics = _fallback_topics(source_units, content_profile)
        plan = {**plan, "fallback_plan_used": True}
    return {**plan, "topics": topics}


def parse_longform_sections(data: bytes) -> list[dict[str, object]]:
    payload = decode_longform_json(data)
    sections = payload.get("sections")
    if not isinstance(sections, list):
        candidates = _dict_list(payload.get("candidates"))
        if candidates:
            sections = candidates[0].get("sections")
    if not isinstance(sections, list):
        raise NoteGenerationError(
            ErrorDetail(
                code="longform_sections_malformed",
                message="Longform section response must include sections.",
                stage=NOTE_STAGE,
                retryable=False,
            )
        )
    return [section for section in sections if isinstance(section, dict)]


def topic_batches(
    topics: list[dict[str, object]],
    *,
    batch_size: int,
) -> list[list[dict[str, object]]]:
    return [
        topics[index : index + batch_size]
        for index in range(0, len(topics), batch_size)
    ]


def decode_longform_json(data: bytes | str) -> dict[str, object]:
    text = data.decode("utf-8", errors="replace") if isinstance(data, bytes) else data
    try:
        payload = json.loads(_strip_json_fence(text.strip()))
    except json.JSONDecodeError as exc:
        raise NoteGenerationError(
            ErrorDetail(
                code="longform_response_invalid_json",
                message=f"Longform note response JSON could not be parsed: {exc.msg}",
                stage=NOTE_STAGE,
                retryable=False,
            )
        ) from exc
    if not isinstance(payload, dict):
        raise NoteGenerationError(
            ErrorDetail(
                code="longform_response_malformed",
                message="Longform note response must be a JSON object.",
                stage=NOTE_STAGE,
                retryable=False,
            )
        )
    if not any(key in payload for key in ("plan", "topics", "sections", "candidates")):
        response_text = _extract_response_text(payload)
        if response_text is not None:
            return decode_longform_json(response_text)
    return payload


def _normalized_topics(
    raw_topics: list[dict[str, object]],
    source_units: list[NoteSourceUnit],
    content_profile: NoteContentProfile,
) -> list[dict[str, object]]:
    valid_ids = {unit.segment_id for unit in source_units}
    topics = []
    for index, raw in enumerate(raw_topics, start=1):
        ids = []
        raw_ids = raw.get("source_segment_ids")
        if isinstance(raw_ids, list):
            ids = [str(segment_id) for segment_id in raw_ids if str(segment_id) in valid_ids]
        if not ids:
            ids = _fallback_segment_ids(source_units, index, content_profile)
        topics.append(
            {
                "section_key": str(raw.get("section_key") or f"topic_{index}"),
                "title": str(raw.get("title") or f"## {index}. 핵심 주제"),
                "purpose": str(raw.get("purpose") or ""),
                "style_hint": str(raw.get("style_hint") or "narrative"),
                "source_segment_ids": ids,
            }
        )
    return topics


def _fallback_segment_ids(
    source_units: list[NoteSourceUnit],
    index: int,
    content_profile: NoteContentProfile,
) -> list[str]:
    topic_min = max(1, content_profile.target_counts["core_topics"][0])
    width = max(1, len(source_units) // topic_min)
    start = min(len(source_units) - 1, (index - 1) * width)
    end = min(len(source_units), start + width)
    return [unit.segment_id for unit in source_units[start:end]][:4]


def _fallback_topics(
    source_units: list[NoteSourceUnit],
    content_profile: NoteContentProfile,
) -> list[dict[str, object]]:
    target = content_profile.target_counts["core_topics"][0]
    topic_count = max(1, min(target, len(source_units)))
    return [
        {
            "section_key": f"topic_{index}",
            "title": f"## {index}. 핵심 주제 {index}",
            "purpose": "OpenAI plan response was missing topics, so source ranges were split locally.",
            "style_hint": "narrative",
            "source_segment_ids": _fallback_segment_ids(
                source_units,
                index,
                content_profile,
            ),
        }
        for index in range(1, topic_count + 1)
    ]


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


def _dict(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _dict_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]

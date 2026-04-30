from __future__ import annotations

import re
from dataclasses import dataclass

from lecturedigest.anki_validation import validate_card
from lecturedigest.models import LectureRecord, TranscriptSegment

CODE_TOKEN_PATTERN = re.compile(
    r"`([^`]+)`|\b[A-Za-z_][A-Za-z0-9_]*\.(?:py|js|ts|tsx|jsx|html|css)\b|"
    r"\b[A-Za-z_][A-Za-z0-9_]*\(\)|\b[A-Za-z]+[A-Z][A-Za-z0-9_]*\b"
)
WORD_PATTERN = re.compile(r"[0-9A-Za-z\uac00-\ud7a3]+")
ACTION_SECTION_PATTERN = re.compile(
    r"(?i)(action|apply|practice|task|todo|\uc2e4\ud589|\uc801\uc6a9|\uc2e4\uc2b5|\uacfc\uc81c)"
)
STOPWORDS = {
    "the",
    "and",
    "that",
    "this",
    "from",
    "with",
    "source",
    "lecture",
    "action",
    "flow",
}


@dataclass(frozen=True)
class CardBuildContext:
    record: LectureRecord
    segment_lookup: dict[str, TranscriptSegment]
    card_model: str
    prompt_version: str


def cards_for_section(
    record: LectureRecord,
    section: dict[str, object],
    segment_lookup: dict[str, TranscriptSegment],
    *,
    card_types: list[str],
    card_model: str,
    prompt_version: str,
) -> list[dict[str, object]]:
    context = CardBuildContext(
        record=record,
        segment_lookup=segment_lookup,
        card_model=card_model,
        prompt_version=prompt_version,
    )
    cards = []
    if "qa" in card_types:
        cards.append(_qa_card(context, section))
    if "cloze" in card_types:
        cloze = _cloze_card(context, section)
        if cloze is not None:
            cards.append(cloze)
    if "code" in card_types:
        code = _code_card(context, section)
        if code is not None:
            cards.append(code)
    if "application" in card_types:
        application = _application_card(context, section)
        if application is not None:
            cards.append(application)
    return cards


def source_label(source: object) -> str:
    if not isinstance(source, dict):
        return "source: unmapped"
    segment_ids = ", ".join(str(item) for item in _as_list(source.get("segment_ids", [])))
    if not segment_ids:
        return "source: unmapped"
    return (
        f"source: {segment_ids} @ {source.get('start_ts', '')}-"
        f"{source.get('end_ts', '')}"
    )


def _qa_card(context: CardBuildContext, section: dict[str, object]) -> dict[str, object]:
    title = _section_title(section)
    return validate_card(
        _card_payload(
            context,
            section,
            "qa",
            front=f'How does "{title}" work in this lecture?',
            back=_snippet(_section_text(section), 420),
            source=_source_payload(context, section),
        )
    )


def _cloze_card(
    context: CardBuildContext,
    section: dict[str, object],
) -> dict[str, object] | None:
    text = _first_content_line(_section_text(section))
    keyword = _keyword(text)
    if not text or not keyword:
        return None
    cloze_text = text.replace(keyword, f"{{{{c1::{keyword}}}}}", 1)
    return validate_card(
        _card_payload(
            context,
            section,
            "cloze",
            front=cloze_text,
            back="",
            cloze_text=cloze_text,
            source=_source_payload(context, section),
        )
    )


def _code_card(
    context: CardBuildContext,
    section: dict[str, object],
) -> dict[str, object] | None:
    text = _section_text(section)
    tokens = _code_tokens(text)
    if not tokens:
        return None
    token = tokens[0]
    return validate_card(
        _card_payload(
            context,
            section,
            "code",
            front=f"What role does `{token}` have in this lecture section?",
            back=_snippet(text, 360),
            source=_source_payload(context, section),
        )
    )


def _application_card(
    context: CardBuildContext,
    section: dict[str, object],
) -> dict[str, object] | None:
    if not _is_application_section(section):
        return None
    title = _section_title(section)
    text = _section_text(section)
    if not text:
        return None
    return validate_card(
        _card_payload(
            context,
            section,
            "application",
            front=f'How should you apply "{title}" after the lecture?',
            back=_snippet(text, 420),
            source=_source_payload(context, section),
        )
    )


def _card_payload(
    context: CardBuildContext,
    section: dict[str, object],
    card_type: str,
    *,
    front: str,
    back: str,
    source: dict[str, object],
    cloze_text: str = "",
) -> dict[str, object]:
    note_section_id = _section_id(section)
    difficulty = _difficulty(section)
    record = context.record
    return {
        "card_id": _card_id(record, section, card_type),
        "lecture_id": record.lecture_id,
        "note_section_id": note_section_id,
        "card_type": card_type,
        "front": front,
        "back": back,
        "cloze_text": cloze_text,
        "extra": source_label(source),
        "tags": _tags(record, card_type, difficulty),
        "difficulty": difficulty,
        "source_segment_ids": source["segment_ids"],
        "start_ts": source["start_ts"],
        "end_ts": source["end_ts"],
        "jump_link": source["jump_link"],
        "source_note_candidate_id": str(record.approved_note.get("candidate_id") or ""),
        "model": context.card_model,
        "prompt_version": context.prompt_version,
        "source": source,
    }


def _source_payload(context: CardBuildContext, section: dict[str, object]) -> dict[str, object]:
    record = context.record
    segment_lookup = context.segment_lookup
    segment_ids = [str(value) for value in _as_list(section.get("segment_ids", []))]
    mapped_segments = [segment_lookup[item] for item in segment_ids if item in segment_lookup]
    start_ts = str(section.get("start_ts") or "")
    end_ts = str(section.get("end_ts") or "")
    if mapped_segments:
        start_ts = start_ts or mapped_segments[0].start_ts
        end_ts = end_ts or mapped_segments[-1].end_ts
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


def _is_application_section(section: dict[str, object]) -> bool:
    values = [
        str(section.get("section_key") or ""),
        str(section.get("title") or ""),
        str(section.get("text") or ""),
    ]
    return any(ACTION_SECTION_PATTERN.search(value) for value in values)


def _difficulty(section: dict[str, object]) -> str:
    text = f"{_section_title(section)} {_section_text(section)}".lower()
    if any(marker in text for marker in ("advanced", "architecture", "internal")):
        return "advanced"
    if any(marker in text for marker in ("engine", "api", "dom", "interpreter")):
        return "intermediate"
    return "beginner"


def _section_id(section: dict[str, object]) -> str:
    return str(section.get("note_section_id") or section.get("section_key") or "section")


def _section_title(section: dict[str, object]) -> str:
    return str(section.get("title") or section.get("section_key") or "note section")


def _section_text(section: dict[str, object]) -> str:
    return str(section.get("text") or section.get("body") or "").strip()


def _first_content_line(text: str) -> str:
    for line in text.splitlines():
        cleaned = line.strip(" -")
        if cleaned and not cleaned.endswith(":"):
            return cleaned
    return ""


def _keyword(text: str) -> str:
    for token in WORD_PATTERN.findall(text):
        normalized = token.lower()
        if normalized not in STOPWORDS and len(normalized) >= 3:
            return token
    return ""


def _code_tokens(text: str) -> list[str]:
    tokens = []
    for match in CODE_TOKEN_PATTERN.finditer(text):
        token = match.group(1) or match.group(0)
        if token not in tokens:
            tokens.append(token)
    return tokens


def _card_id(record: LectureRecord, section: dict[str, object], card_type: str) -> str:
    safe_section = re.sub(r"[^0-9A-Za-z_-]+", "-", _section_id(section)).strip("-")
    return f"{record.lecture_id}:{safe_section}:{card_type}"


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


def _snippet(text: str, max_chars: int) -> str:
    compact = " ".join(text.split())
    if len(compact) <= max_chars:
        return compact
    trimmed = compact[: max_chars + 1].rsplit(" ", maxsplit=1)[0]
    return f"{trimmed or compact[:max_chars]}..."


def _as_list(value: object) -> list[object]:
    if not isinstance(value, list):
        return []
    return value

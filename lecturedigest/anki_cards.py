from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from lecturedigest.errors import AnkiExportError, ErrorDetail, ValidationError
from lecturedigest.models import LectureRecord, TranscriptSegment

DEFAULT_CARD_MODEL = "local-anki-card-v1"
DEFAULT_CARD_PROMPT_VERSION = "anki-card-v1"
DEFAULT_DECK_NAME = "LectureDigest"
DEFAULT_MAX_CARDS = 24
SUPPORTED_EXPORT_FORMATS = {"anki_tsv", "json"}
CODE_TOKEN_PATTERN = re.compile(
    r"`([^`]+)`|\b[A-Za-z_][A-Za-z0-9_]*\.(?:py|js|ts|tsx|jsx|html|css)\b|"
    r"\b[A-Za-z_][A-Za-z0-9_]*\(\)|\b[A-Za-z]+[A-Z][A-Za-z0-9_]*\b"
)
WORD_PATTERN = re.compile(r"[0-9A-Za-z가-힣]+")
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
class AnkiExportResult:
    output_path: str
    export_format: str
    exported_count: int
    skipped_flagged_count: int
    retryable: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "output_path": self.output_path,
            "export_format": self.export_format,
            "exported_count": self.exported_count,
            "skipped_flagged_count": self.skipped_flagged_count,
            "retryable": self.retryable,
            "exported_at": _now(),
        }


def generate_anki_cards(
    record: LectureRecord,
    *,
    max_cards: int = DEFAULT_MAX_CARDS,
    card_model: str = DEFAULT_CARD_MODEL,
    prompt_version: str = DEFAULT_CARD_PROMPT_VERSION,
) -> LectureRecord:
    if max_cards <= 0:
        raise ValidationError(
            ErrorDetail(
                code="max_cards_invalid",
                message="max_cards must be at least 1.",
                stage="anki",
                retryable=False,
            )
        )
    normalized_model = _require_text(card_model, "card_model")
    normalized_prompt = _require_text(prompt_version, "prompt_version")
    sections = _approved_note_sections(record)
    segment_lookup = {segment.segment_id: segment for segment in record.segments}

    cards = []
    for section in sections:
        cards.extend(_cards_for_section(record, section, segment_lookup))
        if len(cards) >= max_cards:
            break
    cards = cards[:max_cards]
    valid_count = sum(1 for card in cards if card["status"] == "ready")
    flagged_count = len(cards) - valid_count
    return replace(
        record,
        status="anki_cards_ready",
        stage="anki",
        flashcards=cards,
        card_metadata={
            "model": normalized_model,
            "prompt_version": normalized_prompt,
            "card_count": len(cards),
            "valid_count": valid_count,
            "flagged_count": flagged_count,
            "validity_rate": round(valid_count / len(cards), 3) if cards else 0.0,
            "source": "approved_note",
        },
    )


def export_anki_cards(
    record: LectureRecord,
    *,
    output_path: str | Path,
    export_format: str = "anki_tsv",
    deck_name: str = DEFAULT_DECK_NAME,
    include_flagged: bool = False,
) -> tuple[LectureRecord, AnkiExportResult]:
    normalized_format = _validate_export_format(export_format)
    normalized_deck = _require_text(deck_name, "deck_name")
    if not record.flashcards:
        raise AnkiExportError(
            ErrorDetail(
                code="flashcards_required",
                message="Generate Anki cards before exporting.",
                stage="anki_export",
                retryable=False,
            )
        )

    cards = [
        card
        for card in record.flashcards
        if include_flagged or card.get("status") == "ready"
    ]
    skipped = len(record.flashcards) - len(cards)
    if not cards:
        raise AnkiExportError(
            ErrorDetail(
                code="no_exportable_cards",
                message="No ready Anki cards are available for export.",
                stage="anki_export",
                retryable=False,
            )
        )
    path = Path(output_path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    if normalized_format == "json":
        _write_json(path, record, cards, normalized_deck)
    else:
        _write_tsv(path, cards, normalized_deck)

    result = AnkiExportResult(
        output_path=str(path),
        export_format=normalized_format,
        exported_count=len(cards),
        skipped_flagged_count=skipped,
        retryable=True,
    )
    updated = replace(
        record,
        status="anki_exported",
        stage="anki_export",
        anki_exports=[*record.anki_exports, result.to_dict()],
    )
    return updated, result


def _approved_note_sections(record: LectureRecord) -> list[dict[str, object]]:
    if record.approved_note.get("status") != "approved":
        raise AnkiExportError(
            ErrorDetail(
                code="approved_note_required",
                message="An approved note is required before generating Anki cards.",
                stage="anki",
                retryable=False,
            )
        )
    sections = record.note_sections or _as_dict_list(record.approved_note.get("sections", []))
    if not sections:
        raise AnkiExportError(
            ErrorDetail(
                code="note_sections_required",
                message="Approved note sections are required before generating Anki cards.",
                stage="anki",
                retryable=False,
            )
        )
    return sections


def _cards_for_section(
    record: LectureRecord,
    section: dict[str, object],
    segment_lookup: dict[str, TranscriptSegment],
) -> list[dict[str, object]]:
    cards = [
        _qa_card(record, section, segment_lookup),
    ]
    cloze = _cloze_card(record, section, segment_lookup)
    if cloze is not None:
        cards.append(cloze)
    code = _code_card(record, section, segment_lookup)
    if code is not None:
        cards.append(code)
    return cards


def _qa_card(
    record: LectureRecord,
    section: dict[str, object],
    segment_lookup: dict[str, TranscriptSegment],
) -> dict[str, object]:
    title = _section_title(section)
    source = _source_payload(record, section, segment_lookup)
    card = {
        "card_id": _card_id(record, section, "qa"),
        "card_type": "qa",
        "front": f"{record.title}: what is the key point of {title}?",
        "back": f"{_snippet(_section_text(section), 420)}\n\n{_source_label(source)}",
        "cloze_text": "",
        "extra": _source_label(source),
        "tags": _tags(record, "qa"),
        "source": source,
    }
    return _with_validation(card)


def _cloze_card(
    record: LectureRecord,
    section: dict[str, object],
    segment_lookup: dict[str, TranscriptSegment],
) -> dict[str, object] | None:
    text = _first_content_line(_section_text(section))
    keyword = _keyword(text)
    if not text or not keyword:
        return None
    source = _source_payload(record, section, segment_lookup)
    cloze_text = text.replace(keyword, f"{{{{c1::{keyword}}}}}", 1)
    card = {
        "card_id": _card_id(record, section, "cloze"),
        "card_type": "cloze",
        "front": cloze_text,
        "back": "",
        "cloze_text": cloze_text,
        "extra": _source_label(source),
        "tags": _tags(record, "cloze"),
        "source": source,
    }
    return _with_validation(card)


def _code_card(
    record: LectureRecord,
    section: dict[str, object],
    segment_lookup: dict[str, TranscriptSegment],
) -> dict[str, object] | None:
    text = _section_text(section)
    tokens = _code_tokens(text)
    if not tokens:
        return None
    source = _source_payload(record, section, segment_lookup)
    token = tokens[0]
    card = {
        "card_id": _card_id(record, section, "code"),
        "card_type": "code",
        "front": f"What role does `{token}` have in this lecture section?",
        "back": f"{_snippet(text, 360)}\n\n{_source_label(source)}",
        "cloze_text": "",
        "extra": _source_label(source),
        "tags": _tags(record, "code"),
        "source": source,
    }
    return _with_validation(card)


def _source_payload(
    record: LectureRecord,
    section: dict[str, object],
    segment_lookup: dict[str, TranscriptSegment],
) -> dict[str, object]:
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


def _with_validation(card: dict[str, object]) -> dict[str, object]:
    failed = []
    if not str(card.get("front") or card.get("cloze_text") or "").strip():
        failed.append("front_required")
    if card.get("card_type") != "cloze" and not str(card.get("back") or "").strip():
        failed.append("back_required")
    source = card.get("source", {})
    if not isinstance(source, dict) or source.get("mapping_status") != "mapped":
        failed.append("source_mapping_required")
    status = "ready" if not failed else "flagged"
    return {
        **card,
        "status": status,
        "validation": {
            "status": "passed" if not failed else "flagged",
            "failed_rules": failed,
        },
    }


def _write_tsv(path: Path, cards: list[dict[str, object]], deck_name: str) -> None:
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.writer(output, delimiter="\t", lineterminator="\n")
        writer.writerow(["Deck", "Note Type", "Front", "Back", "Tags", "Source"])
        for card in cards:
            note_type = "Cloze" if card["card_type"] == "cloze" else "Basic"
            front = str(card.get("cloze_text") or card.get("front") or "")
            writer.writerow(
                [
                    deck_name,
                    note_type,
                    front,
                    str(card.get("back") or card.get("extra") or ""),
                    " ".join(str(tag) for tag in _as_list(card.get("tags", []))),
                    _source_label(card.get("source", {})),
                ]
            )


def _write_json(
    path: Path,
    record: LectureRecord,
    cards: list[dict[str, object]],
    deck_name: str,
) -> None:
    path.write_text(
        json.dumps(
            {
                "deck_name": deck_name,
                "lecture_id": record.lecture_id,
                "export_format": "json",
                "cards": cards,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _validate_export_format(export_format: str) -> str:
    normalized = export_format.strip()
    if normalized not in SUPPORTED_EXPORT_FORMATS:
        raise ValidationError(
            ErrorDetail(
                code="anki_export_format_invalid",
                message="export_format must be one of: anki_tsv, json.",
                stage="anki_export",
                retryable=False,
            )
        )
    return normalized


def _require_text(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValidationError(
            ErrorDetail(
                code=f"{field_name}_required",
                message=f"{field_name} is required.",
                stage="anki",
                retryable=False,
            )
        )
    return normalized


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
    section_id = str(section.get("note_section_id") or section.get("section_key"))
    safe_section = re.sub(r"[^0-9A-Za-z_-]+", "-", section_id).strip("-")
    return f"{record.lecture_id}:{safe_section}:{card_type}"


def _tags(record: LectureRecord, card_type: str) -> list[str]:
    tags = ["lecturedigest", card_type, record.category]
    if record.major_category:
        tags.append(record.major_category)
    if record.middle_category:
        tags.append(record.middle_category)
    return [tag.replace(" ", "_") for tag in tags if tag]


def _source_label(source: object) -> str:
    if not isinstance(source, dict):
        return "source: unmapped"
    segment_ids = ", ".join(str(item) for item in _as_list(source.get("segment_ids", [])))
    if not segment_ids:
        return "source: unmapped"
    return (
        f"source: {segment_ids} @ {source.get('start_ts', '')}-"
        f"{source.get('end_ts', '')}"
    )


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


def _as_dict_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _as_list(value: object) -> list[object]:
    if not isinstance(value, list):
        return []
    return value


def _now() -> str:
    return datetime.now(UTC).isoformat()

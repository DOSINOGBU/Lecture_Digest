from __future__ import annotations

import csv
import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from lecturedigest.anki_card_factory import cards_for_section, source_label
from lecturedigest.anki_policy import normalize_card_types, resolve_card_generation_plan
from lecturedigest.anki_validation import remove_duplicate_cards
from lecturedigest.errors import AnkiExportError, ErrorDetail, ValidationError
from lecturedigest.models import LectureRecord

DEFAULT_CARD_MODEL = "local-anki-card-v1"
DEFAULT_CARD_PROMPT_VERSION = "anki-card-v1"
DEFAULT_DECK_NAME = "LectureDigest"
DEFAULT_MAX_CARDS: int | None = None
SUPPORTED_EXPORT_FORMATS = {"anki_tsv", "json"}


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
    max_cards: int | None = DEFAULT_MAX_CARDS,
    card_types: list[str] | str | None = None,
    card_model: str = DEFAULT_CARD_MODEL,
    prompt_version: str = DEFAULT_CARD_PROMPT_VERSION,
) -> LectureRecord:
    normalized_model = _require_text(card_model, "card_model")
    normalized_prompt = _require_text(prompt_version, "prompt_version")
    sections = _approved_note_sections(record)
    segment_lookup = {segment.segment_id: segment for segment in record.segments}
    normalized_types = normalize_card_types(card_types)
    plan = resolve_card_generation_plan(
        record,
        sections,
        max_cards=max_cards,
        card_types=normalized_types,
    )

    cards = []
    for section in sections:
        cards.extend(
            cards_for_section(
                record,
                section,
                segment_lookup,
                card_types=normalized_types,
                card_model=normalized_model,
                prompt_version=normalized_prompt,
            )
        )
    cards, duplicate_count = remove_duplicate_cards(cards)
    cards = cards[: plan.target_card_count]
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
            "removed_duplicate_count": duplicate_count,
            "validity_rate": round(valid_count / len(cards), 3) if cards else 0.0,
            "source": "approved_note",
            "generation_plan": plan.to_dict(),
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
                    source_label(card.get("source", {})),
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

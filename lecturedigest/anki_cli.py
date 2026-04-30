from __future__ import annotations

import argparse
from pathlib import Path

from lecturedigest.anki_cards import (
    DEFAULT_CARD_MODEL,
    DEFAULT_CARD_PROMPT_VERSION,
    DEFAULT_DECK_NAME,
    DEFAULT_MAX_CARDS,
    export_anki_cards,
    generate_anki_cards,
)
from lecturedigest.errors import ErrorDetail, ValidationError
from lecturedigest.storage import JsonLectureRepository


def generate_cards_command(
    args: argparse.Namespace,
    repository: JsonLectureRepository,
) -> int:
    record = _load_record(args.lecture_id, repository, stage="anki")
    if record is None:
        return 0

    print(
        "[LectureAnki] generate-cards start "
        f"{{ lectureId={args.lecture_id}; maxCards={args.max_cards}; "
        f"cardModel={args.card_model}; promptVersion={args.prompt_version} }}"
    )
    updated = generate_anki_cards(
        record,
        max_cards=args.max_cards,
        card_model=args.card_model,
        prompt_version=args.prompt_version,
    )
    repository.save(updated)
    print(format_card_generation_result(updated))
    return 0


def export_anki_command(
    args: argparse.Namespace,
    repository: JsonLectureRepository,
) -> int:
    record = _load_record(args.lecture_id, repository, stage="anki_export")
    if record is None:
        return 0

    print(
        "[LectureAnki] export-anki start "
        f"{{ lectureId={args.lecture_id}; format={args.format}; "
        f"includeFlagged={args.include_flagged}; output={args.output} }}"
    )
    updated, result = export_anki_cards(
        record,
        output_path=args.output,
        export_format=args.format,
        deck_name=args.deck_name,
        include_flagged=args.include_flagged,
    )
    repository.save(updated)
    print(
        "[LectureAnki] export-anki success "
        f"{{ lectureId={updated.lecture_id}; status={updated.status}; "
        f"stage={updated.stage}; exported={result.exported_count}; "
        f"skippedFlagged={result.skipped_flagged_count}; "
        f"output={result.output_path}; retryable={result.retryable} }}"
    )
    return 0


def add_anki_parsers(subparsers: argparse._SubParsersAction) -> None:
    generate_parser = subparsers.add_parser("generate-cards")
    generate_parser.add_argument("--lecture-id", required=True)
    generate_parser.add_argument("--max-cards", type=int, default=DEFAULT_MAX_CARDS)
    generate_parser.add_argument("--card-model", default=DEFAULT_CARD_MODEL)
    generate_parser.add_argument(
        "--prompt-version",
        default=DEFAULT_CARD_PROMPT_VERSION,
    )

    export_parser = subparsers.add_parser("export-anki")
    export_parser.add_argument("--lecture-id", required=True)
    export_parser.add_argument("--output", required=True, type=Path)
    export_parser.add_argument(
        "--format",
        choices=["anki_tsv", "json"],
        default="anki_tsv",
    )
    export_parser.add_argument("--deck-name", default=DEFAULT_DECK_NAME)
    export_parser.add_argument("--include-flagged", action="store_true")


def format_card_generation_result(record) -> str:
    flagged = sum(1 for card in record.flashcards if card.get("status") == "flagged")
    ready = len(record.flashcards) - flagged
    lines = [
        "[LectureAnki] generate-cards success "
        f"{{ lectureId={record.lecture_id}; status={record.status}; "
        f"stage={record.stage}; cards={len(record.flashcards)}; "
        f"ready={ready}; flagged={flagged}; "
        f"validityRate={record.card_metadata.get('validity_rate', 0)} }}"
    ]
    for card in record.flashcards:
        lines.append(
            "- "
            f"{card.get('card_id')} "
            f"type={card.get('card_type')} "
            f"status={card.get('status')}"
        )
    return "\n".join(lines)


def _load_record(
    lecture_id: str,
    repository: JsonLectureRepository,
    *,
    stage: str,
):
    lectures = repository.list_lectures()
    if not lectures:
        print("No lectures registered yet. Add one with `register`.")
        return None

    record = repository.get_lecture(lecture_id)
    if record is None:
        raise ValidationError(
            ErrorDetail(
                code="lecture_not_found",
                message=f"Lecture not found: {lecture_id}",
                stage=stage,
                retryable=False,
            )
        )
    return record

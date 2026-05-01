from __future__ import annotations

from collections.abc import Callable

from lecturedigest.anki_cards import DEFAULT_MAX_CARDS
from lecturedigest.chunking import (
    DEFAULT_CHUNK_OVERLAP_SECONDS,
    DEFAULT_CHUNK_WINDOW_SECONDS,
    chunk_lecture,
)
from lecturedigest.correction import (
    DEFAULT_CORRECTION_CONFIDENCE_THRESHOLD,
    DEFAULT_CORRECTION_MODEL,
    DEFAULT_CORRECTION_PROMPT_VERSION,
)
from lecturedigest.errors import ValidationError
from lecturedigest.media_transcription import (
    should_route_to_large_media,
    transcribe_large_lecture_with_openai,
)
from lecturedigest.models import LectureRecord
from lecturedigest.note_generation import DEFAULT_NOTE_TONE
from lecturedigest.ocr_cli import enrich_lecture_with_openai_ocr
from lecturedigest.openai_anki_cards import generate_anki_cards_with_openai
from lecturedigest.openai_correction import (
    DEFAULT_CORRECTION_BATCH_SIZE,
    correct_transcript_with_openai,
)
from lecturedigest.openai_embeddings import embed_search_index_with_openai
from lecturedigest.openai_notes import generate_note_candidates_with_openai
from lecturedigest.openai_quizzes import generate_quizzes_with_openai
from lecturedigest.openai_transcription import (
    DEFAULT_STT_CHUNKING_STRATEGY,
    transcribe_lecture_with_openai,
)
from lecturedigest.rag import DEFAULT_EMBEDDING_MODEL, DEFAULT_VECTOR_STORE
from lecturedigest.rag import build_search_index
from lecturedigest.transcription import DEFAULT_STT_MODEL, DEFAULT_STT_RESPONSE_FORMAT


def transcribe_step(record: LectureRecord, options) -> LectureRecord:
    try:
        result = transcribe_lecture_with_openai(
            record,
            model=DEFAULT_STT_MODEL,
            response_format=DEFAULT_STT_RESPONSE_FORMAT,
            chunking_strategy=DEFAULT_STT_CHUNKING_STRATEGY,
            dry_run=options.dry_run,
        )
    except ValidationError as exc:
        if not should_route_to_large_media(exc):
            raise
        result = transcribe_large_lecture_with_openai(
            record,
            model=DEFAULT_STT_MODEL,
            response_format=DEFAULT_STT_RESPONSE_FORMAT,
            chunking_strategy=DEFAULT_STT_CHUNKING_STRATEGY,
            dry_run=options.dry_run,
        )
    return result.record


def ocr_step(record: LectureRecord, options) -> LectureRecord:
    return enrich_lecture_with_openai_ocr(record).record


def correct_step(record: LectureRecord, options) -> LectureRecord:
    return correct_transcript_with_openai(
        record,
        model=DEFAULT_CORRECTION_MODEL,
        prompt_version=DEFAULT_CORRECTION_PROMPT_VERSION,
        batch_size=DEFAULT_CORRECTION_BATCH_SIZE,
        confidence_threshold=DEFAULT_CORRECTION_CONFIDENCE_THRESHOLD,
        dry_run=options.dry_run,
    ).record


def chunk_step(record: LectureRecord, options) -> LectureRecord:
    return chunk_lecture(
        record,
        window_seconds=DEFAULT_CHUNK_WINDOW_SECONDS,
        overlap_seconds=DEFAULT_CHUNK_OVERLAP_SECONDS,
        chapter=record.middle_category or record.category or "unassigned",
    )


def index_step(record: LectureRecord, options) -> LectureRecord:
    indexed = build_search_index(
        record,
        embedding_model=DEFAULT_EMBEDDING_MODEL,
        vector_store=DEFAULT_VECTOR_STORE,
    )
    return embed_search_index_with_openai(indexed, model=DEFAULT_EMBEDDING_MODEL).record


def notes_step(
    record: LectureRecord,
    options,
    checkpoint: Callable[[LectureRecord], None],
) -> LectureRecord:
    return generate_note_candidates_with_openai(
        record,
        tone=DEFAULT_NOTE_TONE,
        repair=True,
        candidate_limit=options.note_candidate_count,
        resume=options.resume,
        time_budget_seconds=options.time_budget_seconds,
        checkpoint=checkpoint,
    ).record


def cards_step(
    record: LectureRecord,
    options,
    checkpoint: Callable[[LectureRecord], None],
) -> LectureRecord:
    return generate_anki_cards_with_openai(
        record,
        max_cards=DEFAULT_MAX_CARDS,
        resume=options.resume,
        time_budget_seconds=options.time_budget_seconds,
        checkpoint=checkpoint,
    ).record


def quizzes_step(
    record: LectureRecord,
    options,
    checkpoint: Callable[[LectureRecord], None],
) -> LectureRecord:
    return generate_quizzes_with_openai(
        record,
        resume=options.resume,
        time_budget_seconds=options.time_budget_seconds,
        checkpoint=checkpoint,
    ).record

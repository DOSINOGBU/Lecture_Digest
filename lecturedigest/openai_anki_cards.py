from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, replace

from lecturedigest.anki_policy import normalize_card_types, resolve_card_generation_plan
from lecturedigest.anki_validation import remove_duplicate_cards
from lecturedigest.errors import AnkiExportError, ErrorDetail, ValidationError
from lecturedigest.models import LectureRecord
from lecturedigest.openai_anki_parse import parse_card_response
from lecturedigest.openai_anki_prompt import (
    CARD_STAGE,
    DEFAULT_OPENAI_CARD_MODEL,
    DEFAULT_OPENAI_CARD_PROMPT_VERSION,
    OPENAI_CARD_ENDPOINT,
    OPENAI_CARD_USE_CASE,
    build_card_request,
)
from lecturedigest.openai_client import OpenAIClient, format_dry_run_result
from lecturedigest.openai_types import OpenAIClientResult

DEFAULT_OPENAI_CARD_TIMEOUT_SECONDS = 240.0
DEFAULT_CARD_BATCH_SIZE_SECTIONS = 4


@dataclass(frozen=True)
class OpenAIAnkiCardGenerationResult:
    record: LectureRecord
    client_results: list[OpenAIClientResult]
    dry_run: bool = False


def generate_anki_cards_with_openai(
    record: LectureRecord,
    *,
    client: OpenAIClient | None = None,
    max_cards: int | None = None,
    card_types: list[str] | str | None = None,
    card_model: str = DEFAULT_OPENAI_CARD_MODEL,
    prompt_version: str = DEFAULT_OPENAI_CARD_PROMPT_VERSION,
    dry_run: bool = False,
    resume: bool = False,
    time_budget_seconds: float | None = None,
    batch_size_sections: int = DEFAULT_CARD_BATCH_SIZE_SECTIONS,
    timeout_seconds: float = DEFAULT_OPENAI_CARD_TIMEOUT_SECONDS,
    checkpoint: Callable[[LectureRecord], None] | None = None,
) -> OpenAIAnkiCardGenerationResult:
    if batch_size_sections < 1:
        raise ValidationError(
            ErrorDetail(
                code="batch_size_sections_invalid",
                message="batch_size_sections must be at least 1.",
                stage=CARD_STAGE,
                retryable=False,
            )
        )
    normalized_model = _require_text(card_model, "card_model")
    normalized_prompt = _require_text(prompt_version, "prompt_version")
    sections = _approved_note_sections(record)
    normalized_types = normalize_card_types(card_types)
    plan = resolve_card_generation_plan(
        record,
        sections,
        max_cards=max_cards,
        card_types=normalized_types,
    )
    batches = _section_batches(sections, batch_size_sections)
    openai_client = client or OpenAIClient(timeout_seconds=timeout_seconds)
    started_at = time.perf_counter()
    client_results: list[OpenAIClientResult] = []
    existing_progress = _existing_progress(
        record,
        model=normalized_model,
        prompt_version=normalized_prompt,
    )
    completed_batches = set(existing_progress.get("completed_batches", [])) if resume else set()
    skipped_batches: list[str] = []
    failed_batches: list[dict[str, object]] = []
    cards = list(record.flashcards) if resume and completed_batches else []

    for batch_id, batch_sections in batches:
        if batch_id in completed_batches:
            skipped_batches.append(batch_id)
            continue
        if _time_budget_exhausted(started_at, time_budget_seconds):
            break
        request = build_card_request(
            record,
            sections=batch_sections,
            batch_id=batch_id,
            card_types=normalized_types,
            plan=plan,
            model=normalized_model,
            prompt_version=normalized_prompt,
        )
        result = openai_client.send(request, dry_run=dry_run)
        client_results.append(result)
        if dry_run:
            continue
        if not result.succeeded:
            issue = result.to_processing_issue(stage=CARD_STAGE)
            failed_batches.append(
                {
                    "batch_id": batch_id,
                    "code": issue.code if issue else "openai_card_generation_failed",
                    "message": issue.message if issue else "OpenAI card generation failed.",
                    "retryable": issue.retryable if issue else False,
                    "openai_call": result.metadata.to_dict(),
                }
            )
            continue
        cards.extend(
            parse_card_response(
                result.body,
                record=record,
                sections=batch_sections,
                card_types=normalized_types,
                model=normalized_model,
                prompt_version=normalized_prompt,
                client_result=result,
            )
        )
        cards, _ = remove_duplicate_cards(cards)
        cards = cards[: plan.target_card_count]
        completed_batches.add(batch_id)
        _checkpoint(
            checkpoint,
            _record_with_cards(
                record,
                cards,
                model=normalized_model,
                prompt_version=normalized_prompt,
                plan=plan,
                completed_batches=sorted(completed_batches),
                skipped_batches=skipped_batches,
                failed_batches=failed_batches,
                client_results=client_results,
                batch_ids=[item[0] for item in batches],
                resume=resume,
                batch_size_sections=batch_size_sections,
                time_budget_seconds=time_budget_seconds,
                time_budget_exhausted=_time_budget_exhausted(started_at, time_budget_seconds),
                partial=True,
            ),
        )

    if dry_run:
        return OpenAIAnkiCardGenerationResult(
            record=record,
            client_results=client_results,
            dry_run=True,
        )

    cards, duplicate_count = remove_duplicate_cards(cards)
    cards = cards[: plan.target_card_count]
    partial = _generation_is_partial(
        batch_ids=[item[0] for item in batches],
        completed_batches=sorted(completed_batches),
        failed_batches=failed_batches,
        time_budget_exhausted=_time_budget_exhausted(started_at, time_budget_seconds),
    )
    updated = _record_with_cards(
        record,
        cards,
        model=normalized_model,
        prompt_version=normalized_prompt,
        plan=plan,
        completed_batches=sorted(completed_batches),
        skipped_batches=skipped_batches,
        failed_batches=failed_batches,
        client_results=client_results,
        batch_ids=[item[0] for item in batches],
        resume=resume,
        batch_size_sections=batch_size_sections,
        time_budget_seconds=time_budget_seconds,
        time_budget_exhausted=_time_budget_exhausted(started_at, time_budget_seconds),
        partial=partial,
        duplicate_count=duplicate_count,
    )
    return OpenAIAnkiCardGenerationResult(
        record=updated,
        client_results=client_results,
        dry_run=False,
    )


def format_openai_card_dry_run(result: OpenAIAnkiCardGenerationResult) -> str:
    total_bytes = sum(item.metadata.input_size_bytes for item in result.client_results)
    return "\n".join(
        [
            *[format_dry_run_result(item) for item in result.client_results],
            (
                "[LectureAnki] openai dry-run "
                f"{{ requests={len(result.client_results)}; "
                f"totalInputSizeBytes={total_bytes}; "
                "externalDataBoundary=approved note sections and source snippets "
                "to OpenAI Responses API; willUpload=false; willSave=false }}"
            ),
        ]
    )


def _record_with_cards(
    record: LectureRecord,
    cards: list[dict[str, object]],
    *,
    model: str,
    prompt_version: str,
    plan,
    completed_batches: list[str],
    skipped_batches: list[str],
    failed_batches: list[dict[str, object]],
    client_results: list[OpenAIClientResult],
    batch_ids: list[str],
    resume: bool,
    batch_size_sections: int,
    time_budget_seconds: float | None,
    time_budget_exhausted: bool,
    partial: bool,
    duplicate_count: int = 0,
) -> LectureRecord:
    ready = sum(1 for card in cards if card.get("status") == "ready")
    flagged = len(cards) - ready
    metadata = {
        "provider": "openai_responses",
        "model": model,
        "prompt_version": prompt_version,
        "card_count": len(cards),
        "valid_count": ready,
        "flagged_count": flagged,
        "removed_duplicate_count": duplicate_count,
        "validity_rate": round(ready / len(cards), 3) if cards else 0.0,
        "source": "approved_note",
        "source_note_candidate_id": str(record.approved_note.get("candidate_id") or ""),
        "generation_plan": plan.to_dict(),
        "generation_progress": _generation_progress(
            batch_ids=batch_ids,
            completed_batches=completed_batches,
            skipped_batches=skipped_batches,
            failed_batches=failed_batches,
            client_results=client_results,
            resume=resume,
            batch_size_sections=batch_size_sections,
            time_budget_seconds=time_budget_seconds,
            time_budget_exhausted=time_budget_exhausted,
            partial=partial,
        ),
        "last_card_calls": [result.metadata.to_dict() for result in client_results],
    }
    return replace(
        record,
        status="anki_cards_partial" if partial else "anki_cards_ready",
        stage=CARD_STAGE,
        flashcards=cards,
        card_metadata=metadata,
    )


def _generation_progress(
    *,
    batch_ids: list[str],
    completed_batches: list[str],
    skipped_batches: list[str],
    failed_batches: list[dict[str, object]],
    client_results: list[OpenAIClientResult],
    resume: bool,
    batch_size_sections: int,
    time_budget_seconds: float | None,
    time_budget_exhausted: bool,
    partial: bool,
) -> dict[str, object]:
    failed = [str(item.get("batch_id") or "") for item in failed_batches]
    pending = [
        batch_id
        for batch_id in batch_ids
        if batch_id not in completed_batches and batch_id not in failed
    ]
    return {
        "status": "partial" if partial else "completed",
        "requested_batches": batch_ids,
        "completed_batches": completed_batches,
        "pending_batches": pending,
        "failed_batches": failed_batches,
        "skipped_batches": skipped_batches,
        "resume": resume,
        "batch_size_sections": batch_size_sections,
        "time_budget_seconds": time_budget_seconds,
        "time_budget_exhausted": time_budget_exhausted,
        "call_count": len(client_results),
        "calls": [result.metadata.to_dict() for result in client_results],
    }


def _section_batches(
    sections: list[dict[str, object]],
    batch_size_sections: int,
) -> list[tuple[str, list[dict[str, object]]]]:
    return [
        (f"batch-{index + 1:03d}", sections[start : start + batch_size_sections])
        for index, start in enumerate(range(0, len(sections), batch_size_sections))
    ]


def _approved_note_sections(record: LectureRecord) -> list[dict[str, object]]:
    if record.approved_note.get("status") != "approved":
        raise AnkiExportError(
            ErrorDetail(
                code="approved_note_required",
                message="An approved note is required before generating AI Anki cards.",
                stage=CARD_STAGE,
                retryable=False,
            )
        )
    sections = record.note_sections or _as_dict_list(record.approved_note.get("sections", []))
    if not sections:
        raise AnkiExportError(
            ErrorDetail(
                code="note_sections_required",
                message="Approved note sections are required before generating AI Anki cards.",
                stage=CARD_STAGE,
                retryable=False,
            )
        )
    return sections


def _existing_progress(
    record: LectureRecord,
    *,
    model: str,
    prompt_version: str,
) -> dict[str, object]:
    metadata = record.card_metadata if isinstance(record.card_metadata, dict) else {}
    if (
        metadata.get("provider") != "openai_responses"
        or metadata.get("model") != model
        or metadata.get("prompt_version") != prompt_version
    ):
        return {}
    progress = metadata.get("generation_progress")
    return progress if isinstance(progress, dict) else {}


def _generation_is_partial(
    *,
    batch_ids: list[str],
    completed_batches: list[str],
    failed_batches: list[dict[str, object]],
    time_budget_exhausted: bool,
) -> bool:
    if failed_batches or time_budget_exhausted:
        return True
    return len(completed_batches) < len(batch_ids)


def _time_budget_exhausted(
    started_at: float,
    time_budget_seconds: float | None,
) -> bool:
    if time_budget_seconds is None:
        return False
    return time.perf_counter() - started_at >= time_budget_seconds


def _checkpoint(
    checkpoint: Callable[[LectureRecord], None] | None,
    record: LectureRecord,
) -> None:
    if checkpoint is not None:
        checkpoint(record)


def _require_text(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValidationError(
            ErrorDetail(
                code=f"{field_name}_required",
                message=f"{field_name} is required.",
                stage=CARD_STAGE,
                retryable=False,
            )
        )
    return normalized


def _as_dict_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import replace

from lecturedigest.errors import ErrorDetail, NoteGenerationError
from lecturedigest.models import LectureRecord
from lecturedigest.openai_note_prompt import NOTE_STAGE, NOTE_VARIANTS
from lecturedigest.openai_types import OpenAIClientResult


def selected_variants(
    variants: list[str] | None,
    *,
    candidate_limit: int | None,
) -> list[str]:
    requested = variants or list(NOTE_VARIANTS)
    selected = []
    for variant in requested:
        if variant not in NOTE_VARIANTS:
            raise NoteGenerationError(
                ErrorDetail(
                    code="unsupported_note_variant",
                    message=f"Unsupported note variant: {variant}",
                    stage=NOTE_STAGE,
                    retryable=False,
                )
            )
        if variant not in selected:
            selected.append(variant)
    if candidate_limit is not None:
        if candidate_limit < 1:
            raise NoteGenerationError(
                ErrorDetail(
                    code="invalid_candidate_limit",
                    message="candidate_limit must be 1 or greater.",
                    stage=NOTE_STAGE,
                    retryable=False,
                )
            )
        selected = selected[:candidate_limit]
    return selected


def existing_candidates_by_variant(
    record: LectureRecord,
    *,
    model: str,
    prompt_version: str,
    source_digest: str,
) -> dict[str, dict[str, object]]:
    metadata = record.note_metadata if isinstance(record.note_metadata, dict) else {}
    if (
        metadata.get("model") != model
        or metadata.get("prompt_version") != prompt_version
        or metadata.get("source_hash") != source_digest
    ):
        return {}
    result = {}
    for candidate in record.note_candidates:
        if not isinstance(candidate, dict):
            continue
        variant = str(candidate.get("variant") or "")
        if variant and variant not in result:
            result[variant] = candidate
    return result


def record_with_note_candidates(
    record: LectureRecord,
    candidates: list[dict[str, object]],
    *,
    selected_variants: list[str],
    failed_variants: list[dict[str, object]],
    skipped_variants: list[str],
    repair_summaries: list[dict[str, object]],
    client_results: list[OpenAIClientResult],
    model: str,
    prompt_version: str,
    tone: str,
    source_digest: str,
    content_profile,
    repair: bool,
    max_repair_attempts: int,
    resume: bool,
    candidate_limit: int | None,
    time_budget_seconds: float | None,
    time_budget_exhausted: bool,
    partial: bool,
) -> LectureRecord:
    approved_note = stale_approved_note(
        record.approved_note,
        model=model,
        prompt_version=prompt_version,
    )
    metadata = {
        "provider": "openai_responses",
        "model": model,
        "prompt_version": prompt_version,
        "tone": tone,
        "candidate_count": len(candidates),
        "source_hash": source_digest,
        "content_profile": content_profile.to_dict(),
        "approved_note_stale": approved_note.get("status") == "stale",
        "repair_requested": repair,
        "max_repair_attempts": max_repair_attempts if repair else 0,
        "repair_attempted_count": len(repair_summaries),
        "repair_success_count": sum(1 for item in repair_summaries if item.get("applied")),
        "repair_summaries": repair_summaries,
        "last_note_call": client_results[-1].metadata.to_dict() if client_results else {},
        "last_note_calls": [result.metadata.to_dict() for result in client_results],
        "generation_progress": generation_progress(
            candidates,
            selected_variants=selected_variants,
            failed_variants=failed_variants,
            skipped_variants=skipped_variants,
            client_results=client_results,
            repair=repair,
            max_repair_attempts=max_repair_attempts,
            resume=resume,
            candidate_limit=candidate_limit,
            time_budget_seconds=time_budget_seconds,
            time_budget_exhausted=time_budget_exhausted,
            partial=partial,
        ),
    }
    return replace(
        record,
        status="note_candidates_partial" if partial else "note_candidates_ready",
        stage=NOTE_STAGE,
        note_candidates=candidates,
        approved_note=approved_note,
        note_metadata=metadata,
    )


def generation_progress(
    candidates: list[dict[str, object]],
    *,
    selected_variants: list[str],
    failed_variants: list[dict[str, object]],
    skipped_variants: list[str],
    client_results: list[OpenAIClientResult],
    repair: bool,
    max_repair_attempts: int,
    resume: bool,
    candidate_limit: int | None,
    time_budget_seconds: float | None,
    time_budget_exhausted: bool,
    partial: bool,
) -> dict[str, object]:
    completed = completed_variants(candidates)
    failed = [str(item.get("variant") or "") for item in failed_variants]
    pending = [
        variant
        for variant in selected_variants
        if variant not in completed and variant not in failed
    ]
    return {
        "status": "partial" if partial else "completed",
        "requested_variants": selected_variants,
        "completed_variants": completed,
        "pending_variants": pending,
        "failed_variants": failed_variants,
        "skipped_variants": skipped_variants,
        "resume": resume,
        "candidate_limit": candidate_limit,
        "time_budget_seconds": time_budget_seconds,
        "time_budget_exhausted": time_budget_exhausted,
        "call_count": len(client_results),
        "max_possible_calls": len(selected_variants)
        * (1 + (max_repair_attempts if repair else 0)),
        "calls": [result.metadata.to_dict() for result in client_results],
    }


def generation_is_partial(
    candidates: list[dict[str, object]],
    *,
    selected_variants: list[str],
    failed_variants: list[dict[str, object]],
    time_budget_exhausted: bool,
) -> bool:
    if time_budget_exhausted or failed_variants:
        return True
    return len(completed_variants(candidates)) < len(selected_variants)


def completed_variants(candidates: list[dict[str, object]]) -> list[str]:
    completed = []
    for candidate in candidates:
        variant = str(candidate.get("variant") or "")
        if variant and variant not in completed:
            completed.append(variant)
    return completed


def time_budget_exhausted(
    started_at: float | None,
    time_budget_seconds: float | None,
) -> bool:
    if started_at is None or time_budget_seconds is None:
        return False
    return time.perf_counter() - started_at >= time_budget_seconds


def checkpoint_record(
    checkpoint: Callable[[LectureRecord], None] | None,
    record: LectureRecord,
) -> None:
    if checkpoint is not None:
        checkpoint(record)


def stale_approved_note(
    approved_note: dict[str, object],
    *,
    model: str,
    prompt_version: str,
) -> dict[str, object]:
    if not approved_note:
        return {}
    if (
        approved_note.get("model") == model
        and approved_note.get("prompt_version") == prompt_version
    ):
        return approved_note
    return {
        **approved_note,
        "status": "stale",
        "stale_reason": "model_or_prompt_version_changed",
    }

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, replace

from lecturedigest.errors import ErrorDetail, QuizGenerationError, ValidationError
from lecturedigest.models import LectureRecord
from lecturedigest.openai_client import OpenAIClient, format_dry_run_result
from lecturedigest.openai_quiz_parse import parse_quiz_response
from lecturedigest.openai_quiz_prompt import (
    DEFAULT_OPENAI_QUIZ_MODEL,
    DEFAULT_OPENAI_QUIZ_PROMPT_VERSION,
    QUIZ_STAGE,
    build_quiz_request,
)
from lecturedigest.openai_types import OpenAIClientResult
from lecturedigest.quiz_policy import normalize_question_types, resolve_quiz_generation_plan
from lecturedigest.quiz_validation import remove_duplicate_quiz_items

DEFAULT_OPENAI_QUIZ_TIMEOUT_SECONDS = 240.0
DEFAULT_QUIZ_BATCH_SIZE_SECTIONS = 4


@dataclass(frozen=True)
class OpenAIQuizGenerationResult:
    record: LectureRecord
    client_results: list[OpenAIClientResult]
    dry_run: bool = False


def generate_quizzes_with_openai(
    record: LectureRecord,
    *,
    client: OpenAIClient | None = None,
    quiz_count: int | None = None,
    seed: int | None = None,
    question_types: list[str] | None = None,
    quiz_model: str = DEFAULT_OPENAI_QUIZ_MODEL,
    prompt_version: str = DEFAULT_OPENAI_QUIZ_PROMPT_VERSION,
    dry_run: bool = False,
    resume: bool = False,
    time_budget_seconds: float | None = None,
    batch_size_sections: int = DEFAULT_QUIZ_BATCH_SIZE_SECTIONS,
    timeout_seconds: float = DEFAULT_OPENAI_QUIZ_TIMEOUT_SECONDS,
    checkpoint: Callable[[LectureRecord], None] | None = None,
) -> OpenAIQuizGenerationResult:
    if batch_size_sections < 1:
        raise ValidationError(
            ErrorDetail(
                code="batch_size_sections_invalid",
                message="batch_size_sections must be at least 1.",
                stage=QUIZ_STAGE,
                retryable=False,
            )
        )
    normalized_model = _require_text(quiz_model, "quiz_model")
    normalized_prompt = _require_text(prompt_version, "prompt_version")
    normalized_types = normalize_question_types(question_types)
    sections = _approved_note_sections(record)
    ready_cards = _ready_cards(record)
    plan = resolve_quiz_generation_plan(
        record,
        sections,
        ready_cards,
        quiz_count=quiz_count,
        question_types=normalized_types,
    )
    batches = _section_batches(sections, batch_size_sections)
    openai_client = client or OpenAIClient(timeout_seconds=timeout_seconds)
    started_at = time.perf_counter()
    client_results: list[OpenAIClientResult] = []
    failed_batches: list[dict[str, object]] = []
    skipped_batches: list[str] = []
    existing_progress = _existing_progress(
        record,
        model=normalized_model,
        prompt_version=normalized_prompt,
    )
    completed_batches = set(existing_progress.get("completed_batches", [])) if resume else set()
    quiz_items = list(record.quiz_items) if resume and completed_batches else []

    for batch_id, batch_sections in batches:
        if batch_id in completed_batches:
            skipped_batches.append(batch_id)
            continue
        if _time_budget_exhausted(started_at, time_budget_seconds):
            break
        batch_cards = _cards_for_sections(ready_cards, batch_sections)
        request = build_quiz_request(
            record,
            sections=batch_sections,
            ready_cards=batch_cards,
            batch_id=batch_id,
            question_types=normalized_types,
            plan=plan,
            seed=seed,
            model=normalized_model,
            prompt_version=normalized_prompt,
        )
        result = openai_client.send(request, dry_run=dry_run)
        client_results.append(result)
        if dry_run:
            continue
        if not result.succeeded:
            failed_batches.append(_failed_batch(batch_id, result))
            _checkpoint(
                checkpoint,
                _record_with_quizzes(
                    record,
                    quiz_items,
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
                    seed=seed,
                ),
            )
            continue
        quiz_items.extend(
            parse_quiz_response(
                result.body,
                record=record,
                sections=batch_sections,
                ready_cards=batch_cards,
                question_types=normalized_types,
                model=normalized_model,
                prompt_version=normalized_prompt,
                client_result=result,
            )
        )
        quiz_items, _ = remove_duplicate_quiz_items(quiz_items)
        quiz_items = quiz_items[: plan.target_quiz_count]
        completed_batches.add(batch_id)
        _checkpoint(
            checkpoint,
            _record_with_quizzes(
                record,
                quiz_items,
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
                seed=seed,
            ),
        )

    if dry_run:
        return OpenAIQuizGenerationResult(record=record, client_results=client_results, dry_run=True)

    quiz_items, duplicate_count = remove_duplicate_quiz_items(quiz_items)
    quiz_items = quiz_items[: plan.target_quiz_count]
    partial = _generation_is_partial(
        batch_ids=[item[0] for item in batches],
        completed_batches=sorted(completed_batches),
        failed_batches=failed_batches,
        time_budget_exhausted=_time_budget_exhausted(started_at, time_budget_seconds),
    )
    updated = _record_with_quizzes(
        record,
        quiz_items,
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
        seed=seed,
    )
    return OpenAIQuizGenerationResult(record=updated, client_results=client_results)


def format_openai_quiz_dry_run(result: OpenAIQuizGenerationResult) -> str:
    total_bytes = sum(item.metadata.input_size_bytes for item in result.client_results)
    return "\n".join(
        [
            *[format_dry_run_result(item) for item in result.client_results],
            (
                "[LectureQuiz] openai dry-run "
                f"{{ requests={len(result.client_results)}; "
                f"totalInputSizeBytes={total_bytes}; "
                "externalDataBoundary=approved note sections, ready cards, "
                "and source snippets to OpenAI Responses API; "
                "willUpload=false; willSave=false }}"
            ),
        ]
    )


def _record_with_quizzes(
    record: LectureRecord,
    quiz_items: list[dict[str, object]],
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
    seed: int | None,
    duplicate_count: int = 0,
) -> LectureRecord:
    ready = sum(1 for item in quiz_items if item.get("status") == "ready")
    flagged = len(quiz_items) - ready
    metadata = {
        "provider": "openai_responses",
        "model": model,
        "prompt_version": prompt_version,
        "quiz_count": len(quiz_items),
        "ready_count": ready,
        "flagged_count": flagged,
        "removed_duplicate_count": duplicate_count,
        "seed": seed,
        "question_types": plan.question_types,
        "source": "approved_note_ready_cards" if plan.ready_card_count else "approved_note",
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
        "last_quiz_calls": [result.metadata.to_dict() for result in client_results],
    }
    return replace(
        record,
        status="quizzes_partial" if partial else "quizzes_ready",
        stage=QUIZ_STAGE,
        quiz_items=quiz_items,
        quiz_metadata=metadata,
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
        raise QuizGenerationError(
            ErrorDetail(
                code="approved_note_required",
                message="An approved note is required before generating AI quizzes.",
                stage=QUIZ_STAGE,
                retryable=False,
            )
        )
    sections = record.note_sections or _as_dict_list(record.approved_note.get("sections", []))
    if not sections:
        raise QuizGenerationError(
            ErrorDetail(
                code="note_sections_required",
                message="Approved note sections are required before generating AI quizzes.",
                stage=QUIZ_STAGE,
                retryable=False,
            )
        )
    return sections


def _ready_cards(record: LectureRecord) -> list[dict[str, object]]:
    return [
        card
        for card in record.flashcards
        if isinstance(card, dict) and card.get("status") == "ready"
    ]


def _cards_for_sections(
    ready_cards: list[dict[str, object]],
    sections: list[dict[str, object]],
) -> list[dict[str, object]]:
    section_ids = {
        str(section.get("note_section_id") or section.get("section_key") or "")
        for section in sections
    }
    return [
        card
        for card in ready_cards
        if str(card.get("note_section_id") or "") in section_ids
    ]


def _existing_progress(
    record: LectureRecord,
    *,
    model: str,
    prompt_version: str,
) -> dict[str, object]:
    metadata = record.quiz_metadata if isinstance(record.quiz_metadata, dict) else {}
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


def _failed_batch(batch_id: str, result: OpenAIClientResult) -> dict[str, object]:
    issue = result.to_processing_issue(stage=QUIZ_STAGE)
    return {
        "batch_id": batch_id,
        "code": issue.code if issue else "openai_quiz_generation_failed",
        "message": issue.message if issue else "OpenAI quiz generation failed.",
        "retryable": issue.retryable if issue else False,
        "openai_call": result.metadata.to_dict(),
    }


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
                stage=QUIZ_STAGE,
                retryable=False,
            )
        )
    return normalized


def _as_dict_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]

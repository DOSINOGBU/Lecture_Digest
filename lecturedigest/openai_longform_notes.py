from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, replace

from lecturedigest.errors import ErrorDetail, NoteGenerationError
from lecturedigest.models import LectureRecord
from lecturedigest.note_markdown import NoteSourceUnit, source_hash
from lecturedigest.note_profile import NoteContentProfile
from lecturedigest.openai_client import OpenAIClient
from lecturedigest.openai_longform_note_assembly import parse_assembly_or_fallback
from lecturedigest.openai_longform_note_parse import (
    parse_longform_plan,
    parse_longform_sections,
    topic_batches,
)
from lecturedigest.openai_longform_note_repair import (
    first_auto_approvable_candidate_id,
    repair_longform_candidates,
)
from lecturedigest.openai_longform_note_requests import LONGFORM_NOTE_PROMPT_VERSION
from lecturedigest.openai_longform_note_requests import LONGFORM_TOPIC_BATCH_SIZE
from lecturedigest.openai_longform_note_requests import build_longform_assembly_request
from lecturedigest.openai_longform_note_requests import build_longform_plan_request
from lecturedigest.openai_longform_note_requests import build_longform_section_request
from lecturedigest.openai_note_progress import checkpoint_record
from lecturedigest.openai_note_progress import existing_candidates_by_variant
from lecturedigest.openai_note_progress import generation_is_partial
from lecturedigest.openai_note_progress import record_with_note_candidates
from lecturedigest.openai_note_progress import selected_variants as select_note_variants
from lecturedigest.openai_note_progress import time_budget_exhausted
from lecturedigest.openai_note_prompt import DEFAULT_OPENAI_NOTE_MODEL
from lecturedigest.openai_note_prompt import NOTE_STAGE, NOTE_VARIANTS
from lecturedigest.openai_types import OpenAIClientResult, OpenAIRequest

LONGFORM_RETRY_ATTEMPTS = 2

@dataclass(frozen=True)
class LongformNoteGenerationResult:
    record: LectureRecord
    client_results: list[OpenAIClientResult]
    dry_run: bool = False
    repair_requested: bool = False
    max_repair_attempts: int = 0


def should_use_longform_notes(
    record: LectureRecord,
    content_profile: NoteContentProfile,
) -> bool:
    return (
        content_profile.strategy in {"expanded", "chaptered"}
        or len(record.chunks) >= 12
    )


def generate_longform_note_candidates_with_openai(
    record: LectureRecord,
    *,
    client: OpenAIClient,
    source_units: list[NoteSourceUnit],
    content_profile: NoteContentProfile,
    tone: str,
    model: str = DEFAULT_OPENAI_NOTE_MODEL,
    prompt_version: str = LONGFORM_NOTE_PROMPT_VERSION,
    dry_run: bool = False,
    repair: bool = False,
    max_repair_attempts: int = 1,
    variants: list[str] | None = None,
    candidate_limit: int | None = None,
    resume: bool = False,
    time_budget_seconds: float | None = None,
    checkpoint: Callable[[LectureRecord], None] | None = None,
) -> LongformNoteGenerationResult:
    selected = select_note_variants(variants, candidate_limit=candidate_limit)
    source_digest = source_hash(source_units)
    started_at = time.perf_counter()
    client_results: list[OpenAIClientResult] = []

    if dry_run:
        for variant in selected:
            client_results.append(
                client.send(
                    build_longform_plan_request(
                        record,
                        source_units=source_units,
                        content_profile=content_profile,
                        tone=tone,
                        model=model,
                        prompt_version=prompt_version,
                        variant=variant,
                    ),
                    dry_run=True,
                )
            )
        return LongformNoteGenerationResult(
            record=record,
            client_results=client_results,
            dry_run=True,
            repair_requested=repair,
            max_repair_attempts=max_repair_attempts if repair else 0,
        )

    existing = existing_candidates_by_variant(
        record,
        model=model,
        prompt_version=prompt_version,
        source_digest=source_digest,
    )
    candidates: list[dict[str, object]] = []
    failed_variants: list[dict[str, object]] = []
    skipped_variants: list[str] = []
    repair_summaries: list[dict[str, object]] = []
    plans: dict[str, object] = {}
    section_batches: list[dict[str, object]] = []

    for variant in selected:
        variant_index = NOTE_VARIANTS.index(variant) + 1
        if resume and variant in existing:
            candidates.append(existing[variant])
            skipped_variants.append(variant)
            continue
        if time_budget_exhausted(started_at, time_budget_seconds):
            break

        candidate, metadata, failure = _generate_variant(
            record,
            source_units=source_units,
            content_profile=content_profile,
            client=client,
            client_results=client_results,
            tone=tone,
            model=model,
            prompt_version=prompt_version,
            variant=variant,
            variant_index=variant_index,
            started_at=started_at,
            time_budget_seconds=time_budget_seconds,
        )
        plans[variant] = metadata.get("plan", {})
        section_batches.extend(_dict_list(metadata.get("section_batches")))
        if failure:
            failed_variants.append(failure)
        if candidate is not None:
            candidates.append(candidate)
        _checkpoint_longform_record(
            checkpoint,
            record,
            candidates,
            selected_variants=selected,
            failed_variants=failed_variants,
            skipped_variants=skipped_variants,
            repair_summaries=repair_summaries,
            client_results=client_results,
            model=model,
            prompt_version=prompt_version,
            tone=tone,
            source_digest=source_digest,
            content_profile=content_profile,
            repair=repair,
            max_repair_attempts=max_repair_attempts,
            resume=resume,
            candidate_limit=candidate_limit,
            time_budget_seconds=time_budget_seconds,
            time_budget_exhausted=time_budget_exhausted(started_at, time_budget_seconds),
            plans=plans,
            section_batches=section_batches,
        )

    if repair:
        candidates, repair_summaries = repair_longform_candidates(
            record,
            candidates,
            source_units=source_units,
            content_profile=content_profile,
            client=client,
            client_results=client_results,
            tone=tone,
            model=model,
            prompt_version=prompt_version,
            max_repair_attempts=max_repair_attempts,
            started_at=started_at,
            time_budget_seconds=time_budget_seconds,
        )

    partial = generation_is_partial(
        candidates,
        selected_variants=selected,
        failed_variants=failed_variants,
        time_budget_exhausted=time_budget_exhausted(started_at, time_budget_seconds),
    )
    updated = _record_with_longform_metadata(
        record,
        candidates,
        selected_variants=selected,
        failed_variants=failed_variants,
        skipped_variants=skipped_variants,
        repair_summaries=repair_summaries,
        client_results=client_results,
        model=model,
        prompt_version=prompt_version,
        tone=tone,
        source_digest=source_digest,
        content_profile=content_profile,
        repair=repair,
        max_repair_attempts=max_repair_attempts,
        resume=resume,
        candidate_limit=candidate_limit,
        time_budget_seconds=time_budget_seconds,
        time_budget_exhausted=time_budget_exhausted(started_at, time_budget_seconds),
        partial=partial,
        plans=plans,
        section_batches=section_batches,
        repair_targets=repair_summaries,
    )
    return LongformNoteGenerationResult(
        record=updated,
        client_results=client_results,
        dry_run=False,
        repair_requested=repair,
        max_repair_attempts=max_repair_attempts if repair else 0,
    )


def _generate_variant(
    record: LectureRecord,
    *,
    source_units: list[NoteSourceUnit],
    content_profile: NoteContentProfile,
    client: OpenAIClient,
    client_results: list[OpenAIClientResult],
    tone: str,
    model: str,
    prompt_version: str,
    variant: str,
    variant_index: int,
    started_at: float,
    time_budget_seconds: float | None,
) -> tuple[dict[str, object] | None, dict[str, object], dict[str, object] | None]:
    batches: list[dict[str, object]] = []
    metadata: dict[str, object] = {"variant": variant, "section_batches": batches}
    plan_result = _send_longform_request(
        client,
        build_longform_plan_request(
            record,
            source_units=source_units,
            content_profile=content_profile,
            tone=tone,
            model=model,
            prompt_version=prompt_version,
            variant=variant,
        ),
        client_results=client_results,
        started_at=started_at,
        time_budget_seconds=time_budget_seconds,
    )
    if not plan_result.succeeded:
        return None, metadata, _failed_variant(variant, plan_result)
    plan = parse_longform_plan(
        plan_result.body,
        source_units=source_units,
        content_profile=content_profile,
    )
    metadata["plan"] = plan

    topic_sections: list[dict[str, object]] = []
    for batch_index, batch in enumerate(
        topic_batches(_dict_list(plan.get("topics")), batch_size=LONGFORM_TOPIC_BATCH_SIZE),
        start=1,
    ):
        if time_budget_exhausted(started_at, time_budget_seconds):
            break
        section_result = _send_longform_request(
            client,
            build_longform_section_request(
                record,
                source_units=source_units,
                content_profile=content_profile,
                tone=tone,
                model=model,
                prompt_version=prompt_version,
                variant=variant,
                plan=plan,
                topics=batch,
                batch_index=batch_index,
            ),
            client_results=client_results,
            started_at=started_at,
            time_budget_seconds=time_budget_seconds,
        )
        batches.append(
            {
                "variant": variant,
                "batch_index": batch_index,
                "topic_count": len(batch),
                "status": section_result.metadata.status,
            }
        )
        if not section_result.succeeded:
            return None, metadata, _failed_variant(variant, section_result)
        topic_sections.extend(parse_longform_sections(section_result.body))

    if not topic_sections:
        return None, metadata, {
            "variant": variant,
            "code": "longform_sections_empty",
            "message": "Longform section generation produced no topic sections.",
            "retryable": False,
        }

    assembly_result = _send_longform_request(
        client,
        build_longform_assembly_request(
            record,
            source_units=source_units,
            content_profile=content_profile,
            tone=tone,
            model=model,
            prompt_version=prompt_version,
            variant=variant,
            plan=plan,
            topic_sections=topic_sections,
        ),
        client_results=client_results,
        started_at=started_at,
        time_budget_seconds=time_budget_seconds,
    )
    if not assembly_result.succeeded:
        return None, metadata, _failed_variant(variant, assembly_result)

    candidate = parse_assembly_or_fallback(
        assembly_result,
        record=record,
        source_units=source_units,
        content_profile=content_profile,
        tone=tone,
        model=model,
        prompt_version=prompt_version,
        variant=variant,
        variant_index=variant_index,
        plan=plan,
        topic_sections=topic_sections,
    )
    return candidate, metadata, None


def _checkpoint_longform_record(
    checkpoint: Callable[[LectureRecord], None] | None,
    record: LectureRecord,
    candidates: list[dict[str, object]],
    **metadata,
) -> None:
    checkpoint_record(
        checkpoint,
        _record_with_longform_metadata(
            record,
            candidates,
            partial=True,
            repair_targets=metadata.get("repair_summaries", []),
            **metadata,
        ),
    )


def _send_longform_request(
    client: OpenAIClient,
    request: OpenAIRequest,
    *,
    client_results: list[OpenAIClientResult],
    started_at: float,
    time_budget_seconds: float | None,
) -> OpenAIClientResult:
    result: OpenAIClientResult | None = None
    for attempt in range(1, LONGFORM_RETRY_ATTEMPTS + 1):
        result = client.send(request)
        client_results.append(result)
        if result.succeeded or not result.metadata.retryable:
            return result
        if attempt >= LONGFORM_RETRY_ATTEMPTS:
            return result
        if time_budget_exhausted(started_at, time_budget_seconds):
            return result
        time.sleep(min(5.0, 2.0 * attempt))
    if result is None:
        raise NoteGenerationError(
            ErrorDetail(
                code="longform_request_not_sent",
                message="Longform OpenAI request was not sent.",
                stage=NOTE_STAGE,
                retryable=True,
            )
        )
    return result


def _record_with_longform_metadata(
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
    content_profile: NoteContentProfile,
    repair: bool,
    max_repair_attempts: int,
    resume: bool,
    candidate_limit: int | None,
    time_budget_seconds: float | None,
    time_budget_exhausted: bool,
    partial: bool,
    plans: dict[str, object],
    section_batches: list[dict[str, object]],
    repair_targets: list[dict[str, object]],
) -> LectureRecord:
    updated = record_with_note_candidates(
        record,
        candidates,
        selected_variants=selected_variants,
        failed_variants=failed_variants,
        skipped_variants=skipped_variants,
        repair_summaries=repair_summaries,
        client_results=client_results,
        model=model,
        prompt_version=prompt_version,
        tone=tone,
        source_digest=source_digest,
        content_profile=content_profile,
        repair=repair,
        max_repair_attempts=max_repair_attempts,
        resume=resume,
        candidate_limit=candidate_limit,
        time_budget_seconds=time_budget_seconds,
        time_budget_exhausted=time_budget_exhausted,
        partial=partial,
    )
    return replace(
        updated,
        note_metadata={
            **updated.note_metadata,
            "longform_generation": {
                "enabled": True,
                "prompt_version": prompt_version,
                "plan": plans,
                "section_batches": section_batches,
                "repair_targets": repair_targets,
                "auto_approval_candidate_id": first_auto_approvable_candidate_id(
                    candidates
                ),
            },
        },
    )


def _failed_variant(
    variant: str,
    result: OpenAIClientResult,
) -> dict[str, object]:
    issue = result.to_processing_issue(stage=NOTE_STAGE)
    return {
        "variant": variant,
        "code": issue.code if issue else "openai_longform_note_generation_failed",
        "message": issue.message if issue else "OpenAI longform note generation failed.",
        "retryable": issue.retryable if issue else False,
        "openai_call": result.metadata.to_dict(),
    }


def _dict_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]

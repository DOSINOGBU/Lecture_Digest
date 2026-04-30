from __future__ import annotations

from dataclasses import dataclass, replace

from lecturedigest.errors import ErrorDetail, NoteGenerationError
from lecturedigest.models import LectureRecord
from lecturedigest.note_markdown import NoteSourceUnit, source_hash, source_units
from lecturedigest.note_profile import build_content_profile
from lecturedigest.openai_client import OpenAIClient, format_dry_run_result
from lecturedigest.openai_note_parse import parse_note_response
from lecturedigest.openai_note_prompt import (
    DEFAULT_OPENAI_NOTE_MODEL,
    DEFAULT_OPENAI_NOTE_PROMPT_VERSION,
    NOTE_STAGE,
    NOTE_VARIANTS,
    OPENAI_NOTE_ENDPOINT,
    OPENAI_NOTE_USE_CASE,
    build_note_request as _build_note_request,
)
from lecturedigest.openai_note_repair import build_note_repair_request
from lecturedigest.openai_types import OpenAIClientResult


@dataclass(frozen=True)
class OpenAINoteGenerationResult:
    record: LectureRecord
    client_results: list[OpenAIClientResult]
    dry_run: bool = False
    repair_requested: bool = False
    max_repair_attempts: int = 0

    @property
    def client_result(self) -> OpenAIClientResult:
        return self.client_results[-1]


def generate_note_candidates_with_openai(
    record: LectureRecord,
    *,
    client: OpenAIClient | None = None,
    tone: str,
    model: str = DEFAULT_OPENAI_NOTE_MODEL,
    prompt_version: str = DEFAULT_OPENAI_NOTE_PROMPT_VERSION,
    dry_run: bool = False,
    repair: bool = False,
    max_repair_attempts: int = 1,
) -> OpenAINoteGenerationResult:
    units = _required_source_units(record)
    content_profile = build_content_profile(units, chunks=record.chunks)
    openai_client = client or OpenAIClient()
    client_results: list[OpenAIClientResult] = []
    candidates: list[dict[str, object]] = []
    for variant_index, variant in enumerate(NOTE_VARIANTS, start=1):
        request = build_note_request(
            record,
            source_units=units,
            tone=tone,
            model=model,
            prompt_version=prompt_version,
            variant=variant,
        )
        result = openai_client.send(request, dry_run=dry_run)
        client_results.append(result)
        if dry_run:
            continue
        if not result.succeeded:
            issue = result.to_processing_issue(stage=NOTE_STAGE)
            raise NoteGenerationError(
                ErrorDetail(
                    code=issue.code if issue else "openai_note_generation_failed",
                    message=issue.message if issue else "OpenAI note generation failed.",
                    stage=NOTE_STAGE,
                    retryable=issue.retryable if issue else False,
                )
            )
        candidates.extend(
            parse_note_response(
                result.body,
                record=record,
                source_units=units,
                tone=tone,
                model=model,
                prompt_version=prompt_version,
                client_result=result,
                content_profile=content_profile,
                expected_count=1,
                variant_index_start=variant_index,
            )
        )
    if dry_run:
        return OpenAINoteGenerationResult(
            record=record,
            client_results=client_results,
            dry_run=True,
            repair_requested=repair,
            max_repair_attempts=max_repair_attempts if repair else 0,
        )

    repaired_candidates, repair_summaries = _repair_flagged_candidates(
        record,
        candidates,
        source_units=units,
        content_profile=content_profile,
        client=openai_client,
        client_results=client_results,
        tone=tone,
        model=model,
        prompt_version=prompt_version,
        repair=repair,
        max_repair_attempts=max_repair_attempts,
    )

    approved_note = _stale_approved_note(
        record.approved_note,
        model=model,
        prompt_version=prompt_version,
    )
    updated = replace(
        record,
        status="note_candidates_ready",
        stage=NOTE_STAGE,
        note_candidates=repaired_candidates,
        approved_note=approved_note,
        note_metadata={
            "provider": "openai_responses",
            "model": model,
            "prompt_version": prompt_version,
            "tone": tone,
            "candidate_count": len(repaired_candidates),
            "source_hash": source_hash(units),
            "content_profile": content_profile.to_dict(),
            "approved_note_stale": approved_note.get("status") == "stale",
            "repair_requested": repair,
            "max_repair_attempts": max_repair_attempts if repair else 0,
            "repair_attempted_count": len(repair_summaries),
            "repair_success_count": sum(
                1 for item in repair_summaries if item.get("applied")
            ),
            "repair_summaries": repair_summaries,
            "last_note_call": client_results[-1].metadata.to_dict(),
            "last_note_calls": [result.metadata.to_dict() for result in client_results],
        },
    )
    return OpenAINoteGenerationResult(
        record=updated,
        client_results=client_results,
        dry_run=False,
        repair_requested=repair,
        max_repair_attempts=max_repair_attempts if repair else 0,
    )


def build_note_request(
    record: LectureRecord,
    *,
    source_units: list[NoteSourceUnit] | None = None,
    tone: str,
    model: str = DEFAULT_OPENAI_NOTE_MODEL,
    prompt_version: str = DEFAULT_OPENAI_NOTE_PROMPT_VERSION,
    variant: str | None = None,
):
    return _build_note_request(
        record,
        source_units=source_units or _required_source_units(record),
        tone=tone,
        model=model,
        prompt_version=prompt_version,
        variant=variant,
    )


def format_openai_note_dry_run(result: OpenAINoteGenerationResult) -> str:
    total_bytes = sum(item.metadata.input_size_bytes for item in result.client_results)
    return "\n".join(
        [
            *[format_dry_run_result(item) for item in result.client_results],
            (
                "[LectureNotes] openai dry-run "
                f"{{ requests={len(result.client_results)}; "
                f"totalInputSizeBytes={total_bytes}; "
                f"repairRequested={result.repair_requested}; "
                f"maxRepairAttempts={result.max_repair_attempts}; "
                f"repairDryRunDeferred={result.repair_requested}; "
                "externalDataBoundary=lecture transcript chunks to OpenAI "
                "Responses API; willUpload=false; willSave=false }"
            ),
        ]
    )


def _repair_flagged_candidates(
    record: LectureRecord,
    candidates: list[dict[str, object]],
    *,
    source_units: list[NoteSourceUnit],
    content_profile,
    client: OpenAIClient,
    client_results: list[OpenAIClientResult],
    tone: str,
    model: str,
    prompt_version: str,
    repair: bool,
    max_repair_attempts: int,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    if not repair or max_repair_attempts <= 0:
        return candidates, []

    repaired_candidates = []
    repair_summaries = []
    for variant_index, candidate in enumerate(candidates, start=1):
        if _validation_status(candidate) != "flagged":
            repaired_candidates.append(candidate)
            continue

        current = candidate
        summary: dict[str, object] = {}
        for attempt in range(1, max_repair_attempts + 1):
            request = build_note_repair_request(
                record,
                source_units=source_units,
                candidate=current,
                tone=tone,
                model=model,
                prompt_version=prompt_version,
                variant=str(current.get("variant") or NOTE_VARIANTS[variant_index - 1]),
                content_profile=content_profile,
            )
            result = client.send(request, dry_run=False)
            client_results.append(result)
            summary = _repair_summary(
                current,
                result=result,
                attempt=attempt,
                applied=False,
            )
            if not result.succeeded:
                if result.metadata.retryable and attempt < max_repair_attempts:
                    continue
                current["repair_metadata"] = summary
                break

            repaired = parse_note_response(
                result.body,
                record=record,
                source_units=source_units,
                tone=tone,
                model=model,
                prompt_version=prompt_version,
                client_result=result,
                content_profile=content_profile,
                expected_count=1,
                variant_index_start=variant_index,
            )[0]
            applied = _is_repair_improvement(current, repaired)
            summary = _repair_summary(
                current,
                repaired=repaired,
                result=result,
                attempt=attempt,
                applied=applied,
            )
            if applied:
                repaired["repair_metadata"] = summary
                current = repaired
            else:
                current["repair_metadata"] = summary

            if _validation_status(current) != "flagged":
                break

        repair_summaries.append(summary)
        repaired_candidates.append(current)
    return repaired_candidates, repair_summaries


def _repair_summary(
    original: dict[str, object],
    *,
    result: OpenAIClientResult,
    attempt: int,
    applied: bool,
    repaired: dict[str, object] | None = None,
) -> dict[str, object]:
    repaired_validation = _validation(repaired or original)
    return {
        "candidate_id": original.get("candidate_id"),
        "variant": original.get("variant"),
        "attempt": attempt,
        "applied": applied,
        "initial_status": _validation_status(original),
        "initial_failed_rules": _failed_rules(original),
        "repaired_status": repaired_validation.get("status"),
        "repaired_failed_rules": _string_list(repaired_validation.get("failed_rules")),
        "openai_call": result.metadata.to_dict(),
        "error_code": result.error_code,
    }


def _is_repair_improvement(
    original: dict[str, object],
    repaired: dict[str, object],
) -> bool:
    original_failed = len(_failed_rules(original))
    repaired_failed = len(_failed_rules(repaired))
    if _validation_status(repaired) == "review_required":
        return True
    return repaired_failed < original_failed


def _validation_status(candidate: dict[str, object]) -> str:
    return str(_validation(candidate).get("status") or "unknown")


def _failed_rules(candidate: dict[str, object]) -> list[str]:
    return _string_list(_validation(candidate).get("failed_rules"))


def _validation(candidate: dict[str, object] | None) -> dict[str, object]:
    if not isinstance(candidate, dict):
        return {}
    validation = candidate.get("validation")
    return validation if isinstance(validation, dict) else {}


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]


def _required_source_units(record: LectureRecord) -> list[NoteSourceUnit]:
    units = source_units(record.segments)
    if units:
        return units
    raise NoteGenerationError(
        ErrorDetail(
            code="segments_required",
            message="Input transcript segments are required before OpenAI notes.",
            stage=NOTE_STAGE,
            retryable=False,
        )
    )


def _stale_approved_note(
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


__all__ = [
    "DEFAULT_OPENAI_NOTE_MODEL",
    "DEFAULT_OPENAI_NOTE_PROMPT_VERSION",
    "OPENAI_NOTE_ENDPOINT",
    "OPENAI_NOTE_USE_CASE",
    "OpenAINoteGenerationResult",
    "build_note_request",
    "format_openai_note_dry_run",
    "generate_note_candidates_with_openai",
    "parse_note_response",
]

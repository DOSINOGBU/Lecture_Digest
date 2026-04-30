from __future__ import annotations

from dataclasses import dataclass, replace

from lecturedigest.errors import ErrorDetail, NoteGenerationError
from lecturedigest.models import LectureRecord
from lecturedigest.note_markdown import NoteSourceUnit, source_hash, source_units
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
from lecturedigest.openai_types import OpenAIClientResult


@dataclass(frozen=True)
class OpenAINoteGenerationResult:
    record: LectureRecord
    client_results: list[OpenAIClientResult]
    dry_run: bool = False

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
) -> OpenAINoteGenerationResult:
    units = _required_source_units(record)
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
                expected_count=1,
                variant_index_start=variant_index,
            )
        )
    if dry_run:
        return OpenAINoteGenerationResult(
            record=record,
            client_results=client_results,
            dry_run=True,
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
        note_candidates=candidates,
        approved_note=approved_note,
        note_metadata={
            "provider": "openai_responses",
            "model": model,
            "prompt_version": prompt_version,
            "tone": tone,
            "candidate_count": len(candidates),
            "source_hash": source_hash(units),
            "approved_note_stale": approved_note.get("status") == "stale",
            "last_note_call": client_results[-1].metadata.to_dict(),
            "last_note_calls": [result.metadata.to_dict() for result in client_results],
        },
    )
    return OpenAINoteGenerationResult(
        record=updated,
        client_results=client_results,
        dry_run=False,
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
                "externalDataBoundary=lecture transcript chunks to OpenAI "
                "Responses API; willUpload=false; willSave=false }"
            ),
        ]
    )


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

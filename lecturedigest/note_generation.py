from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from lecturedigest.errors import ErrorDetail, NoteGenerationError, ValidationError
from lecturedigest.models import LectureRecord
from lecturedigest.note_markdown import (
    build_note_candidate,
    source_hash,
    source_units,
)

DEFAULT_NOTE_MODEL = "local-scriptdigest-v1"
DEFAULT_NOTE_PROMPT_VERSION = "markdown-note-v1"
DEFAULT_NOTE_TONE = "formal"
NOTE_CANDIDATE_COUNT = 3
ALLOWED_TONES = {"formal", "casual", "keep_original"}


def generate_note_candidates(
    record: LectureRecord,
    *,
    tone: str = DEFAULT_NOTE_TONE,
    model: str = DEFAULT_NOTE_MODEL,
    prompt_version: str = DEFAULT_NOTE_PROMPT_VERSION,
) -> LectureRecord:
    normalized_tone = _validate_tone(tone)
    normalized_model = _require_text(model, "note_model")
    normalized_prompt = _require_text(prompt_version, "prompt_version")
    units = source_units(record.segments)
    if not units:
        raise NoteGenerationError(
            ErrorDetail(
                code="segments_required",
                message="Input transcript segments are required before notes.",
                stage="note_generation",
                retryable=False,
            )
        )

    candidates = [
        build_note_candidate(
            record=record,
            source_units=units,
            tone=normalized_tone,
            model=normalized_model,
            prompt_version=normalized_prompt,
            variant_index=index,
        )
        for index in range(1, NOTE_CANDIDATE_COUNT + 1)
    ]
    approved_note = _stale_approved_note(
        record.approved_note,
        model=normalized_model,
        prompt_version=normalized_prompt,
    )
    return replace(
        record,
        status="note_candidates_ready",
        stage="note_generation",
        note_candidates=candidates,
        approved_note=approved_note,
        note_metadata={
            "model": normalized_model,
            "prompt_version": normalized_prompt,
            "tone": normalized_tone,
            "candidate_count": len(candidates),
            "source_hash": source_hash(units),
            "approved_note_stale": approved_note.get("status") == "stale",
        },
    )


def approve_note_candidate(
    record: LectureRecord,
    *,
    candidate_id: str,
) -> LectureRecord:
    normalized_id = _require_text(candidate_id, "candidate_id")
    selected = _find_candidate(record.note_candidates, normalized_id)
    approved = {**selected, "status": "approved", "approved_at": _now()}
    candidates = [
        (
            approved
            if str(candidate.get("candidate_id")) == normalized_id
            else {**candidate, "status": "rejected"}
        )
        for candidate in record.note_candidates
    ]
    sections = [
        section
        for section in _as_dict_list(approved.get("sections", []))
        if section.get("segment_ids")
    ]
    return replace(
        record,
        status="note_approved",
        stage="note_approval",
        note_candidates=candidates,
        approved_note=approved,
        note_sections=sections,
        note_metadata={
            **record.note_metadata,
            "approved_candidate_id": normalized_id,
            "approved_at": approved["approved_at"],
        },
    )


def reject_note_candidate(
    record: LectureRecord,
    *,
    candidate_id: str,
    reason: str | None = None,
) -> LectureRecord:
    normalized_id = _require_text(candidate_id, "candidate_id")
    _find_candidate(record.note_candidates, normalized_id)
    rejected_at = _now()
    candidates = []
    for candidate in record.note_candidates:
        if str(candidate.get("candidate_id")) != normalized_id:
            candidates.append(candidate)
            continue
        rejected = {
            **candidate,
            "status": "rejected",
            "rejected_at": rejected_at,
        }
        if reason and reason.strip():
            rejected["rejection_reason"] = reason.strip()
        candidates.append(rejected)
    return replace(
        record,
        status="note_candidates_ready",
        stage="note_review",
        note_candidates=candidates,
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


def _find_candidate(
    candidates: list[dict[str, object]],
    candidate_id: str,
) -> dict[str, object]:
    if not candidates:
        raise NoteGenerationError(
            ErrorDetail(
                code="note_candidates_required",
                message="Generate note candidates before approval.",
                stage="note_approval",
                retryable=False,
            )
        )
    for candidate in candidates:
        if str(candidate.get("candidate_id")) == candidate_id:
            return candidate
    raise ValidationError(
        ErrorDetail(
            code="note_candidate_not_found",
            message=f"Note candidate not found: {candidate_id}",
            stage="note_approval",
            retryable=False,
        )
    )


def _validate_tone(tone: str) -> str:
    normalized = _require_text(tone, "tone")
    if normalized not in ALLOWED_TONES:
        allowed = ", ".join(sorted(ALLOWED_TONES))
        raise ValidationError(
            ErrorDetail(
                code="note_tone_invalid",
                message=f"tone must be one of: {allowed}",
                stage="note_generation",
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
                stage="note_generation",
                retryable=False,
            )
        )
    return normalized


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _as_dict_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]

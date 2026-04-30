from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from lecturedigest.errors import CorrectionError, ErrorDetail, ValidationError
from lecturedigest.models import CorrectionLogEntry, LectureRecord, TranscriptSegment


def approve_correction_candidate(
    record: LectureRecord,
    *,
    segment_id: str,
) -> LectureRecord:
    normalized_id = _require_text(segment_id, "segment_id")
    entry = _find_reviewable_entry(record, normalized_id)
    corrected_text = _require_text(entry.corrected_text, "corrected_text")
    updated_segments = [
        _apply_text(segment, corrected_text)
        if segment.segment_id == normalized_id
        else segment
        for segment in record.segments
    ]
    updated_log = [
        _approve_entry(item) if item.segment_id == normalized_id else item
        for item in record.correction_log
    ]
    return replace(
        record,
        status="transcript_finalized",
        stage="correction_review",
        segments=updated_segments,
        correction_log=updated_log,
    )


def reject_correction_candidate(
    record: LectureRecord,
    *,
    segment_id: str,
    reason: str | None = None,
) -> LectureRecord:
    normalized_id = _require_text(segment_id, "segment_id")
    _find_reviewable_entry(record, normalized_id)
    updated_log = [
        _reject_entry(item, reason) if item.segment_id == normalized_id else item
        for item in record.correction_log
    ]
    return replace(
        record,
        status="transcript_finalized",
        stage="correction_review",
        correction_log=updated_log,
    )


def _find_reviewable_entry(
    record: LectureRecord,
    segment_id: str,
) -> CorrectionLogEntry:
    if not record.correction_log:
        raise CorrectionError(
            ErrorDetail(
                code="correction_review_required",
                message="No correction candidates are available for review.",
                stage="correction_review",
                retryable=False,
            )
        )
    for entry in record.correction_log:
        if entry.segment_id == segment_id and entry.status == "review_required":
            return entry
    raise ValidationError(
        ErrorDetail(
            code="correction_candidate_not_found",
            message=f"Reviewable correction candidate not found: {segment_id}",
            stage="correction_review",
            retryable=False,
        )
    )


def _apply_text(segment: TranscriptSegment, corrected_text: str) -> TranscriptSegment:
    return replace(segment, text=corrected_text)


def _approve_entry(entry: CorrectionLogEntry) -> CorrectionLogEntry:
    return replace(
        entry,
        status="applied",
        applied=True,
        provider_metadata={
            **entry.provider_metadata,
            "review_decision": "approved",
            "reviewed_at": _now(),
        },
    )


def _reject_entry(
    entry: CorrectionLogEntry,
    reason: str | None,
) -> CorrectionLogEntry:
    metadata = {
        **entry.provider_metadata,
        "review_decision": "rejected",
        "reviewed_at": _now(),
    }
    if reason and reason.strip():
        metadata["rejection_reason"] = reason.strip()
    return replace(
        entry,
        status="rejected",
        applied=False,
        provider_metadata=metadata,
    )


def _require_text(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValidationError(
            ErrorDetail(
                code=f"{field_name}_required",
                message=f"{field_name} is required.",
                stage="correction_review",
                retryable=False,
            )
        )
    return normalized


def _now() -> str:
    return datetime.now(UTC).isoformat()

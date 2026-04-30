from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from pathlib import Path

from lecturedigest.errors import CorrectionError, ErrorDetail, ValidationError
from lecturedigest.models import (
    CorrectionLogEntry,
    LectureRecord,
    ProcessingIssue,
    TranscriptSegment,
)

SUPPORTED_CORRECTION_RESULT_EXTENSIONS = {".json"}
DEFAULT_CORRECTION_MODEL = "gpt-4o"
DEFAULT_CORRECTION_PROMPT_VERSION = "transcript-correction-v1"
DEFAULT_CORRECTION_CONFIDENCE_THRESHOLD = 0.9

TOKEN_PATTERN = re.compile(r"`[^`]+`|[A-Za-z0-9_./\\()-]+")


@dataclass(frozen=True)
class CorrectionCandidate:
    segment_id: str
    corrected_text: str
    confidence: float | None
    reason: str | None
    status: str
    provider_metadata: dict[str, object]
    original_error: str | None
    retryable: bool


def finalize_transcript(
    record: LectureRecord,
    *,
    correction_result_path: str | Path,
    confidence_threshold: float = DEFAULT_CORRECTION_CONFIDENCE_THRESHOLD,
) -> LectureRecord:
    _validate_confidence_threshold(confidence_threshold)
    if not record.segments:
        raise CorrectionError(
            ErrorDetail(
                code="segments_required",
                message="Transcript segments are required before correction.",
                stage="correction",
                retryable=False,
            )
        )

    payload = _read_correction_payload(correction_result_path)
    provider_metadata = _provider_metadata(payload)
    candidates = _candidates_from_payload(payload, provider_metadata)
    if not candidates:
        raise CorrectionError(
            ErrorDetail(
                code="correction_result_empty",
                message="Correction result did not contain segment corrections.",
                stage="correction",
                retryable=False,
            )
        )

    segments, log_entries, issues = _apply_candidates(
        record=record,
        candidates=candidates,
        confidence_threshold=confidence_threshold,
    )
    return replace(
        record,
        status="transcript_finalized",
        stage="correction",
        segments=segments,
        chunks=[],
        issues=[*record.issues, *issues],
        correction_log=[*record.correction_log, *log_entries],
        correction_metadata={
            **provider_metadata,
            "confidence_threshold": confidence_threshold,
        },
    )


def _validate_confidence_threshold(confidence_threshold: float) -> None:
    if confidence_threshold < 0 or confidence_threshold > 1:
        raise ValidationError(
            ErrorDetail(
                code="correction_confidence_threshold_invalid",
                message="Correction confidence threshold must be between 0 and 1.",
                stage="correction",
                retryable=False,
            )
        )


def _read_correction_payload(path_value: str | Path) -> dict[str, object]:
    path = Path(path_value).expanduser().resolve()
    if not path.exists() or not path.is_file():
        raise ValidationError(
            ErrorDetail(
                code="correction_result_not_found",
                message=f"Correction result file not found: {path}",
                stage="correction",
                retryable=False,
            )
        )
    if path.suffix.lower() not in SUPPORTED_CORRECTION_RESULT_EXTENSIONS:
        raise ValidationError(
            ErrorDetail(
                code="correction_result_unsupported_extension",
                message="Correction result file must be a .json file.",
                stage="correction",
                retryable=False,
            )
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValidationError(
            ErrorDetail(
                code="correction_result_invalid_json",
                message=f"Correction result JSON could not be parsed: {exc.msg}",
                stage="correction",
                retryable=False,
            )
        ) from exc
    if not isinstance(payload, dict):
        raise ValidationError(
            ErrorDetail(
                code="correction_result_invalid_schema",
                message="Correction result JSON must be an object.",
                stage="correction",
                retryable=False,
            )
        )
    return payload


def _provider_metadata(payload: dict[str, object]) -> dict[str, object]:
    metadata = payload.get("provider_metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}
    result = {str(key): value for key, value in metadata.items()}
    result.setdefault("provider", "openai_responses")
    result.setdefault("model", DEFAULT_CORRECTION_MODEL)
    result.setdefault("prompt_version", DEFAULT_CORRECTION_PROMPT_VERSION)
    result.setdefault("status", "succeeded")
    return result


def _candidates_from_payload(
    payload: dict[str, object],
    provider_metadata: dict[str, object],
) -> list[CorrectionCandidate]:
    raw_corrections = payload.get("corrections", [])
    if not isinstance(raw_corrections, list):
        raise ValidationError(
            ErrorDetail(
                code="correction_items_invalid",
                message="Correction result `corrections` must be a list.",
                stage="correction",
                retryable=False,
            )
        )

    candidates: list[CorrectionCandidate] = []
    for item in raw_corrections:
        if not isinstance(item, dict):
            continue
        candidates.append(_candidate_from_item(item, provider_metadata))
    return candidates


def _candidate_from_item(
    item: dict[str, object],
    provider_metadata: dict[str, object],
) -> CorrectionCandidate:
    segment_id = str(item.get("segment_id") or "").strip()
    if not segment_id:
        raise ValidationError(
            ErrorDetail(
                code="correction_segment_id_required",
                message="Correction item `segment_id` is required.",
                stage="correction",
                retryable=False,
            )
        )
    metadata = {**provider_metadata}
    item_metadata = item.get("provider_metadata", {})
    if isinstance(item_metadata, dict):
        metadata.update({str(key): value for key, value in item_metadata.items()})
    return CorrectionCandidate(
        segment_id=segment_id,
        corrected_text=str(item.get("corrected_text") or item.get("text") or ""),
        confidence=_optional_float(item.get("confidence")),
        reason=_optional_string(item.get("reason")),
        status=str(item.get("status") or metadata.get("status") or "succeeded"),
        provider_metadata=metadata,
        original_error=_optional_string(item.get("original_error")),
        retryable=bool(item.get("retryable", False)),
    )


def _apply_candidates(
    *,
    record: LectureRecord,
    candidates: list[CorrectionCandidate],
    confidence_threshold: float,
) -> tuple[list[TranscriptSegment], list[CorrectionLogEntry], list[ProcessingIssue]]:
    candidate_by_id = {candidate.segment_id: candidate for candidate in candidates}
    issues = _unmapped_candidate_issues(record.segments, candidates)
    updated_segments: list[TranscriptSegment] = []
    log_entries: list[CorrectionLogEntry] = []

    for segment in record.segments:
        candidate = candidate_by_id.get(segment.segment_id)
        if candidate is None:
            updated_segments.append(segment)
            continue

        corrected_segment, log_entry, issue = _apply_candidate_to_segment(
            segment=segment,
            candidate=candidate,
            source=record.transcript_source,
            confidence_threshold=confidence_threshold,
        )
        updated_segments.append(corrected_segment)
        log_entries.append(log_entry)
        if issue is not None:
            issues.append(issue)

    return updated_segments, log_entries, issues


def _apply_candidate_to_segment(
    *,
    segment: TranscriptSegment,
    candidate: CorrectionCandidate,
    source: str,
    confidence_threshold: float,
) -> tuple[TranscriptSegment, CorrectionLogEntry, ProcessingIssue | None]:
    protected_terms = _changed_protected_terms(segment.text, candidate.corrected_text)
    status, applied, issue = _candidate_decision(
        candidate=candidate,
        has_protected_term_change=bool(protected_terms),
        confidence_threshold=confidence_threshold,
    )
    corrected_text = candidate.corrected_text.strip()
    next_segment = replace(segment, text=corrected_text) if applied else segment
    log_entry = CorrectionLogEntry(
        segment_id=segment.segment_id,
        start_ts=segment.start_ts,
        end_ts=segment.end_ts,
        original_text=segment.text,
        corrected_text=corrected_text,
        confidence=candidate.confidence,
        reason=candidate.reason,
        applied=applied,
        status=status,
        provider_metadata=candidate.provider_metadata,
        protected_terms=protected_terms,
        original_error=candidate.original_error,
        retryable=candidate.retryable,
        source=source,
    )
    return next_segment, log_entry, issue


def _candidate_decision(
    *,
    candidate: CorrectionCandidate,
    has_protected_term_change: bool,
    confidence_threshold: float,
) -> tuple[str, bool, ProcessingIssue | None]:
    if candidate.status != "succeeded":
        return (
            "failed",
            False,
            _issue(
                "correction_failed",
                candidate.original_error or "Correction provider returned failure.",
                candidate.retryable,
            ),
        )
    if not candidate.corrected_text.strip():
        return (
            "rejected",
            False,
            _issue("correction_empty", "Correction text is empty.", False),
        )
    if candidate.confidence is None or candidate.confidence < confidence_threshold:
        return (
            "review_required",
            False,
            _issue(
                "correction_low_confidence",
                "Correction confidence is below the automatic apply threshold.",
                False,
            ),
        )
    if has_protected_term_change:
        return (
            "review_required",
            False,
            _issue(
                "correction_protected_token_changed",
                "Correction changed protected terms such as code, numbers, or names.",
                False,
            ),
        )
    return "applied", True, None


def _unmapped_candidate_issues(
    segments: list[TranscriptSegment],
    candidates: list[CorrectionCandidate],
) -> list[ProcessingIssue]:
    segment_ids = {segment.segment_id for segment in segments}
    return [
        _issue(
            "correction_unmapped",
            f"Correction item does not map to a transcript segment: {candidate.segment_id}",
            False,
        )
        for candidate in candidates
        if candidate.segment_id not in segment_ids
    ]


def _changed_protected_terms(original_text: str, corrected_text: str) -> list[str]:
    original_terms = _protected_terms(original_text)
    corrected_terms = _protected_terms(corrected_text)
    return sorted(term for term in original_terms if term not in corrected_terms)


def _protected_terms(text: str) -> set[str]:
    terms: set[str] = set()
    for match in TOKEN_PATTERN.finditer(text):
        token = match.group(0).strip("`.,:;!?")
        if _is_protected_token(token):
            terms.add(token)
    return terms


def _is_protected_token(token: str) -> bool:
    if not token:
        return False
    if any(character.isdigit() for character in token):
        return True
    if any(character in token for character in ("_", "/", "\\", ".")):
        return True
    if token.endswith("()"):
        return True
    return any(character.isupper() for character in token)


def _issue(code: str, message: str, retryable: bool) -> ProcessingIssue:
    return ProcessingIssue(
        code=code,
        message=message,
        stage="correction",
        retryable=retryable,
    )


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

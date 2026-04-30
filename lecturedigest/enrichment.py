from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from lecturedigest.errors import EnrichmentError, ErrorDetail, ValidationError
from lecturedigest.models import LectureRecord, ProcessingIssue, SlideOcrResult
from lecturedigest.timecode import normalize_timestamp, timestamp_to_seconds

DEFAULT_FRAME_SAMPLE_INTERVAL_SECONDS = 5
DEFAULT_SLIDE_CHANGE_THRESHOLD = 0.35
MIN_ORIGINAL_FRAME_WIDTH = 1920
MIN_ORIGINAL_FRAME_HEIGHT = 1080


def apply_ocr_enrichment(
    record: LectureRecord,
    *,
    ocr_result_path: str | Path,
    sample_interval_seconds: int = DEFAULT_FRAME_SAMPLE_INTERVAL_SECONDS,
    change_threshold: float = DEFAULT_SLIDE_CHANGE_THRESHOLD,
) -> LectureRecord:
    validate_enrichment_settings(sample_interval_seconds, change_threshold)
    if not record.segments:
        raise EnrichmentError(
            ErrorDetail(
                code="segments_required",
                message="Transcript segments are required before OCR enrichment.",
                stage="enrichment",
                retryable=False,
            )
        )

    payload = _read_ocr_payload(ocr_result_path)
    frames = _frames_from_payload(payload)
    provider_metadata = _metadata_from_payload(payload)
    slides, issues = _slides_from_frames(
        frames=frames,
        provider_metadata=provider_metadata,
        change_threshold=change_threshold,
    )
    if not slides:
        issues.append(_issue("ocr_empty", "No slide OCR candidates were found."))

    linked_segments = _link_slides_to_segments(record, slides)
    enriched_count = sum(1 for segment in linked_segments if segment.ocr_text)
    if slides and enriched_count == 0:
        issues.append(
            _issue(
                "ocr_unmapped",
                "Slide OCR candidates did not overlap transcript segments.",
            )
        )

    status = "ocr_enriched" if enriched_count else record.status
    return replace(
        record,
        status=status,
        stage="enrichment",
        segments=linked_segments,
        slides=slides,
        chunks=[],
        issues=[*record.issues, *issues],
    )


def validate_enrichment_settings(
    sample_interval_seconds: int,
    change_threshold: float,
) -> None:
    if sample_interval_seconds <= 0:
        raise ValidationError(
            ErrorDetail(
                code="frame_sample_interval_invalid",
                message="Frame sample interval must be at least 1 second.",
                stage="enrichment",
                retryable=False,
            )
        )
    if change_threshold < 0:
        raise ValidationError(
            ErrorDetail(
                code="slide_change_threshold_invalid",
                message="Slide change threshold must be 0 or greater.",
                stage="enrichment",
                retryable=False,
            )
        )


def _read_ocr_payload(path_value: str | Path) -> dict[str, object]:
    path = Path(path_value).expanduser().resolve()
    if not path.exists() or not path.is_file():
        raise ValidationError(
            ErrorDetail(
                code="ocr_result_not_found",
                message=f"OCR result file not found: {path}",
                stage="enrichment",
                retryable=False,
            )
        )
    if path.suffix.lower() != ".json":
        raise ValidationError(
            ErrorDetail(
                code="ocr_result_unsupported_extension",
                message="OCR result file must be a .json file.",
                stage="enrichment",
                retryable=False,
            )
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValidationError(
            ErrorDetail(
                code="ocr_result_invalid_json",
                message=f"OCR result JSON could not be parsed: {exc.msg}",
                stage="enrichment",
                retryable=False,
            )
        ) from exc
    if not isinstance(payload, dict):
        raise ValidationError(
            ErrorDetail(
                code="ocr_result_invalid_schema",
                message="OCR result JSON must be an object.",
                stage="enrichment",
                retryable=False,
            )
        )
    return payload


def _frames_from_payload(payload: dict[str, object]) -> list[dict[str, object]]:
    value = payload.get("frames", [])
    if not isinstance(value, list):
        raise ValidationError(
            ErrorDetail(
                code="ocr_frames_invalid",
                message="OCR result `frames` must be a list.",
                stage="enrichment",
                retryable=False,
            )
        )
    return [item for item in value if isinstance(item, dict)]


def _metadata_from_payload(payload: dict[str, object]) -> dict[str, object]:
    metadata = payload.get("provider_metadata", {})
    if not isinstance(metadata, dict):
        return {}
    return {str(key): value for key, value in metadata.items()}


def _slides_from_frames(
    *,
    frames: list[dict[str, object]],
    provider_metadata: dict[str, object],
    change_threshold: float,
) -> tuple[list[SlideOcrResult], list[ProcessingIssue]]:
    slides: list[SlideOcrResult] = []
    issues: list[ProcessingIssue] = []
    for frame in sorted(frames, key=_frame_sort_key):
        if not _is_slide_candidate(frame, slides, change_threshold):
            continue
        slide = _slide_from_frame(
            frame=frame,
            index=len(slides) + 1,
            provider_metadata=provider_metadata,
        )
        slides.append(slide)
        issues.extend(_frame_issues(slide))
    return slides, issues


def _is_slide_candidate(
    frame: dict[str, object],
    slides: list[SlideOcrResult],
    change_threshold: float,
) -> bool:
    if not slides:
        return True
    change_score = _optional_float(frame.get("change_score"))
    return change_score is not None and change_score >= change_threshold


def _slide_from_frame(
    *,
    frame: dict[str, object],
    index: int,
    provider_metadata: dict[str, object],
) -> SlideOcrResult:
    source_frame_ts = _required_timestamp(frame, "source_frame_ts")
    frame_metadata = frame.get("provider_metadata", {})
    metadata = {**provider_metadata}
    if isinstance(frame_metadata, dict):
        metadata.update({str(key): value for key, value in frame_metadata.items()})
    return SlideOcrResult(
        slide_id=str(frame.get("slide_id") or f"slide-{index:06d}"),
        source_frame_ts=source_frame_ts,
        raw_ocr_text=str(frame.get("raw_ocr_text") or ""),
        refined_ocr_text=str(frame.get("refined_ocr_text") or ""),
        confidence=_optional_float(frame.get("confidence")),
        provider_metadata=metadata,
        frame_width=_optional_int(frame.get("frame_width")),
        frame_height=_optional_int(frame.get("frame_height")),
        change_score=_optional_float(frame.get("change_score")),
        status=str(frame.get("status") or metadata.get("status") or "succeeded"),
    )


def _link_slides_to_segments(
    record: LectureRecord,
    slides: list[SlideOcrResult],
):
    usable_slides = list(_usable_slides(slides))
    if not usable_slides:
        return record.segments

    intervals = []
    for index, slide in enumerate(usable_slides):
        start = timestamp_to_seconds(slide.source_frame_ts)
        end = (
            timestamp_to_seconds(usable_slides[index + 1].source_frame_ts)
            if index + 1 < len(usable_slides)
            else float("inf")
        )
        intervals.append((start, end, slide))

    linked = []
    for segment in record.segments:
        segment_start = timestamp_to_seconds(segment.start_ts)
        segment_end = timestamp_to_seconds(segment.end_ts)
        matched = _matching_slide(segment_start, segment_end, intervals)
        if matched is None:
            linked.append(segment)
            continue
        linked.append(
            replace(
                segment,
                ocr_text=matched.refined_ocr_text,
                slide_id=matched.slide_id,
                source_frame_ts=matched.source_frame_ts,
            )
        )
    return linked


def _matching_slide(
    segment_start: float,
    segment_end: float,
    intervals: list[tuple[float, float, SlideOcrResult]],
) -> SlideOcrResult | None:
    for start, end, slide in intervals:
        if segment_end > start and segment_start < end:
            return slide
    return None


def _usable_slides(slides: list[SlideOcrResult]):
    for slide in slides:
        if slide.status != "succeeded":
            continue
        if not slide.refined_ocr_text.strip():
            continue
        yield slide


def _frame_issues(slide: SlideOcrResult) -> list[ProcessingIssue]:
    issues: list[ProcessingIssue] = []
    if slide.status != "succeeded":
        issues.append(_issue("ocr_failed", f"OCR failed for {slide.slide_id}."))
    if not slide.raw_ocr_text and slide.status == "succeeded":
        issues.append(_issue("ocr_raw_empty", f"Raw OCR is empty for {slide.slide_id}."))
    if not slide.refined_ocr_text and slide.status == "succeeded":
        issues.append(
            _issue("ocr_refined_empty", f"Refined OCR is empty for {slide.slide_id}.")
        )
    if (
        slide.frame_width is not None
        and slide.frame_height is not None
        and (
            slide.frame_width < MIN_ORIGINAL_FRAME_WIDTH
            or slide.frame_height < MIN_ORIGINAL_FRAME_HEIGHT
        )
    ):
        issues.append(
            _issue(
                "ocr_frame_below_original_resolution",
                f"OCR frame is below 1080p for {slide.slide_id}.",
            )
        )
    return issues


def _frame_sort_key(frame: dict[str, object]) -> float:
    return timestamp_to_seconds(_required_timestamp(frame, "source_frame_ts"))


def _required_timestamp(frame: dict[str, object], field_name: str) -> str:
    value = frame.get(field_name)
    if value is None:
        raise ValidationError(
            ErrorDetail(
                code=f"{field_name}_required",
                message=f"OCR frame `{field_name}` is required.",
                stage="enrichment",
                retryable=False,
            )
        )
    try:
        return normalize_timestamp(str(value))
    except ValueError as exc:
        raise ValidationError(
            ErrorDetail(
                code=f"{field_name}_invalid",
                message=f"OCR frame timestamp is invalid: {value}",
                stage="enrichment",
                retryable=False,
            )
        ) from exc


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _issue(code: str, message: str) -> ProcessingIssue:
    return ProcessingIssue(
        code=code,
        message=message,
        stage="enrichment",
        retryable=False,
    )

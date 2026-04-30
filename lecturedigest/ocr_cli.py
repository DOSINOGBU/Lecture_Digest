from __future__ import annotations

import argparse
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from lecturedigest.enrichment import apply_ocr_enrichment_payload
from lecturedigest.errors import EnrichmentError, ErrorDetail, ValidationError
from lecturedigest.frame_extraction import (
    DEFAULT_FRAME_EXTRACTION_INTERVAL_SECONDS,
    DEFAULT_SCENE_CHANGE_THRESHOLD,
    FRAME_METHOD_SCENE,
    SUPPORTED_FRAME_METHODS,
    FrameExtractionResult,
    extract_frame_candidates,
    plan_frame_candidates_for_dry_run,
)
from lecturedigest.media_preflight import CommandRunner, MediaToolPaths
from lecturedigest.models import LectureRecord
from lecturedigest.openai_client import OpenAIClient
from lecturedigest.storage import JsonLectureRepository
from lecturedigest.vision_ocr import (
    DEFAULT_VISION_DETAIL,
    DEFAULT_VISION_OCR_MODEL,
    DEFAULT_VISION_OCR_PROMPT_VERSION,
    VisionOcrRunResult,
    run_vision_ocr_on_frames,
)


@dataclass(frozen=True)
class OpenAIOcrEnrichmentResult:
    record: LectureRecord
    extraction_result: FrameExtractionResult
    vision_result: VisionOcrRunResult


def add_ocr_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("ocr")
    parser.add_argument("--lecture-id", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--method",
        default=FRAME_METHOD_SCENE,
        choices=sorted(SUPPORTED_FRAME_METHODS),
    )
    parser.add_argument(
        "--sample-interval-seconds",
        type=int,
        default=DEFAULT_FRAME_EXTRACTION_INTERVAL_SECONDS,
    )
    parser.add_argument(
        "--scene-threshold",
        type=float,
        default=DEFAULT_SCENE_CHANGE_THRESHOLD,
    )
    parser.add_argument("--detail", default=DEFAULT_VISION_DETAIL)
    parser.add_argument("--model", default=DEFAULT_VISION_OCR_MODEL)
    parser.add_argument(
        "--prompt-version",
        default=DEFAULT_VISION_OCR_PROMPT_VERSION,
    )
    parser.add_argument("--no-fallback", action="store_true")


def ocr_command(
    args: argparse.Namespace,
    repository: JsonLectureRepository,
) -> int:
    lectures = repository.list_lectures()
    if not lectures:
        print("No lectures registered yet. Add one with `register`.")
        return 0

    print(
        "[LectureEnrichment] ocr start "
        f"{{ lectureId={args.lecture_id}; dryRun={args.dry_run}; "
        f"method={args.method}; model={args.model}; detail={args.detail} }}"
    )
    record = repository.get_lecture(args.lecture_id)
    if record is None:
        raise ValidationError(
            ErrorDetail(
                code="lecture_not_found",
                message=f"Lecture was not found: {args.lecture_id}",
                stage="enrichment",
                retryable=False,
            )
        )
    _require_segments(record)

    if args.dry_run:
        dry_run_result = plan_frame_candidates_for_dry_run(
            record.source_path,
            method=args.method,
            sample_interval_seconds=args.sample_interval_seconds,
            scene_threshold=args.scene_threshold,
        )
        print(
            format_ocr_dry_run(
                record,
                dry_run_result,
                model=args.model,
                detail=args.detail,
            )
        )
        return 0

    result = enrich_lecture_with_openai_ocr(
        record,
        method=args.method,
        sample_interval_seconds=args.sample_interval_seconds,
        scene_threshold=args.scene_threshold,
        fallback_to_interval=not args.no_fallback,
        model=args.model,
        prompt_version=args.prompt_version,
        detail=args.detail,
    )
    repository.save(result.record)
    if result.vision_result.succeeded_frames == 0:
        raise _vision_failed(result.vision_result)

    print(_format_ocr_success(result.record))
    return 0


def enrich_lecture_with_openai_ocr(
    record: LectureRecord,
    *,
    method: str = FRAME_METHOD_SCENE,
    sample_interval_seconds: int = DEFAULT_FRAME_EXTRACTION_INTERVAL_SECONDS,
    scene_threshold: float = DEFAULT_SCENE_CHANGE_THRESHOLD,
    fallback_to_interval: bool = True,
    client: OpenAIClient | None = None,
    model: str = DEFAULT_VISION_OCR_MODEL,
    prompt_version: str = DEFAULT_VISION_OCR_PROMPT_VERSION,
    detail: str = DEFAULT_VISION_DETAIL,
    tools: MediaToolPaths | None = None,
    runner: CommandRunner = subprocess.run,
    temp_root: str | Path | None = None,
) -> OpenAIOcrEnrichmentResult:
    _require_segments(record)
    with tempfile.TemporaryDirectory(
        prefix="lecturedigest-ocr-",
        dir=str(temp_root) if temp_root is not None else None,
    ) as temp_dir:
        extraction_result = extract_frame_candidates(
            record.source_path,
            output_dir=temp_dir,
            method=method,
            sample_interval_seconds=sample_interval_seconds,
            scene_threshold=scene_threshold,
            fallback_to_interval=fallback_to_interval,
            tools=tools,
            runner=runner,
        )
        vision_result = run_vision_ocr_on_frames(
            extraction_result.frames,
            extraction_metadata=extraction_result.to_safe_metadata(),
            client=client,
            model=model,
            prompt_version=prompt_version,
            detail=detail,
        )
        updated = apply_ocr_enrichment_payload(
            record,
            ocr_payload=vision_result.ocr_payload,
            sample_interval_seconds=sample_interval_seconds,
            change_threshold=scene_threshold,
        )
    return OpenAIOcrEnrichmentResult(
        record=updated,
        extraction_result=extraction_result,
        vision_result=vision_result,
    )


def format_ocr_dry_run(
    record: LectureRecord,
    extraction_result: FrameExtractionResult,
    *,
    model: str,
    detail: str,
) -> str:
    media = extraction_result.media_preflight
    resolution = (
        f"{media.width}x{media.height}"
        if media.width is not None and media.height is not None
        else "unknown"
    )
    warnings = ",".join(media.warnings or []) or "none"
    frame_range = _frame_range(extraction_result)
    return "\n".join(
        [
            (
                "[LectureMedia] ocr preflight success "
                f"{{ fileSizeBytes={media.file_size_bytes}; "
                f"durationSeconds={media.duration_seconds:.3f}; "
                f"resolution={resolution}; warnings={warnings}; "
                f"method={extraction_result.method}; "
                f"frameCandidates={len(extraction_result.frames)}; "
                f"frameRange={frame_range} }}"
            ),
            (
                "[LectureEnrichment] ocr dry-run "
                f"{{ lectureId={record.lecture_id}; model={model}; "
                f"detail={detail}; "
                "externalDataBoundary=extracted frame images to OpenAI "
                "Vision OCR API; willUpload=false; willSave=false }}"
            ),
        ]
    )


def _format_ocr_success(record: LectureRecord) -> str:
    enriched_segments = sum(1 for segment in record.segments if segment.ocr_text)
    enrichment_issues = sum(
        1 for issue in record.issues if issue.stage == "enrichment"
    )
    return (
        "[LectureEnrichment] ocr success "
        f"{{ lectureId={record.lecture_id}; status={record.status}; "
        f"stage={record.stage}; slides={len(record.slides)}; "
        f"enrichedSegments={enriched_segments}; issues={enrichment_issues} }}"
    )


def _require_segments(record: LectureRecord) -> None:
    if record.segments:
        return
    raise EnrichmentError(
        ErrorDetail(
            code="segments_required",
            message="Transcript segments are required before OCR enrichment.",
            stage="enrichment",
            retryable=False,
        )
    )


def _vision_failed(result: VisionOcrRunResult) -> EnrichmentError:
    retryable = any(item.metadata.retryable for item in result.client_results)
    return EnrichmentError(
        ErrorDetail(
            code="vision_ocr_failed",
            message="Vision OCR completed without any successful frame results.",
            stage="enrichment",
            retryable=retryable,
        )
    )


def _frame_range(result: FrameExtractionResult) -> str:
    first = result.frames[0].source_frame_ts
    last = result.frames[-1].source_frame_ts
    return f"{first}..{last}"

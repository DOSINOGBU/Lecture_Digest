from __future__ import annotations

import tempfile
import shutil
from dataclasses import dataclass, replace
from pathlib import Path

from lecturedigest.errors import ErrorDetail, TranscriptionError, ValidationError
from lecturedigest.media_preflight import (
    AudioChunkArtifact,
    CommandRunner,
    MediaPreflightResult,
    MediaToolPaths,
    build_audio_chunk_plan,
    extract_audio_chunks,
    offset_transcript_segments,
    run_media_preflight,
)
from lecturedigest.models import LectureRecord, ProcessingIssue, TranscriptSegment
from lecturedigest.openai_client import OpenAIClient
from lecturedigest.openai_transcription import (
    DEFAULT_STT_CHUNKING_STRATEGY,
    DEFAULT_STT_TIMEOUT_SECONDS,
    MAX_TRANSCRIPTION_UPLOAD_BYTES,
    SUPPORTED_TRANSCRIPTION_EXTENSIONS,
    transcribe_lecture_with_openai,
)
from lecturedigest.openai_types import OpenAIClientResult
from lecturedigest.transcription import DEFAULT_STT_MODEL, DEFAULT_STT_RESPONSE_FORMAT


@dataclass(frozen=True)
class LargeOpenAITranscriptionResult:
    record: LectureRecord
    media_preflight: MediaPreflightResult
    chunk_plan: list[dict[str, object]]
    client_results: list[OpenAIClientResult]
    dry_run: bool = False


def transcribe_large_lecture_with_openai(
    record: LectureRecord,
    *,
    client: OpenAIClient | None = None,
    model: str = DEFAULT_STT_MODEL,
    response_format: str = DEFAULT_STT_RESPONSE_FORMAT,
    chunking_strategy: str = DEFAULT_STT_CHUNKING_STRATEGY,
    dry_run: bool = False,
    tools: MediaToolPaths | None = None,
    runner: CommandRunner | None = None,
    temp_root: str | Path | None = None,
) -> LargeOpenAITranscriptionResult:
    source_path = _validate_large_transcription_record(record)
    media_preflight = run_media_preflight(
        source_path,
        tools=tools,
        runner=runner or _default_runner,
    )
    planned_chunks = build_audio_chunk_plan(media_preflight)
    if dry_run:
        return LargeOpenAITranscriptionResult(
            record=record,
            media_preflight=media_preflight,
            chunk_plan=[chunk.to_dict() for chunk in planned_chunks],
            client_results=[],
            dry_run=True,
        )

    openai_client = client or OpenAIClient(timeout_seconds=DEFAULT_STT_TIMEOUT_SECONDS)
    output_dir = tempfile.mkdtemp(
        prefix="lecturedigest-stt-",
        dir=str(temp_root) if temp_root is not None else None,
    )
    try:
        artifacts = extract_audio_chunks(
            media_preflight,
            output_dir=output_dir,
            tools=tools,
            runner=runner or _default_runner,
        )
        result = _transcribe_audio_artifacts(
            record,
            artifacts=artifacts,
            client=openai_client,
            model=model,
            response_format=response_format,
            chunking_strategy=chunking_strategy,
            media_preflight=media_preflight,
        )
    except Exception:
        _cleanup_temp_dir(Path(output_dir))
        raise
    cleanup_issue = _cleanup_temp_dir(Path(output_dir))
    if cleanup_issue is not None:
        result = replace(
            result,
            record=replace(
                result.record,
                issues=[*result.record.issues, cleanup_issue],
            ),
        )
    return result


def format_large_transcription_dry_run(
    result: LargeOpenAITranscriptionResult,
) -> str:
    media = result.media_preflight
    resolution = (
        f"{media.width}x{media.height}"
        if media.width is not None and media.height is not None
        else "audio-only"
    )
    warnings = ",".join(media.warnings or []) or "none"
    return "\n".join(
        [
            (
                "[LectureMedia] preflight success "
                f"{{ fileSizeBytes={media.file_size_bytes}; "
                f"durationSeconds={media.duration_seconds:.3f}; "
                f"resolution={resolution}; hasAudio={media.has_audio}; "
                f"requiresSplit={media.requires_split}; warnings={warnings} }}"
            ),
            (
                "[LectureTranscription] split dry-run "
                f"{{ chunks={len(result.chunk_plan)}; "
                "externalDataBoundary=split audio chunks only; "
                "willUpload=false }}"
            ),
        ]
    )


def should_route_to_large_media(error: ValidationError) -> bool:
    return error.detail.code == "stt_file_too_large"


def _transcribe_audio_artifacts(
    record: LectureRecord,
    *,
    artifacts: list[AudioChunkArtifact],
    client: OpenAIClient,
    model: str,
    response_format: str,
    chunking_strategy: str,
    media_preflight: MediaPreflightResult,
) -> LargeOpenAITranscriptionResult:
    merged_segments: list[TranscriptSegment] = []
    client_results: list[OpenAIClientResult] = []
    for artifact in artifacts:
        chunk_record = replace(
            record,
            source_path=str(artifact.path),
            segments=[],
            chunks=[],
            issues=[],
            transcript_metadata={},
        )
        chunk_result = transcribe_lecture_with_openai(
            chunk_record,
            client=client,
            model=model,
            response_format=response_format,
            chunking_strategy=chunking_strategy,
        )
        client_results.append(chunk_result.client_result)
        if not chunk_result.client_result.succeeded:
            return _large_failure_result(
                record,
                artifact=artifact,
                media_preflight=media_preflight,
                artifacts=artifacts,
                client_results=client_results,
            )
        merged_segments.extend(
            offset_transcript_segments(
                chunk_result.record.segments,
                offset_seconds=artifact.plan.offset_seconds,
                start_index=len(merged_segments) + 1,
            )
        )

    if not merged_segments:
        raise TranscriptionError(
            ErrorDetail(
                code="stt_result_empty",
                message="Split transcription completed without timestamped segments.",
                stage="transcription",
                retryable=False,
            )
        )

    return LargeOpenAITranscriptionResult(
        record=replace(
            record,
            status="transcript_ready",
            stage="transcription",
            transcript_source="stt",
            segments=merged_segments,
            chunks=[],
            issues=[],
            transcript_metadata=_large_success_metadata(
                media_preflight,
                artifacts,
                client_results,
                model=model,
                response_format=response_format,
                chunking_strategy=chunking_strategy,
            ),
        ),
        media_preflight=media_preflight,
        chunk_plan=[artifact.to_safe_metadata() for artifact in artifacts],
        client_results=client_results,
        dry_run=False,
    )


def _large_failure_result(
    record: LectureRecord,
    *,
    artifact: AudioChunkArtifact,
    media_preflight: MediaPreflightResult,
    artifacts: list[AudioChunkArtifact],
    client_results: list[OpenAIClientResult],
) -> LargeOpenAITranscriptionResult:
    failed_result = client_results[-1]
    issue = failed_result.to_processing_issue(stage="transcription") or ProcessingIssue(
        code="openai_request_failed",
        message="OpenAI split transcription request failed.",
        stage="transcription",
        retryable=failed_result.metadata.retryable,
    )
    issue = replace(
        issue,
        message=f"{issue.message} chunk_id={artifact.plan.chunk_id}",
    )
    return LargeOpenAITranscriptionResult(
        record=replace(
            record,
            status="stt_failed",
            stage="transcription",
            issues=[*record.issues, issue],
            transcript_metadata=_large_failure_metadata(
                media_preflight,
                artifacts,
                client_results,
            ),
        ),
        media_preflight=media_preflight,
        chunk_plan=[item.to_safe_metadata() for item in artifacts],
        client_results=client_results,
        dry_run=False,
    )


def _validate_large_transcription_record(record: LectureRecord) -> Path:
    if record.segments:
        raise ValidationError(
            ErrorDetail(
                code="transcript_already_exists",
                message="Transcript segments already exist for this lecture.",
                stage="transcription",
                retryable=False,
            )
        )
    if record.transcript_source != "stt_pending":
        raise ValidationError(
            ErrorDetail(
                code="stt_not_expected",
                message="OpenAI transcription is only allowed for stt_pending lectures.",
                stage="transcription",
                retryable=False,
            )
        )

    source_path = Path(record.source_path).expanduser().resolve()
    if not source_path.exists() or not source_path.is_file():
        raise ValidationError(
            ErrorDetail(
                code="stt_file_not_found",
                message=f"STT source file was not found: {source_path}",
                stage="transcription",
                retryable=False,
            )
        )
    if source_path.suffix.lower() not in SUPPORTED_TRANSCRIPTION_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_TRANSCRIPTION_EXTENSIONS))
        raise ValidationError(
            ErrorDetail(
                code="stt_file_unsupported_extension",
                message=f"STT source file extension must be one of: {supported}",
                stage="transcription",
                retryable=False,
            )
        )
    if source_path.stat().st_size <= MAX_TRANSCRIPTION_UPLOAD_BYTES:
        raise ValidationError(
            ErrorDetail(
                code="stt_split_not_required",
                message="Media splitting is only used above the direct upload limit.",
                stage="transcription",
                retryable=False,
            )
        )
    return source_path


def _large_success_metadata(
    media_preflight: MediaPreflightResult,
    artifacts: list[AudioChunkArtifact],
    client_results: list[OpenAIClientResult],
    *,
    model: str,
    response_format: str,
    chunking_strategy: str,
) -> dict[str, object]:
    return {
        "provider": "openai_transcriptions",
        "model": model,
        "response_format": response_format,
        "chunking_strategy": chunking_strategy,
        "source_format": "split_audio_api_response",
        "media_preflight": media_preflight.to_safe_metadata(),
        "audio_chunks": [artifact.to_safe_metadata() for artifact in artifacts],
        "openai_calls": [result.metadata.to_dict() for result in client_results],
    }


def _large_failure_metadata(
    media_preflight: MediaPreflightResult,
    artifacts: list[AudioChunkArtifact],
    client_results: list[OpenAIClientResult],
) -> dict[str, object]:
    return {
        "provider": "openai_transcriptions",
        "source_format": "split_audio_api_response",
        "media_preflight": media_preflight.to_safe_metadata(),
        "audio_chunks": [artifact.to_safe_metadata() for artifact in artifacts],
        "openai_calls": [result.metadata.to_dict() for result in client_results],
    }


def _default_runner(*args, **kwargs):
    return __import__("subprocess").run(*args, **kwargs)


def _cleanup_temp_dir(path: Path) -> ProcessingIssue | None:
    try:
        shutil.rmtree(path)
    except Exception:
        return ProcessingIssue(
            code="temp_cleanup_failed",
            message="Temporary transcription files could not be deleted.",
            stage="transcription",
            retryable=True,
        )
    return None

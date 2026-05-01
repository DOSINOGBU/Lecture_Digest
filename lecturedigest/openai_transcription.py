from __future__ import annotations

import json
import mimetypes
from dataclasses import dataclass, replace
from pathlib import Path
from uuid import uuid4

from lecturedigest.errors import ErrorDetail, TranscriptionError, ValidationError
from lecturedigest.models import LectureRecord, ProcessingIssue, TranscriptSegment
from lecturedigest.openai_client import OpenAIClient, format_dry_run_result
from lecturedigest.openai_types import OpenAIClientResult, OpenAIRequest
from lecturedigest.transcription import (
    DEFAULT_STT_MODEL,
    DEFAULT_STT_RESPONSE_FORMAT,
    parse_diarized_json_payload,
)

OPENAI_TRANSCRIPTIONS_ENDPOINT = "/v1/audio/transcriptions"
OPENAI_TRANSCRIPTION_USE_CASE = "stt_transcription"
OPENAI_TRANSCRIPTION_PROMPT_VERSION = "openai-transcription-v1"
DEFAULT_STT_CHUNKING_STRATEGY = "auto"
DEFAULT_STT_TIMEOUT_SECONDS = 600.0
MAX_TRANSCRIPTION_UPLOAD_BYTES = 25 * 1024 * 1024
SUPPORTED_TRANSCRIPTION_EXTENSIONS = {
    ".mp3",
    ".mp4",
    ".mpeg",
    ".mpga",
    ".m4a",
    ".wav",
    ".webm",
}


@dataclass(frozen=True)
class TranscriptionPreflight:
    source_path: Path
    file_size_bytes: int
    extension: str
    model: str
    response_format: str
    chunking_strategy: str


@dataclass(frozen=True)
class OpenAITranscriptionResult:
    record: LectureRecord
    preflight: TranscriptionPreflight
    client_result: OpenAIClientResult


def transcribe_lecture_with_openai(
    record: LectureRecord,
    *,
    client: OpenAIClient | None = None,
    model: str = DEFAULT_STT_MODEL,
    response_format: str = DEFAULT_STT_RESPONSE_FORMAT,
    chunking_strategy: str = DEFAULT_STT_CHUNKING_STRATEGY,
    dry_run: bool = False,
) -> OpenAITranscriptionResult:
    preflight = validate_transcription_preflight(
        record,
        model=model,
        response_format=response_format,
        chunking_strategy=chunking_strategy,
    )
    request = build_transcription_request(preflight)
    openai_client = client or OpenAIClient(timeout_seconds=DEFAULT_STT_TIMEOUT_SECONDS)
    client_result = openai_client.send(request, dry_run=dry_run)

    if dry_run:
        return OpenAITranscriptionResult(
            record=record,
            preflight=preflight,
            client_result=client_result,
        )

    if not client_result.succeeded:
        return OpenAITranscriptionResult(
            record=_record_with_failed_transcription(record, client_result, preflight),
            preflight=preflight,
            client_result=client_result,
        )

    segments, transcript_metadata = _parse_openai_diarized_response(
        client_result.body,
    )
    transcript_metadata.update(
        _successful_transcript_metadata(client_result, preflight)
    )
    return OpenAITranscriptionResult(
        record=replace(
            record,
            status="transcript_ready",
            stage="transcription",
            transcript_source="stt",
            segments=segments,
            chunks=[],
            issues=[],
            transcript_metadata=transcript_metadata,
        ),
        preflight=preflight,
        client_result=client_result,
    )


def validate_transcription_preflight(
    record: LectureRecord,
    *,
    model: str = DEFAULT_STT_MODEL,
    response_format: str = DEFAULT_STT_RESPONSE_FORMAT,
    chunking_strategy: str = DEFAULT_STT_CHUNKING_STRATEGY,
) -> TranscriptionPreflight:
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

    extension = source_path.suffix.lower()
    if extension not in SUPPORTED_TRANSCRIPTION_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_TRANSCRIPTION_EXTENSIONS))
        raise ValidationError(
            ErrorDetail(
                code="stt_file_unsupported_extension",
                message=f"STT source file extension must be one of: {supported}",
                stage="transcription",
                retryable=False,
            )
        )

    try:
        file_size_bytes = source_path.stat().st_size
    except OSError as exc:
        raise ValidationError(
            ErrorDetail(
                code="stt_file_unreadable",
                message=f"STT source file could not be inspected: {source_path}",
                stage="transcription",
                retryable=False,
            )
        ) from exc
    if file_size_bytes <= 0:
        raise ValidationError(
            ErrorDetail(
                code="stt_file_empty",
                message=f"STT source file is empty: {source_path}",
                stage="transcription",
                retryable=False,
            )
        )
    if file_size_bytes > MAX_TRANSCRIPTION_UPLOAD_BYTES:
        raise ValidationError(
            ErrorDetail(
                code="stt_file_too_large",
                message=(
                    "STT source file exceeds the 25MB direct upload limit. "
                    "Use the later media splitting flow before transcription."
                ),
                stage="transcription",
                retryable=False,
            )
        )

    return TranscriptionPreflight(
        source_path=source_path,
        file_size_bytes=file_size_bytes,
        extension=extension,
        model=model,
        response_format=response_format,
        chunking_strategy=chunking_strategy,
    )


def build_transcription_request(preflight: TranscriptionPreflight) -> OpenAIRequest:
    body, content_type = _multipart_form_data(
        fields={
            "model": preflight.model,
            "response_format": preflight.response_format,
            "chunking_strategy": preflight.chunking_strategy,
        },
        file_path=preflight.source_path,
    )
    return OpenAIRequest(
        endpoint=OPENAI_TRANSCRIPTIONS_ENDPOINT,
        use_case=OPENAI_TRANSCRIPTION_USE_CASE,
        model=preflight.model,
        prompt_version=OPENAI_TRANSCRIPTION_PROMPT_VERSION,
        body=body,
        headers={"Content-Type": content_type},
        input_size_bytes=preflight.file_size_bytes,
        external_data_boundary=(
            "audio/video file upload to OpenAI Transcriptions API"
        ),
    )


def format_transcription_dry_run(result: OpenAITranscriptionResult) -> str:
    preflight = result.preflight
    return "\n".join(
        [
            format_dry_run_result(result.client_result),
            (
                "[LectureTranscription] transcribe dry-run "
                f"{{ source={preflight.source_path}; "
                f"fileSizeBytes={preflight.file_size_bytes}; "
                f"extension={preflight.extension}; "
                f"responseFormat={preflight.response_format}; "
                f"chunkingStrategy={preflight.chunking_strategy}; "
                "willUpload=false }}"
            ),
        ]
    )


def _multipart_form_data(
    *,
    fields: dict[str, str],
    file_path: Path,
) -> tuple[bytes, str]:
    boundary = f"lecturedigest-{uuid4().hex}"
    parts: list[bytes] = []
    for name, value in fields.items():
        parts.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                (
                    f'Content-Disposition: form-data; name="{name}"'
                    "\r\n\r\n"
                ).encode("utf-8"),
                str(value).encode("utf-8"),
                b"\r\n",
            ]
        )

    mime_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    parts.extend(
        [
            f"--{boundary}\r\n".encode("utf-8"),
            (
                'Content-Disposition: form-data; name="file"; '
                f'filename="{file_path.name}"\r\n'
                f"Content-Type: {mime_type}\r\n\r\n"
            ).encode("utf-8"),
            file_path.read_bytes(),
            b"\r\n",
            f"--{boundary}--\r\n".encode("utf-8"),
        ]
    )
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def _parse_openai_diarized_response(
    data: bytes,
) -> tuple[list[TranscriptSegment], dict[str, object]]:
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        message = (
            exc.msg
            if isinstance(exc, json.JSONDecodeError)
            else "response is not valid UTF-8"
        )
        raise TranscriptionError(
            ErrorDetail(
                code="stt_result_invalid_json",
                message=f"OpenAI transcription response could not be parsed: {message}",
                stage="transcription",
                retryable=False,
            )
        ) from exc
    if not isinstance(payload, dict):
        raise TranscriptionError(
            ErrorDetail(
                code="stt_result_invalid_schema",
                message="OpenAI transcription response must be a JSON object.",
                stage="transcription",
                retryable=False,
            )
        )

    normalized_payload = _normalize_diarized_payload(payload)
    return parse_diarized_json_payload(normalized_payload)


def _normalize_diarized_payload(
    payload: dict[str, object],
) -> dict[str, object]:
    raw_segments = payload.get("segments", payload.get("diarized_segments", []))
    if not isinstance(raw_segments, list):
        raise TranscriptionError(
            ErrorDetail(
                code="stt_segments_invalid",
                message="OpenAI transcription response segments must be a list.",
                stage="transcription",
                retryable=False,
            )
        )

    normalized_segments: list[object] = []
    for index, item in enumerate(raw_segments, start=1):
        if not isinstance(item, dict):
            continue
        normalized = dict(item)
        if (
            normalized.get("speaker") is None
            and normalized.get("speaker_id") is not None
        ):
            normalized["speaker"] = normalized["speaker_id"]
        if normalized.get("speaker") is None:
            raise TranscriptionError(
                ErrorDetail(
                    code="stt_speaker_missing",
                    message=(
                        "OpenAI diarized transcription segment is missing "
                        f"speaker metadata at index {index}."
                    ),
                    stage="transcription",
                    retryable=False,
                )
            )
        normalized_segments.append(normalized)

    normalized_payload = dict(payload)
    normalized_payload["segments"] = normalized_segments
    return normalized_payload


def _successful_transcript_metadata(
    result: OpenAIClientResult,
    preflight: TranscriptionPreflight,
) -> dict[str, object]:
    return {
        "provider": "openai_transcriptions",
        "model": preflight.model,
        "response_format": preflight.response_format,
        "chunking_strategy": preflight.chunking_strategy,
        "source_format": "api_response",
        "last_openai_call": result.metadata.to_dict(),
        "status_code": result.status_code,
    }


def _record_with_failed_transcription(
    record: LectureRecord,
    result: OpenAIClientResult,
    preflight: TranscriptionPreflight,
) -> LectureRecord:
    issue = result.to_processing_issue(stage="transcription") or ProcessingIssue(
        code="openai_request_failed",
        message="OpenAI transcription request failed.",
        stage="transcription",
        retryable=result.metadata.retryable,
    )
    transcript_metadata = dict(record.transcript_metadata)
    transcript_metadata.update(
        {
            "provider": "openai_transcriptions",
            "model": preflight.model,
            "response_format": preflight.response_format,
            "chunking_strategy": preflight.chunking_strategy,
            "last_openai_call": result.metadata.to_dict(),
            "status_code": result.status_code,
        }
    )
    return replace(
        record,
        status="stt_failed",
        stage="transcription",
        issues=[*record.issues, issue],
        transcript_metadata=transcript_metadata,
    )

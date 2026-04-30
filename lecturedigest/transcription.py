from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from lecturedigest.errors import (
    ErrorDetail,
    LectureDigestError,
    SubtitleParseError,
    TranscriptionError,
    ValidationError,
)
from lecturedigest.models import LectureRecord, TranscriptSegment
from lecturedigest.subtitles import parse_subtitle_file
from lecturedigest.timecode import (
    normalize_timestamp,
    seconds_to_timestamp,
    timestamp_to_seconds,
)

SUPPORTED_STT_RESULT_EXTENSIONS = {".srt", ".vtt", ".json"}
DEFAULT_STT_MODEL = "gpt-4o-transcribe-diarize"
DEFAULT_STT_RESPONSE_FORMAT = "diarized_json"


def apply_stt_result(
    record: LectureRecord,
    *,
    stt_result_path: str | Path,
) -> LectureRecord:
    if record.segments:
        raise ValidationError(
            ErrorDetail(
                code="transcript_already_exists",
                message="이미 대본 세그먼트가 있어 STT 결과를 덮어쓸 수 없습니다.",
                stage="transcription",
                retryable=False,
            )
        )
    if record.transcript_source != "stt_pending":
        raise ValidationError(
            ErrorDetail(
                code="stt_result_not_expected",
                message="STT 대기 상태의 강의에만 STT 결과를 저장할 수 있습니다.",
                stage="transcription",
                retryable=False,
            )
        )

    stt_result = _validate_stt_result_file(stt_result_path)
    segments, transcript_metadata = _parse_stt_result_with_metadata(stt_result)
    return replace(
        record,
        status="transcript_ready",
        stage="transcription",
        transcript_source="stt",
        segments=segments,
        chunks=[],
        issues=[],
        transcript_metadata=transcript_metadata,
    )


def parse_stt_result_file(path: Path) -> list[TranscriptSegment]:
    segments, _metadata = _parse_stt_result_with_metadata(path)
    return segments


def parse_diarized_json_payload(
    payload: dict[str, object],
) -> tuple[list[TranscriptSegment], dict[str, object]]:
    raw_segments = payload.get("segments", payload.get("diarized_segments", []))
    if not isinstance(raw_segments, list):
        raise TranscriptionError(
            ErrorDetail(
                code="stt_segments_invalid",
                message="STT result JSON `segments` must be a list.",
                stage="transcription",
                retryable=False,
            )
        )

    segments = [
        _json_segment_to_transcript(item, index)
        for index, item in enumerate(raw_segments, start=1)
        if isinstance(item, dict)
    ]
    if not segments:
        raise TranscriptionError(
            ErrorDetail(
                code="stt_result_empty",
                message="STT result JSON did not contain timestamped segments.",
                stage="transcription",
                retryable=False,
            )
        )
    return segments, _transcript_metadata(payload)


def parse_diarized_json_bytes(
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
                message=f"STT result JSON could not be parsed: {message}",
                stage="transcription",
                retryable=False,
            )
        ) from exc
    if not isinstance(payload, dict):
        raise TranscriptionError(
            ErrorDetail(
                code="stt_result_invalid_schema",
                message="STT result JSON must be an object.",
                stage="transcription",
                retryable=False,
            )
        )
    return parse_diarized_json_payload(payload)


def _parse_stt_result_with_metadata(
    path: Path,
) -> tuple[list[TranscriptSegment], dict[str, object]]:
    if path.suffix.lower() == ".json":
        return _parse_diarized_json_result(path)

    try:
        return parse_subtitle_file(path), {
            "source_format": path.suffix.lower().lstrip("."),
        }
    except SubtitleParseError as exc:
        detail = exc.detail
        code = _stt_error_code(detail.code)
        raise TranscriptionError(
            ErrorDetail(
                code=code,
                message=f"STT 결과를 시간축 세그먼트로 읽을 수 없습니다: {detail.message}",
                stage="transcription",
                retryable=detail.retryable,
            )
        ) from exc


def _parse_diarized_json_result(
    path: Path,
) -> tuple[list[TranscriptSegment], dict[str, object]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise TranscriptionError(
            ErrorDetail(
                code="stt_result_invalid_json",
                message=f"STT result JSON could not be parsed: {exc.msg}",
                stage="transcription",
                retryable=False,
            )
        ) from exc
    if not isinstance(payload, dict):
        raise TranscriptionError(
            ErrorDetail(
                code="stt_result_invalid_schema",
                message="STT result JSON must be an object.",
                stage="transcription",
                retryable=False,
            )
        )

    return parse_diarized_json_payload(payload)


def _json_segment_to_transcript(
    item: dict[str, object],
    index: int,
) -> TranscriptSegment:
    text = str(item.get("text") or item.get("transcript") or "").strip()
    if not text:
        raise TranscriptionError(
            ErrorDetail(
                code="stt_segment_text_required",
                message="STT JSON segment text is required.",
                stage="transcription",
                retryable=False,
            )
        )
    start_ts = _timestamp_from_segment_value(item.get("start", item.get("start_ts")))
    end_ts = _timestamp_from_segment_value(item.get("end", item.get("end_ts")))
    if timestamp_to_seconds(end_ts) <= timestamp_to_seconds(start_ts):
        raise TranscriptionError(
            ErrorDetail(
                code="stt_result_invalid_range",
                message="STT JSON segment end timestamp must be after start.",
                stage="transcription",
                retryable=False,
            )
        )
    return TranscriptSegment(
        segment_id=str(item.get("segment_id") or f"seg-{index:06d}"),
        start_ts=start_ts,
        end_ts=end_ts,
        text=text,
        speaker=(
            str(item["speaker"])
            if item.get("speaker") is not None
            else None
        ),
    )


def _timestamp_from_segment_value(value: object) -> str:
    if isinstance(value, (int, float)):
        if value < 0:
            raise _invalid_json_timestamp(value)
        return seconds_to_timestamp(float(value))
    if value is None:
        raise _invalid_json_timestamp(value)
    try:
        return normalize_timestamp(str(value))
    except ValueError as exc:
        raise _invalid_json_timestamp(value) from exc


def _invalid_json_timestamp(value: object) -> TranscriptionError:
    return TranscriptionError(
        ErrorDetail(
            code="stt_segment_timestamp_invalid",
            message=f"STT JSON segment timestamp is invalid: {value}",
            stage="transcription",
            retryable=False,
        )
    )


def _transcript_metadata(payload: dict[str, object]) -> dict[str, object]:
    metadata = payload.get("provider_metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}
    result = {str(key): value for key, value in metadata.items()}
    result.setdefault("provider", "openai_transcriptions")
    result.setdefault("model", DEFAULT_STT_MODEL)
    result.setdefault("response_format", DEFAULT_STT_RESPONSE_FORMAT)
    result.setdefault("source_format", "json")
    return result


def _validate_stt_result_file(path_value: str | Path) -> Path:
    path = Path(path_value).expanduser().resolve()
    if not path.exists() or not path.is_file():
        raise ValidationError(
            ErrorDetail(
                code="stt_result_not_found",
                message=f"STT 결과 파일을 찾을 수 없습니다: {path}",
                stage="transcription",
                retryable=False,
            )
        )
    if path.suffix.lower() not in SUPPORTED_STT_RESULT_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_STT_RESULT_EXTENSIONS))
        raise ValidationError(
            ErrorDetail(
                code="stt_result_unsupported_extension",
                message=f"STT 결과 파일 형식은 {supported} 중 하나여야 합니다.",
                stage="transcription",
                retryable=False,
            )
        )
    return path


def _stt_error_code(subtitle_code: str) -> str:
    mapping = {
        "subtitle_encoding_error": "stt_result_encoding_error",
        "subtitle_empty": "stt_result_empty",
        "subtitle_invalid_range": "stt_result_invalid_range",
        "subtitle_invalid_timestamp": "stt_result_invalid_timestamp",
    }
    return mapping.get(subtitle_code, "stt_result_parse_failed")

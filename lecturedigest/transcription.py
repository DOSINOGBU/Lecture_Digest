from __future__ import annotations

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

SUPPORTED_STT_RESULT_EXTENSIONS = {".srt", ".vtt"}


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
    segments = parse_stt_result_file(stt_result)
    return replace(
        record,
        status="transcript_ready",
        stage="transcription",
        transcript_source="stt",
        segments=segments,
        chunks=[],
        issues=[],
    )


def parse_stt_result_file(path: Path) -> list[TranscriptSegment]:
    try:
        return parse_subtitle_file(path)
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

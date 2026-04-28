from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from lecturedigest.errors import ErrorDetail, ValidationError
from lecturedigest.models import LectureRecord, ProcessingIssue
from lecturedigest.subtitles import parse_subtitle_file

SUPPORTED_VIDEO_EXTENSIONS = {".mp4", ".mkv", ".mov", ".webm"}
SUPPORTED_SUBTITLE_EXTENSIONS = {".srt", ".vtt"}


def register_lecture(
    *,
    video_path: str | Path,
    title: str,
    instructor: str,
    category: str,
    subtitle_path: str | Path | None = None,
) -> LectureRecord:
    video = _validate_file(video_path, SUPPORTED_VIDEO_EXTENSIONS, "video")
    subtitle = (
        _validate_file(subtitle_path, SUPPORTED_SUBTITLE_EXTENSIONS, "subtitle")
        if subtitle_path is not None
        else None
    )
    normalized_title = _require_text(title, "title")
    normalized_instructor = _require_text(instructor, "instructor")
    normalized_category = _require_text(category, "category")

    lecture_id = f"lec_{uuid4().hex[:12]}"
    created_at = datetime.now(UTC).isoformat()

    if subtitle is None:
        return LectureRecord(
            lecture_id=lecture_id,
            title=normalized_title,
            instructor=normalized_instructor,
            category=normalized_category,
            source_path=str(video),
            subtitle_path=None,
            status="stt_required",
            stage="awaiting_stt",
            transcript_source="stt_pending",
            segments=[],
            issues=[
                ProcessingIssue(
                    code="subtitle_missing",
                    message="자막이 없어 STT 처리가 필요합니다.",
                    stage="transcription",
                    retryable=False,
                )
            ],
            created_at=created_at,
        )

    segments = parse_subtitle_file(subtitle)
    return LectureRecord(
        lecture_id=lecture_id,
        title=normalized_title,
        instructor=normalized_instructor,
        category=normalized_category,
        source_path=str(video),
        subtitle_path=str(subtitle),
        status="transcript_ready",
        stage="transcription",
        transcript_source="subtitle",
        segments=segments,
        issues=[],
        created_at=created_at,
    )


def _validate_file(
    path_value: str | Path,
    supported_extensions: set[str],
    field_name: str,
) -> Path:
    path = Path(path_value).expanduser().resolve()
    if not path.exists() or not path.is_file():
        raise ValidationError(
            ErrorDetail(
                code=f"{field_name}_not_found",
                message=f"{field_name} 파일을 찾을 수 없습니다: {path}",
                stage="ingestion",
                retryable=False,
            )
        )
    if path.suffix.lower() not in supported_extensions:
        supported = ", ".join(sorted(supported_extensions))
        raise ValidationError(
            ErrorDetail(
                code=f"{field_name}_unsupported_extension",
                message=f"{field_name} 파일 형식은 {supported} 중 하나여야 합니다.",
                stage="ingestion",
                retryable=False,
            )
        )
    return path


def _require_text(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValidationError(
            ErrorDetail(
                code=f"{field_name}_required",
                message=f"{field_name} 값이 필요합니다.",
                stage="ingestion",
                retryable=False,
            )
        )
    return normalized

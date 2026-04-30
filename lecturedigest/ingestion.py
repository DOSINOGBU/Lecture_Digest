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
    input_mode: str = "file",
    lecture_title: str | None = None,
    major_category: str | None = None,
    middle_category: str | None = None,
    clip_title: str | None = None,
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
    normalized_lecture_title = _optional_text(lecture_title)
    normalized_major_category = _optional_text(major_category)
    normalized_middle_category = _optional_text(middle_category)
    normalized_clip_title = _optional_text(clip_title)

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
            input_mode=input_mode,
            lecture_title=normalized_lecture_title,
            major_category=normalized_major_category,
            middle_category=normalized_middle_category,
            clip_title=normalized_clip_title,
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
        input_mode=input_mode,
        lecture_title=normalized_lecture_title,
        major_category=normalized_major_category,
        middle_category=normalized_middle_category,
        clip_title=normalized_clip_title,
    )


def register_subtitle_unmatched_lecture(
    *,
    video_path: str | Path,
    title: str,
    instructor: str,
    category: str,
    lecture_title: str,
    major_category: str,
    middle_category: str,
    clip_title: str,
) -> LectureRecord:
    video = _validate_file(video_path, SUPPORTED_VIDEO_EXTENSIONS, "video")
    normalized_title = _require_text(title, "title")
    normalized_instructor = _require_text(instructor, "instructor")
    normalized_category = _require_text(category, "category")
    created_at = datetime.now(UTC).isoformat()

    return LectureRecord(
        lecture_id=f"lec_{uuid4().hex[:12]}",
        title=normalized_title,
        instructor=normalized_instructor,
        category=normalized_category,
        source_path=str(video),
        subtitle_path=None,
        status="subtitle_unmatched",
        stage="ingestion",
        transcript_source="subtitle_unmatched",
        segments=[],
        issues=[
            ProcessingIssue(
                code="subtitle_unmatched",
                message="Subtitle folder exists, but no subtitle matched this clip.",
                stage="ingestion",
                retryable=False,
            )
        ],
        created_at=created_at,
        input_mode="folder",
        lecture_title=_require_text(lecture_title, "lecture_title"),
        major_category=_require_text(major_category, "major_category"),
        middle_category=_require_text(middle_category, "middle_category"),
        clip_title=_require_text(clip_title, "clip_title"),
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


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None

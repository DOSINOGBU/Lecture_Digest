from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from lecturedigest.errors import ErrorDetail, ValidationError
from lecturedigest.ingestion import (
    SUPPORTED_SUBTITLE_EXTENSIONS,
    SUPPORTED_VIDEO_EXTENSIONS,
    register_lecture,
    register_subtitle_unmatched_lecture,
)
from lecturedigest.models import LectureRecord, ProcessingIssue

SUBTITLE_FOLDER_NAMES = {
    "captions",
    "subtitles",
    "\uc790\ub9c9",
    "\uc790\ub9c9\ud30c\uc77c",
}


@dataclass(frozen=True)
class FolderIngestionResult:
    root_path: str
    lecture_title: str
    records: list[LectureRecord] = field(default_factory=list)
    issues: list[ProcessingIssue] = field(default_factory=list)


def register_lecture_folder(
    *,
    folder_path: str | Path,
    instructor: str,
) -> FolderIngestionResult:
    root = _validate_folder(folder_path)
    normalized_instructor = _require_text(instructor, "instructor")
    lecture_title = _require_text(root.name, "lecture_title")
    records: list[LectureRecord] = []
    issues: list[ProcessingIssue] = []

    major_dirs = _child_dirs(root)
    if not major_dirs:
        return FolderIngestionResult(
            root_path=str(root),
            lecture_title=lecture_title,
            issues=[_issue("folder_empty", "Folder has no major category folders.")],
        )

    for major_dir in major_dirs:
        middle_dirs = _child_dirs(major_dir)
        if not middle_dirs:
            issues.append(
                _issue(
                    "major_category_empty",
                    f"Major category has no middle category folders: {major_dir}",
                )
            )
            continue

        for middle_dir in middle_dirs:
            result = _register_middle_category(
                lecture_title=lecture_title,
                instructor=normalized_instructor,
                major_dir=major_dir,
                middle_dir=middle_dir,
            )
            records.extend(result.records)
            issues.extend(result.issues)

    if not records and not issues:
        issues.append(_issue("folder_empty", "Folder has no supported lecture clips."))
    return FolderIngestionResult(
        root_path=str(root),
        lecture_title=lecture_title,
        records=records,
        issues=issues,
    )


def _register_middle_category(
    *,
    lecture_title: str,
    instructor: str,
    major_dir: Path,
    middle_dir: Path,
) -> FolderIngestionResult:
    records: list[LectureRecord] = []
    issues = _unsupported_file_issues(middle_dir)
    subtitle_dir = _find_subtitle_folder(middle_dir)
    subtitle_files = _subtitle_files(subtitle_dir) if subtitle_dir is not None else []
    videos = _video_files(middle_dir)

    if not videos:
        issues.append(
            _issue(
                "middle_category_empty",
                f"Middle category has no supported video clips: {middle_dir}",
            )
        )
        return FolderIngestionResult(
            root_path=str(middle_dir),
            lecture_title=lecture_title,
            records=records,
            issues=issues,
        )

    for video in videos:
        subtitle = _match_subtitle(video, subtitle_files)
        common = {
            "video_path": video,
            "title": video.stem,
            "instructor": instructor,
            "category": major_dir.name,
            "lecture_title": lecture_title,
            "major_category": major_dir.name,
            "middle_category": middle_dir.name,
            "clip_title": video.stem,
        }
        if subtitle_dir is not None and subtitle is None:
            records.append(register_subtitle_unmatched_lecture(**common))
            continue
        records.append(
            register_lecture(
                **common,
                subtitle_path=subtitle,
                input_mode="folder",
            )
        )

    return FolderIngestionResult(
        root_path=str(middle_dir),
        lecture_title=lecture_title,
        records=records,
        issues=issues,
    )


def _validate_folder(path_value: str | Path) -> Path:
    path = Path(path_value).expanduser().resolve()
    if not path.exists() or not path.is_dir():
        raise ValidationError(
            ErrorDetail(
                code="folder_not_found",
                message=f"Folder not found: {path}",
                stage="ingestion",
                retryable=False,
            )
        )
    return path


def _child_dirs(path: Path) -> list[Path]:
    return sorted(
        (
            child
            for child in path.iterdir()
            if child.is_dir() and child.name.casefold() not in SUBTITLE_FOLDER_NAMES
        ),
        key=lambda child: child.name.casefold(),
    )


def _find_subtitle_folder(path: Path) -> Path | None:
    matches = sorted(
        (
            child
            for child in path.iterdir()
            if child.is_dir() and child.name.casefold() in SUBTITLE_FOLDER_NAMES
        ),
        key=lambda child: child.name.casefold(),
    )
    return matches[0] if matches else None


def _video_files(path: Path) -> list[Path]:
    return sorted(
        (
            child
            for child in path.iterdir()
            if child.is_file() and child.suffix.lower() in SUPPORTED_VIDEO_EXTENSIONS
        ),
        key=lambda child: child.name.casefold(),
    )


def _subtitle_files(path: Path | None) -> list[Path]:
    if path is None:
        return []
    return sorted(
        (
            child
            for child in path.iterdir()
            if child.is_file() and child.suffix.lower() in SUPPORTED_SUBTITLE_EXTENSIONS
        ),
        key=lambda child: child.name.casefold(),
    )


def _match_subtitle(video: Path, subtitle_files: list[Path]) -> Path | None:
    stem_matches = [
        subtitle
        for subtitle in subtitle_files
        if subtitle.stem.casefold() == video.stem.casefold()
    ]
    if len(stem_matches) == 1:
        return stem_matches[0]

    prefix = _leading_number(video.stem)
    if prefix is None:
        return None
    prefix_matches = [
        subtitle
        for subtitle in subtitle_files
        if _leading_number(subtitle.stem) == prefix
    ]
    return prefix_matches[0] if len(prefix_matches) == 1 else None


def _leading_number(value: str) -> str | None:
    match = re.match(r"^(\d+)", value.strip())
    return match.group(1) if match else None


def _unsupported_file_issues(path: Path) -> list[ProcessingIssue]:
    issues: list[ProcessingIssue] = []
    for child in sorted(path.iterdir(), key=lambda item: item.name.casefold()):
        if not child.is_file():
            continue
        if child.suffix.lower() in SUPPORTED_VIDEO_EXTENSIONS:
            continue
        issues.append(
            _issue(
                "unsupported_file",
                f"Unsupported file in middle category folder: {child}",
            )
        )
    return issues


def _require_text(value: str, field_name: str) -> str:
    normalized = value.strip()
    if normalized:
        return normalized
    raise ValidationError(
        ErrorDetail(
            code=f"{field_name}_required",
            message=f"{field_name} is required.",
            stage="ingestion",
            retryable=False,
        )
    )


def _issue(code: str, message: str) -> ProcessingIssue:
    return ProcessingIssue(
        code=code,
        message=message,
        stage="ingestion",
        retryable=False,
    )

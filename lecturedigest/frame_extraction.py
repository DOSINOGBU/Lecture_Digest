from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from lecturedigest.errors import EnrichmentError, ErrorDetail, ValidationError
from lecturedigest.media_preflight import (
    CommandRunner,
    MediaPreflightResult,
    MediaToolPaths,
    locate_media_tools,
    run_media_preflight,
)
from lecturedigest.timecode import seconds_to_timestamp

FRAME_EXTRACTION_STAGE = "enrichment"
DEFAULT_FRAME_EXTRACTION_INTERVAL_SECONDS = 30
DEFAULT_SCENE_CHANGE_THRESHOLD = 0.35
FRAME_METHOD_SCENE = "scene"
FRAME_METHOD_INTERVAL = "interval"
SUPPORTED_FRAME_METHODS = {FRAME_METHOD_SCENE, FRAME_METHOD_INTERVAL}

_PTS_TIME_PATTERN = re.compile(r"pts_time:(?P<seconds>[0-9]+(?:\.[0-9]+)?)")


@dataclass(frozen=True)
class FrameCandidate:
    frame_id: str
    source_frame_ts: str
    frame_path: Path | None
    frame_width: int | None
    frame_height: int | None
    change_score: float
    extraction_method: str
    status: str = "candidate"

    @property
    def safe_frame_name(self) -> str:
        if self.frame_path is None:
            return f"{self.frame_id}.jpg"
        return self.frame_path.name


@dataclass(frozen=True)
class FrameExtractionResult:
    media_preflight: MediaPreflightResult
    frames: list[FrameCandidate]
    method: str
    fallback_used: bool
    duplicate_frames_removed: int
    sample_interval_seconds: int
    scene_threshold: float

    def to_safe_metadata(self) -> dict[str, object]:
        return {
            "provider": "ffmpeg",
            "method": self.method,
            "fallback_used": self.fallback_used,
            "frame_candidates": len(self.frames),
            "duplicate_frames_removed": self.duplicate_frames_removed,
            "sample_interval_seconds": self.sample_interval_seconds,
            "scene_threshold": self.scene_threshold,
            "media_preflight": self.media_preflight.to_safe_metadata(),
            "status": "succeeded",
        }


def extract_frame_candidates(
    source_path: str | Path,
    *,
    output_dir: str | Path,
    method: str = FRAME_METHOD_SCENE,
    sample_interval_seconds: int = DEFAULT_FRAME_EXTRACTION_INTERVAL_SECONDS,
    scene_threshold: float = DEFAULT_SCENE_CHANGE_THRESHOLD,
    fallback_to_interval: bool = True,
    tools: MediaToolPaths | None = None,
    runner: CommandRunner = subprocess.run,
) -> FrameExtractionResult:
    _validate_frame_settings(method, sample_interval_seconds, scene_threshold)
    tool_paths = tools or locate_media_tools()
    preflight = _preflight_video(source_path, tools=tool_paths, runner=runner)
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)

    fallback_used = False
    if method == FRAME_METHOD_INTERVAL:
        frames = _extract_interval_frames(
            preflight,
            output_root / FRAME_METHOD_INTERVAL,
            tools=tool_paths,
            runner=runner,
            sample_interval_seconds=sample_interval_seconds,
        )
    else:
        try:
            frames = _extract_scene_frames(
                preflight,
                output_root / FRAME_METHOD_SCENE,
                tools=tool_paths,
                runner=runner,
                sample_interval_seconds=sample_interval_seconds,
                scene_threshold=scene_threshold,
            )
        except EnrichmentError:
            if not fallback_to_interval:
                raise
            frames = []
        if not frames and fallback_to_interval:
            fallback_used = True
            frames = _extract_interval_frames(
                preflight,
                output_root / FRAME_METHOD_INTERVAL,
                tools=tool_paths,
                runner=runner,
                sample_interval_seconds=sample_interval_seconds,
            )

    unique_frames, duplicate_count = _deduplicate_frames(frames)
    if not unique_frames:
        raise _frame_error(
            "frame_extraction_empty",
            "No representative video frames could be extracted.",
            retryable=False,
        )
    return FrameExtractionResult(
        media_preflight=preflight,
        frames=unique_frames,
        method=method,
        fallback_used=fallback_used,
        duplicate_frames_removed=duplicate_count,
        sample_interval_seconds=sample_interval_seconds,
        scene_threshold=scene_threshold,
    )


def plan_frame_candidates_for_dry_run(
    source_path: str | Path,
    *,
    method: str = FRAME_METHOD_SCENE,
    sample_interval_seconds: int = DEFAULT_FRAME_EXTRACTION_INTERVAL_SECONDS,
    scene_threshold: float = DEFAULT_SCENE_CHANGE_THRESHOLD,
    tools: MediaToolPaths | None = None,
    runner: CommandRunner = subprocess.run,
) -> FrameExtractionResult:
    _validate_frame_settings(method, sample_interval_seconds, scene_threshold)
    tool_paths = tools or locate_media_tools()
    preflight = _preflight_video(source_path, tools=tool_paths, runner=runner)
    frames = [
        _candidate(
            index=index,
            timestamp_seconds=timestamp_seconds,
            frame_path=None,
            preflight=preflight,
            method=f"{method}_dry_run_estimate",
            change_score=1.0,
        )
        for index, timestamp_seconds in enumerate(
            _interval_timestamps(preflight.duration_seconds, sample_interval_seconds),
            start=1,
        )
    ]
    if not frames:
        raise _frame_error(
            "frame_extraction_empty",
            "No representative video frame candidates could be planned.",
            retryable=False,
        )
    return FrameExtractionResult(
        media_preflight=preflight,
        frames=frames,
        method=method,
        fallback_used=False,
        duplicate_frames_removed=0,
        sample_interval_seconds=sample_interval_seconds,
        scene_threshold=scene_threshold,
    )


def _extract_scene_frames(
    preflight: MediaPreflightResult,
    output_dir: Path,
    *,
    tools: MediaToolPaths,
    runner: CommandRunner,
    sample_interval_seconds: int,
    scene_threshold: float,
) -> list[FrameCandidate]:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_pattern = output_dir / "frame-%06d.jpg"
    filter_graph = f"select=gt(scene\\,{scene_threshold}),showinfo"
    command = [
        tools.ffmpeg_path,
        "-y",
        "-hide_banner",
        "-i",
        str(preflight.source_path),
        "-vf",
        filter_graph,
        "-vsync",
        "vfr",
        str(output_pattern),
    ]
    result = runner(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise _frame_error(
            "ffmpeg_frame_extraction_failed",
            "ffmpeg scene detection failed while extracting OCR frames.",
            retryable=False,
        )
    files = _nonempty_frame_files(output_dir)
    timestamps = _parse_showinfo_timestamps(result)
    return [
        _candidate(
            index=index,
            timestamp_seconds=_timestamp_for_index(
                index,
                timestamps,
                sample_interval_seconds,
            ),
            frame_path=frame_path,
            preflight=preflight,
            method=FRAME_METHOD_SCENE,
            change_score=scene_threshold,
        )
        for index, frame_path in enumerate(files, start=1)
    ]


def _extract_interval_frames(
    preflight: MediaPreflightResult,
    output_dir: Path,
    *,
    tools: MediaToolPaths,
    runner: CommandRunner,
    sample_interval_seconds: int,
) -> list[FrameCandidate]:
    output_dir.mkdir(parents=True, exist_ok=True)
    frames: list[FrameCandidate] = []
    for index, timestamp_seconds in enumerate(
        _interval_timestamps(preflight.duration_seconds, sample_interval_seconds),
        start=1,
    ):
        output_path = output_dir / f"frame-{index:06d}.jpg"
        command = [
            tools.ffmpeg_path,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            str(round(timestamp_seconds, 3)),
            "-i",
            str(preflight.source_path),
            "-frames:v",
            "1",
            str(output_path),
        ]
        result = runner(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise _frame_error(
                "ffmpeg_frame_extraction_failed",
                "ffmpeg interval sampling failed while extracting OCR frames.",
                retryable=False,
            )
        if output_path.exists() and output_path.stat().st_size > 0:
            frames.append(
                _candidate(
                    index=index,
                    timestamp_seconds=timestamp_seconds,
                    frame_path=output_path,
                    preflight=preflight,
                    method=FRAME_METHOD_INTERVAL,
                    change_score=1.0,
                )
            )
    return frames


def _preflight_video(
    source_path: str | Path,
    *,
    tools: MediaToolPaths,
    runner: CommandRunner,
) -> MediaPreflightResult:
    preflight = run_media_preflight(source_path, tools=tools, runner=runner)
    if not preflight.has_video:
        raise ValidationError(
            ErrorDetail(
                code="media_video_track_missing",
                message="Media file does not contain a video track for OCR.",
                stage=FRAME_EXTRACTION_STAGE,
                retryable=False,
            )
        )
    return preflight


def _candidate(
    *,
    index: int,
    timestamp_seconds: float,
    frame_path: Path | None,
    preflight: MediaPreflightResult,
    method: str,
    change_score: float,
) -> FrameCandidate:
    return FrameCandidate(
        frame_id=f"frame-{index:06d}",
        source_frame_ts=seconds_to_timestamp(timestamp_seconds),
        frame_path=frame_path,
        frame_width=preflight.width,
        frame_height=preflight.height,
        change_score=change_score,
        extraction_method=method,
    )


def _interval_timestamps(duration_seconds: float, sample_interval_seconds: int):
    timestamp = 0.0
    while timestamp < duration_seconds:
        yield round(timestamp, 3)
        timestamp += sample_interval_seconds


def _timestamp_for_index(
    index: int,
    timestamps: list[float],
    sample_interval_seconds: int,
) -> float:
    if index - 1 < len(timestamps):
        return timestamps[index - 1]
    return float((index - 1) * sample_interval_seconds)


def _parse_showinfo_timestamps(
    result: subprocess.CompletedProcess,
) -> list[float]:
    output = f"{result.stdout or ''}\n{result.stderr or ''}"
    return [
        float(match.group("seconds"))
        for match in _PTS_TIME_PATTERN.finditer(output)
    ]


def _nonempty_frame_files(output_dir: Path) -> list[Path]:
    return sorted(
        item
        for item in output_dir.glob("*.jpg")
        if item.is_file() and item.stat().st_size > 0
    )


def _deduplicate_frames(
    frames: list[FrameCandidate],
) -> tuple[list[FrameCandidate], int]:
    seen_timestamps: set[str] = set()
    unique: list[FrameCandidate] = []
    for frame in frames:
        if frame.source_frame_ts in seen_timestamps:
            continue
        seen_timestamps.add(frame.source_frame_ts)
        unique.append(frame)
    return unique, len(frames) - len(unique)


def _validate_frame_settings(
    method: str,
    sample_interval_seconds: int,
    scene_threshold: float,
) -> None:
    if method not in SUPPORTED_FRAME_METHODS:
        supported = ", ".join(sorted(SUPPORTED_FRAME_METHODS))
        raise ValidationError(
            ErrorDetail(
                code="frame_extraction_method_invalid",
                message=f"Frame extraction method must be one of: {supported}",
                stage=FRAME_EXTRACTION_STAGE,
                retryable=False,
            )
        )
    if sample_interval_seconds <= 0:
        raise ValidationError(
            ErrorDetail(
                code="frame_sample_interval_invalid",
                message="Frame sample interval must be at least 1 second.",
                stage=FRAME_EXTRACTION_STAGE,
                retryable=False,
            )
        )
    if scene_threshold < 0:
        raise ValidationError(
            ErrorDetail(
                code="scene_threshold_invalid",
                message="Scene threshold must be 0 or greater.",
                stage=FRAME_EXTRACTION_STAGE,
                retryable=False,
            )
        )


def _frame_error(
    code: str,
    message: str,
    *,
    retryable: bool,
) -> EnrichmentError:
    return EnrichmentError(
        ErrorDetail(
            code=code,
            message=message,
            stage=FRAME_EXTRACTION_STAGE,
            retryable=retryable,
        )
    )

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Protocol

from lecturedigest.errors import ErrorDetail, TranscriptionError, ValidationError
from lecturedigest.models import TranscriptSegment
from lecturedigest.openai_transcription import MAX_TRANSCRIPTION_UPLOAD_BYTES
from lecturedigest.timecode import seconds_to_timestamp, timestamp_to_seconds

MEDIA_STAGE = "media_preflight"
DEFAULT_AUDIO_CHUNK_SECONDS = 600.0
DEFAULT_AUDIO_BITRATE = "64k"
DEFAULT_AUDIO_SAMPLE_RATE = "16000"
DEFAULT_AUDIO_CHANNELS = "1"
SPLIT_TARGET_MAX_BYTES = 20 * 1024 * 1024


class CommandRunner(Protocol):
    def __call__(
        self,
        command: list[str],
        *,
        capture_output: bool,
        text: bool,
        check: bool,
    ) -> subprocess.CompletedProcess:
        ...


@dataclass(frozen=True)
class MediaToolPaths:
    ffmpeg_path: str
    ffprobe_path: str


@dataclass(frozen=True)
class MediaPreflightResult:
    source_path: Path
    file_size_bytes: int
    duration_seconds: float
    has_audio: bool
    has_video: bool
    width: int | None = None
    height: int | None = None
    video_codec: str | None = None
    audio_codec: str | None = None
    warnings: list[str] | None = None

    @property
    def requires_split(self) -> bool:
        return self.file_size_bytes > MAX_TRANSCRIPTION_UPLOAD_BYTES

    @property
    def direct_upload_allowed(self) -> bool:
        return not self.requires_split

    def to_safe_metadata(self) -> dict[str, object]:
        result = asdict(self)
        result["source_path"] = self.source_path.name
        result["requires_split"] = self.requires_split
        result["direct_upload_allowed"] = self.direct_upload_allowed
        return result


@dataclass(frozen=True)
class AudioChunkPlan:
    chunk_id: str
    offset_seconds: float
    duration_seconds: float
    max_upload_bytes: int = SPLIT_TARGET_MAX_BYTES

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class AudioChunkArtifact:
    plan: AudioChunkPlan
    path: Path
    file_size_bytes: int

    def to_safe_metadata(self) -> dict[str, object]:
        result = self.plan.to_dict()
        result["file_size_bytes"] = self.file_size_bytes
        result["path"] = self.path.name
        return result


def locate_media_tools(
    *,
    ffmpeg_path: str | None = None,
    ffprobe_path: str | None = None,
    search_path: str | None = None,
) -> MediaToolPaths:
    ffmpeg = _resolve_tool("ffmpeg", ffmpeg_path, search_path)
    ffprobe = _resolve_tool("ffprobe", ffprobe_path, search_path)
    return MediaToolPaths(ffmpeg_path=ffmpeg, ffprobe_path=ffprobe)


def run_media_preflight(
    source_path: str | Path,
    *,
    tools: MediaToolPaths | None = None,
    runner: CommandRunner = subprocess.run,
) -> MediaPreflightResult:
    media_path = Path(source_path).expanduser().resolve()
    file_size_bytes = _file_size(media_path)
    tool_paths = tools or locate_media_tools()
    command = [
        tool_paths.ffprobe_path,
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(media_path),
    ]
    result = runner(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise TranscriptionError(
            ErrorDetail(
                code="ffprobe_failed",
                message=(
                    "ffprobe could not inspect the media file. "
                    "Check that the file is readable and not corrupt."
                ),
                stage=MEDIA_STAGE,
                retryable=False,
            )
        )
    return parse_ffprobe_json(
        result.stdout,
        source_path=media_path,
        file_size_bytes=file_size_bytes,
    )


def parse_ffprobe_json(
    payload: str | dict[str, object],
    *,
    source_path: str | Path,
    file_size_bytes: int,
) -> MediaPreflightResult:
    parsed = _decode_ffprobe_payload(payload)
    streams = parsed.get("streams", [])
    if not isinstance(streams, list):
        raise _invalid_media("ffprobe_streams_invalid", "`streams` must be a list.")
    stream_items = [item for item in streams if isinstance(item, dict)]

    duration_seconds = _duration_from_payload(parsed, stream_items)
    audio_stream = _first_stream(stream_items, "audio")
    if audio_stream is None:
        raise _invalid_media(
            "media_audio_track_missing",
            "Media file does not contain an audio track.",
        )

    video_stream = _first_stream(stream_items, "video")
    width, height = _resolution_from_stream(video_stream)
    warnings = _media_warnings(width, height)
    return MediaPreflightResult(
        source_path=Path(source_path),
        file_size_bytes=_valid_file_size(file_size_bytes),
        duration_seconds=duration_seconds,
        has_audio=True,
        has_video=video_stream is not None,
        width=width,
        height=height,
        video_codec=_optional_string(video_stream, "codec_name"),
        audio_codec=_optional_string(audio_stream, "codec_name"),
        warnings=warnings,
    )


def build_audio_chunk_plan(
    preflight: MediaPreflightResult,
    *,
    chunk_seconds: float = DEFAULT_AUDIO_CHUNK_SECONDS,
) -> list[AudioChunkPlan]:
    if chunk_seconds <= 0:
        raise _invalid_media(
            "audio_chunk_duration_invalid",
            "Audio chunk duration must be greater than zero.",
        )
    plans: list[AudioChunkPlan] = []
    offset = 0.0
    index = 1
    while offset < preflight.duration_seconds:
        duration = min(chunk_seconds, preflight.duration_seconds - offset)
        plans.append(
            AudioChunkPlan(
                chunk_id=f"chunk-{index:06d}",
                offset_seconds=round(offset, 3),
                duration_seconds=round(duration, 3),
            )
        )
        offset += duration
        index += 1
    if not plans:
        raise _invalid_media("audio_chunk_plan_empty", "No audio chunks were planned.")
    return plans


def extract_audio_chunks(
    preflight: MediaPreflightResult,
    *,
    output_dir: str | Path,
    tools: MediaToolPaths | None = None,
    runner: CommandRunner = subprocess.run,
    chunk_seconds: float = DEFAULT_AUDIO_CHUNK_SECONDS,
) -> list[AudioChunkArtifact]:
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    tool_paths = tools or locate_media_tools()
    artifacts: list[AudioChunkArtifact] = []
    for plan in build_audio_chunk_plan(preflight, chunk_seconds=chunk_seconds):
        output_path = output_root / f"{plan.chunk_id}.m4a"
        command = _ffmpeg_split_command(preflight.source_path, output_path, tool_paths, plan)
        result = runner(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise TranscriptionError(
                ErrorDetail(
                    code="ffmpeg_audio_split_failed",
                    message=(
                        "ffmpeg could not extract a transcription audio chunk. "
                        f"chunk_id={plan.chunk_id}"
                    ),
                    stage="transcription",
                    retryable=False,
                )
            )
        artifacts.append(
            AudioChunkArtifact(
                plan=plan,
                path=output_path,
                file_size_bytes=_validated_chunk_size(output_path, plan.chunk_id),
            )
        )
    return artifacts


def offset_transcript_segments(
    segments: list[TranscriptSegment],
    *,
    offset_seconds: float,
    start_index: int = 1,
) -> list[TranscriptSegment]:
    offset_segments: list[TranscriptSegment] = []
    for index, segment in enumerate(segments, start=start_index):
        start_seconds = timestamp_to_seconds(segment.start_ts) + offset_seconds
        end_seconds = timestamp_to_seconds(segment.end_ts) + offset_seconds
        offset_segments.append(
            replace(
                segment,
                segment_id=f"seg-{index:06d}",
                start_ts=seconds_to_timestamp(start_seconds),
                end_ts=seconds_to_timestamp(end_seconds),
            )
        )
    return offset_segments


def _resolve_tool(
    tool_name: str,
    explicit_path: str | None,
    search_path: str | None,
) -> str:
    candidate = explicit_path or shutil.which(tool_name, path=search_path)
    if candidate:
        return str(candidate)
    raise ValidationError(
        ErrorDetail(
            code=f"{tool_name}_not_found",
            message=(
                f"{tool_name} was not found. Install ffmpeg and ensure both "
                "ffmpeg and ffprobe are available on PATH."
            ),
            stage=MEDIA_STAGE,
            retryable=False,
        )
    )


def _file_size(path: Path) -> int:
    if not path.exists() or not path.is_file():
        raise ValidationError(
            ErrorDetail(
                code="media_file_not_found",
                message=f"Media file was not found: {path}",
                stage=MEDIA_STAGE,
                retryable=False,
            )
        )
    try:
        return _valid_file_size(path.stat().st_size)
    except OSError as exc:
        raise ValidationError(
            ErrorDetail(
                code="media_file_unreadable",
                message=f"Media file could not be inspected: {path.name}",
                stage=MEDIA_STAGE,
                retryable=False,
            )
        ) from exc


def _valid_file_size(file_size_bytes: int) -> int:
    if file_size_bytes <= 0:
        raise _invalid_media("media_file_size_invalid", "Media file size is invalid.")
    return file_size_bytes


def _decode_ffprobe_payload(payload: str | dict[str, object]) -> dict[str, object]:
    if isinstance(payload, dict):
        return payload
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise _invalid_media(
            "ffprobe_json_invalid",
            f"ffprobe JSON could not be parsed: {exc.msg}",
        ) from exc
    if not isinstance(parsed, dict):
        raise _invalid_media("ffprobe_json_invalid", "ffprobe JSON must be an object.")
    return parsed


def _duration_from_payload(
    payload: dict[str, object],
    streams: list[dict[str, object]],
) -> float:
    media_format = payload.get("format", {})
    duration = None
    if isinstance(media_format, dict):
        duration = _optional_float(media_format.get("duration"))
    if duration is None:
        stream_durations = [
            value
            for value in (_optional_float(stream.get("duration")) for stream in streams)
            if value is not None
        ]
        duration = max(stream_durations) if stream_durations else None
    if duration is None or duration <= 0:
        raise _invalid_media(
            "media_duration_missing",
            "Media duration could not be determined.",
        )
    return duration


def _first_stream(
    streams: list[dict[str, object]],
    codec_type: str,
) -> dict[str, object] | None:
    for stream in streams:
        if stream.get("codec_type") == codec_type:
            return stream
    return None


def _resolution_from_stream(
    video_stream: dict[str, object] | None,
) -> tuple[int | None, int | None]:
    if video_stream is None:
        return None, None
    width = _optional_int(video_stream.get("width"))
    height = _optional_int(video_stream.get("height"))
    if width is None or height is None or width <= 0 or height <= 0:
        raise _invalid_media(
            "media_resolution_missing",
            "Video resolution could not be determined.",
        )
    return width, height


def _media_warnings(width: int | None, height: int | None) -> list[str]:
    if width is None or height is None:
        return []
    if width < 1920 or height < 1080:
        return ["video_below_1080p"]
    return []


def _ffmpeg_split_command(
    source_path: Path,
    output_path: Path,
    tools: MediaToolPaths,
    plan: AudioChunkPlan,
) -> list[str]:
    return [
        tools.ffmpeg_path,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        str(plan.offset_seconds),
        "-t",
        str(plan.duration_seconds),
        "-i",
        str(source_path),
        "-vn",
        "-ac",
        DEFAULT_AUDIO_CHANNELS,
        "-ar",
        DEFAULT_AUDIO_SAMPLE_RATE,
        "-b:a",
        DEFAULT_AUDIO_BITRATE,
        str(output_path),
    ]


def _validated_chunk_size(path: Path, chunk_id: str) -> int:
    size = _file_size(path)
    if size > MAX_TRANSCRIPTION_UPLOAD_BYTES:
        raise TranscriptionError(
            ErrorDetail(
                code="audio_chunk_too_large",
                message=(
                    "Extracted audio chunk exceeds the OpenAI direct upload limit. "
                    f"chunk_id={chunk_id}"
                ),
                stage="transcription",
                retryable=False,
            )
        )
    return size


def _optional_string(stream: dict[str, object] | None, key: str) -> str | None:
    if stream is None or stream.get(key) is None:
        return None
    return str(stream[key])


def _optional_float(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _invalid_media(code: str, message: str) -> ValidationError:
    return ValidationError(
        ErrorDetail(
            code=code,
            message=message,
            stage=MEDIA_STAGE,
            retryable=False,
        )
    )

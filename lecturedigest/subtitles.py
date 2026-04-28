from __future__ import annotations

from pathlib import Path

from lecturedigest.errors import ErrorDetail, SubtitleParseError
from lecturedigest.models import TranscriptSegment
from lecturedigest.timecode import normalize_timestamp, timestamp_to_seconds

TIMING_SEPARATOR = "-->"


def parse_subtitle_file(path: Path) -> list[TranscriptSegment]:
    try:
        content = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise SubtitleParseError(
            ErrorDetail(
                code="subtitle_encoding_error",
                message="자막 파일을 UTF-8로 읽을 수 없습니다.",
                stage="subtitle_parse",
                retryable=False,
            )
        ) from exc

    segments = parse_subtitle_text(content)
    if not segments:
        raise SubtitleParseError(
            ErrorDetail(
                code="subtitle_empty",
                message="자막 파일에서 시간축 세그먼트를 찾지 못했습니다.",
                stage="subtitle_parse",
                retryable=False,
            )
        )
    return segments


def parse_subtitle_text(content: str) -> list[TranscriptSegment]:
    lines = content.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    segments: list[TranscriptSegment] = []
    index = 0

    while index < len(lines):
        line = lines[index].strip()
        if _should_skip_line(line):
            index += 1
            continue
        if line.startswith("NOTE"):
            index = _skip_block(lines, index + 1)
            continue
        if TIMING_SEPARATOR not in line:
            index += 1
            continue

        start_ts, end_ts = _parse_timing_line(line)
        text_lines: list[str] = []
        index += 1
        while index < len(lines) and lines[index].strip():
            text_lines.append(lines[index].strip())
            index += 1

        text = " ".join(text_lines).strip()
        if text:
            segments.append(
                TranscriptSegment(
                    segment_id=f"seg-{len(segments) + 1:06d}",
                    start_ts=start_ts,
                    end_ts=end_ts,
                    text=text,
                )
            )
        index += 1

    return segments


def _should_skip_line(line: str) -> bool:
    return not line or line == "WEBVTT" or line.startswith(("STYLE", "REGION"))


def _skip_block(lines: list[str], index: int) -> int:
    while index < len(lines) and lines[index].strip():
        index += 1
    return index + 1


def _parse_timing_line(line: str) -> tuple[str, str]:
    left, right = line.split(TIMING_SEPARATOR, maxsplit=1)
    start_ts = _normalize_subtitle_timestamp(left.strip())
    end_token = right.strip().split()[0] if right.strip() else ""
    end_ts = _normalize_subtitle_timestamp(end_token)

    if timestamp_to_seconds(end_ts) <= timestamp_to_seconds(start_ts):
        raise SubtitleParseError(
            ErrorDetail(
                code="subtitle_invalid_range",
                message=f"자막 시간이 올바르지 않습니다: {line}",
                stage="subtitle_parse",
                retryable=False,
            )
        )
    return start_ts, end_ts


def _normalize_subtitle_timestamp(value: str) -> str:
    try:
        return normalize_timestamp(value)
    except ValueError as exc:
        raise SubtitleParseError(
            ErrorDetail(
                code="subtitle_invalid_timestamp",
                message=f"자막 타임스탬프 형식이 올바르지 않습니다: {value}",
                stage="subtitle_parse",
                retryable=False,
            )
        ) from exc

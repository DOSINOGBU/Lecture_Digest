from __future__ import annotations

from dataclasses import replace

from lecturedigest.errors import ErrorDetail, IndexingError, ValidationError
from lecturedigest.models import LectureRecord, TranscriptChunk, TranscriptSegment
from lecturedigest.timecode import timestamp_to_seconds

DEFAULT_CHUNK_WINDOW_SECONDS = 90
DEFAULT_CHUNK_OVERLAP_SECONDS = 15


def chunk_lecture(
    record: LectureRecord,
    *,
    window_seconds: int = DEFAULT_CHUNK_WINDOW_SECONDS,
    overlap_seconds: int = DEFAULT_CHUNK_OVERLAP_SECONDS,
    chapter: str = "unassigned",
) -> LectureRecord:
    validate_chunk_settings(window_seconds, overlap_seconds)
    if not record.segments:
        raise IndexingError(
            ErrorDetail(
                code="segments_required",
                message="대본 세그먼트가 없어 청크를 생성할 수 없습니다.",
                stage="chunking",
                retryable=False,
            )
        )

    chunks = build_chunks(
        lecture_id=record.lecture_id,
        segments=record.segments,
        window_seconds=window_seconds,
        overlap_seconds=overlap_seconds,
        chapter=chapter,
    )
    return replace(record, status="chunks_ready", stage="chunking", chunks=chunks)


def build_chunks(
    *,
    lecture_id: str,
    segments: list[TranscriptSegment],
    window_seconds: int = DEFAULT_CHUNK_WINDOW_SECONDS,
    overlap_seconds: int = DEFAULT_CHUNK_OVERLAP_SECONDS,
    chapter: str = "unassigned",
) -> list[TranscriptChunk]:
    validate_chunk_settings(window_seconds, overlap_seconds)
    ordered_segments = sorted(segments, key=lambda segment: _timestamp_seconds(segment.start_ts))
    chunks: list[TranscriptChunk] = []
    start_index = 0

    while start_index < len(ordered_segments):
        selected = _select_window(ordered_segments, start_index, window_seconds)
        if not selected:
            break

        chunk = _create_chunk(
            lecture_id=lecture_id,
            chapter=chapter,
            index=len(chunks) + 1,
            segments=selected,
        )
        chunks.append(chunk)
        start_index = _next_start_index(
            ordered_segments=ordered_segments,
            current_start_index=start_index,
            selected_segments=selected,
            overlap_seconds=overlap_seconds,
        )

    return chunks


def validate_chunk_settings(window_seconds: int, overlap_seconds: int) -> None:
    if window_seconds <= 0:
        raise ValidationError(
            ErrorDetail(
                code="chunk_window_invalid",
                message="청크 길이는 1초 이상이어야 합니다.",
                stage="chunking",
                retryable=False,
            )
        )
    if overlap_seconds < 0:
        raise ValidationError(
            ErrorDetail(
                code="chunk_overlap_invalid",
                message="청크 오버랩은 0초 이상이어야 합니다.",
                stage="chunking",
                retryable=False,
            )
        )
    if overlap_seconds >= window_seconds:
        raise ValidationError(
            ErrorDetail(
                code="chunk_overlap_too_large",
                message="청크 오버랩은 청크 길이보다 작아야 합니다.",
                stage="chunking",
                retryable=False,
            )
        )


def _select_window(
    segments: list[TranscriptSegment],
    start_index: int,
    window_seconds: int,
) -> list[TranscriptSegment]:
    first_segment = segments[start_index]
    window_start = _timestamp_seconds(first_segment.start_ts)
    window_end = window_start + window_seconds
    selected: list[TranscriptSegment] = []

    for segment in segments[start_index:]:
        if selected and _timestamp_seconds(segment.start_ts) >= window_end:
            break
        selected.append(segment)
    return selected


def _create_chunk(
    *,
    lecture_id: str,
    chapter: str,
    index: int,
    segments: list[TranscriptSegment],
) -> TranscriptChunk:
    return TranscriptChunk(
        chunk_id=f"chunk-{index:06d}",
        lecture_id=lecture_id,
        chapter=chapter,
        start_ts=segments[0].start_ts,
        end_ts=segments[-1].end_ts,
        text=" ".join(segment.text for segment in segments).strip(),
        segment_ids=[segment.segment_id for segment in segments],
        speaker=_shared_speaker(segments),
        ocr_text=None,
    )


def _shared_speaker(segments: list[TranscriptSegment]) -> str | None:
    speakers = {segment.speaker for segment in segments if segment.speaker}
    if len(speakers) == 1:
        return next(iter(speakers))
    return None


def _next_start_index(
    *,
    ordered_segments: list[TranscriptSegment],
    current_start_index: int,
    selected_segments: list[TranscriptSegment],
    overlap_seconds: int,
) -> int:
    if selected_segments[-1].segment_id == ordered_segments[-1].segment_id:
        return len(ordered_segments)

    selected_end = _timestamp_seconds(selected_segments[-1].end_ts)
    threshold = selected_end - overlap_seconds
    for index in range(current_start_index + 1, len(ordered_segments)):
        if _timestamp_seconds(ordered_segments[index].end_ts) > threshold:
            return index
    return current_start_index + len(selected_segments)


def _timestamp_seconds(value: str) -> float:
    try:
        return timestamp_to_seconds(value)
    except ValueError as exc:
        raise IndexingError(
            ErrorDetail(
                code="segment_timestamp_invalid",
                message=f"세그먼트 타임스탬프 형식이 올바르지 않습니다: {value}",
                stage="chunking",
                retryable=False,
            )
        ) from exc

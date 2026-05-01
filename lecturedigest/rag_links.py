from __future__ import annotations

from lecturedigest.models import LectureRecord
from lecturedigest.timecode import timestamp_to_seconds


def citation_label(record: LectureRecord, chapter: str, start_ts: str) -> str:
    return f"[{record.title} - {chapter} - {display_timestamp(start_ts)}]"


def jump_link(record: LectureRecord, start_ts: str) -> str:
    try:
        seconds = round(timestamp_to_seconds(start_ts))
    except ValueError:
        seconds = 0
    return f"lecturedigest://lecture/{record.lecture_id}?t={seconds}"


def display_timestamp(timestamp: str) -> str:
    try:
        total_seconds = round(timestamp_to_seconds(timestamp))
    except ValueError:
        return timestamp
    minutes, seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"

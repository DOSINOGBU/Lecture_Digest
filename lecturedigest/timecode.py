from __future__ import annotations

import re
from datetime import timedelta

TIMESTAMP_PATTERN = re.compile(
    r"^(?P<hours>\d{1,2}):(?P<minutes>\d{2}):(?P<seconds>\d{2})(?P<fraction>[,.]\d{1,3})?$"
)


def normalize_timestamp(value: str) -> str:
    match = TIMESTAMP_PATTERN.match(value)
    if not match:
        raise ValueError(f"Invalid timestamp: {value}")

    fraction = (match.group("fraction") or ".000").replace(",", ".")
    milliseconds = fraction[1:].ljust(3, "0")[:3]
    return (
        f"{int(match.group('hours')):02d}:"
        f"{int(match.group('minutes')):02d}:"
        f"{int(match.group('seconds')):02d}."
        f"{milliseconds}"
    )


def timestamp_to_seconds(value: str) -> float:
    normalized = normalize_timestamp(value)
    hours, minutes, rest = normalized.split(":")
    seconds, milliseconds = rest.split(".")
    delta = timedelta(
        hours=int(hours),
        minutes=int(minutes),
        seconds=int(seconds),
        milliseconds=int(milliseconds),
    )
    return delta.total_seconds()


def seconds_to_timestamp(seconds_value: float) -> str:
    total_milliseconds = round(seconds_value * 1000)
    milliseconds = total_milliseconds % 1000
    total_seconds = total_milliseconds // 1000
    seconds = total_seconds % 60
    total_minutes = total_seconds // 60
    minutes = total_minutes % 60
    hours = total_minutes // 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"

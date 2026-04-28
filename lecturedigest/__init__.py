"""LectureDigest MVP package."""

from lecturedigest.ingestion import register_lecture
from lecturedigest.models import LectureRecord, ProcessingIssue, TranscriptSegment

__all__ = [
    "LectureRecord",
    "ProcessingIssue",
    "TranscriptSegment",
    "register_lecture",
]

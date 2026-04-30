"""LectureDigest MVP package."""

from lecturedigest.chunking import chunk_lecture
from lecturedigest.ingestion import register_lecture
from lecturedigest.models import (
    LectureRecord,
    ProcessingIssue,
    TranscriptChunk,
    TranscriptSegment,
)
from lecturedigest.transcription import apply_stt_result

__all__ = [
    "LectureRecord",
    "ProcessingIssue",
    "TranscriptChunk",
    "TranscriptSegment",
    "apply_stt_result",
    "chunk_lecture",
    "register_lecture",
]

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ErrorDetail:
    code: str
    message: str
    stage: str
    retryable: bool = False


class LectureDigestError(Exception):
    def __init__(self, detail: ErrorDetail) -> None:
        super().__init__(detail.message)
        self.detail = detail


class ValidationError(LectureDigestError):
    pass


class SubtitleParseError(LectureDigestError):
    pass


class TranscriptionError(LectureDigestError):
    pass


class IndexingError(LectureDigestError):
    pass


class EnrichmentError(LectureDigestError):
    pass


class CorrectionError(LectureDigestError):
    pass


class NoteGenerationError(LectureDigestError):
    pass


class AnkiExportError(LectureDigestError):
    pass


class QuizGenerationError(LectureDigestError):
    pass

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

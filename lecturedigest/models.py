from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class ProcessingIssue:
    code: str
    message: str
    stage: str
    retryable: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class TranscriptSegment:
    segment_id: str
    start_ts: str
    end_ts: str
    text: str
    speaker: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class TranscriptChunk:
    chunk_id: str
    lecture_id: str
    chapter: str
    start_ts: str
    end_ts: str
    text: str
    segment_ids: list[str]
    speaker: str | None = None
    ocr_text: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class LectureRecord:
    lecture_id: str
    title: str
    instructor: str
    category: str
    source_path: str
    subtitle_path: str | None
    status: str
    stage: str
    transcript_source: str
    segments: list[TranscriptSegment] = field(default_factory=list)
    chunks: list[TranscriptChunk] = field(default_factory=list)
    issues: list[ProcessingIssue] = field(default_factory=list)
    created_at: str | None = None
    input_mode: str = "file"
    lecture_title: str | None = None
    major_category: str | None = None
    middle_category: str | None = None
    clip_title: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "lecture_id": self.lecture_id,
            "title": self.title,
            "instructor": self.instructor,
            "category": self.category,
            "source_path": self.source_path,
            "subtitle_path": self.subtitle_path,
            "status": self.status,
            "stage": self.stage,
            "transcript_source": self.transcript_source,
            "segments": [segment.to_dict() for segment in self.segments],
            "chunks": [chunk.to_dict() for chunk in self.chunks],
            "issues": [issue.to_dict() for issue in self.issues],
            "created_at": self.created_at,
            "input_mode": self.input_mode,
            "lecture_title": self.lecture_title,
            "major_category": self.major_category,
            "middle_category": self.middle_category,
            "clip_title": self.clip_title,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "LectureRecord":
        return cls(
            lecture_id=str(payload["lecture_id"]),
            title=str(payload["title"]),
            instructor=str(payload["instructor"]),
            category=str(payload["category"]),
            source_path=str(payload["source_path"]),
            subtitle_path=(
                str(payload["subtitle_path"])
                if payload.get("subtitle_path") is not None
                else None
            ),
            status=str(payload["status"]),
            stage=str(payload["stage"]),
            transcript_source=str(payload["transcript_source"]),
            segments=[
                TranscriptSegment(
                    segment_id=str(segment["segment_id"]),
                    start_ts=str(segment["start_ts"]),
                    end_ts=str(segment["end_ts"]),
                    text=str(segment["text"]),
                    speaker=(
                        str(segment["speaker"])
                        if segment.get("speaker") is not None
                        else None
                    ),
                )
                for segment in _as_dict_list(payload.get("segments", []))
            ],
            chunks=[
                TranscriptChunk(
                    chunk_id=str(chunk["chunk_id"]),
                    lecture_id=str(chunk["lecture_id"]),
                    chapter=str(chunk["chapter"]),
                    start_ts=str(chunk["start_ts"]),
                    end_ts=str(chunk["end_ts"]),
                    text=str(chunk["text"]),
                    segment_ids=[
                        str(segment_id)
                        for segment_id in _as_string_list(chunk.get("segment_ids", []))
                    ],
                    speaker=(
                        str(chunk["speaker"])
                        if chunk.get("speaker") is not None
                        else None
                    ),
                    ocr_text=(
                        str(chunk["ocr_text"])
                        if chunk.get("ocr_text") is not None
                        else None
                    ),
                )
                for chunk in _as_dict_list(payload.get("chunks", []))
            ],
            issues=[
                ProcessingIssue(
                    code=str(issue["code"]),
                    message=str(issue["message"]),
                    stage=str(issue["stage"]),
                    retryable=bool(issue.get("retryable", False)),
                )
                for issue in _as_dict_list(payload.get("issues", []))
            ],
            created_at=(
                str(payload["created_at"])
                if payload.get("created_at") is not None
                else None
            ),
            input_mode=str(payload.get("input_mode", "file")),
            lecture_title=_optional_string(payload.get("lecture_title")),
            major_category=_optional_string(payload.get("major_category")),
            middle_category=_optional_string(payload.get("middle_category")),
            clip_title=_optional_string(payload.get("clip_title")),
        )


def _as_dict_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _as_string_list(value: object) -> list[object]:
    if not isinstance(value, list):
        return []
    return value


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    return str(value)

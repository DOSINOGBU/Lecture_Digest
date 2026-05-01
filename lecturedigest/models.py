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
    ocr_text: str | None = None
    slide_id: str | None = None
    source_frame_ts: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class SlideOcrResult:
    slide_id: str
    source_frame_ts: str
    raw_ocr_text: str
    refined_ocr_text: str
    confidence: float | None = None
    provider_metadata: dict[str, object] = field(default_factory=dict)
    frame_width: int | None = None
    frame_height: int | None = None
    change_score: float | None = None
    status: str = "succeeded"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class CorrectionLogEntry:
    segment_id: str
    start_ts: str
    end_ts: str
    original_text: str
    corrected_text: str
    confidence: float | None = None
    reason: str | None = None
    applied: bool = False
    status: str = "review_required"
    provider_metadata: dict[str, object] = field(default_factory=dict)
    protected_terms: list[str] = field(default_factory=list)
    original_error: str | None = None
    retryable: bool = False
    source: str | None = None

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
    slides: list[SlideOcrResult] = field(default_factory=list)
    correction_log: list[CorrectionLogEntry] = field(default_factory=list)
    transcript_metadata: dict[str, object] = field(default_factory=dict)
    correction_metadata: dict[str, object] = field(default_factory=dict)
    search_index: list[dict[str, object]] = field(default_factory=list)
    summaries: dict[str, object] = field(default_factory=dict)
    rag_metadata: dict[str, object] = field(default_factory=dict)
    note_sections: list[dict[str, object]] = field(default_factory=list)
    note_candidates: list[dict[str, object]] = field(default_factory=list)
    approved_note: dict[str, object] = field(default_factory=dict)
    note_metadata: dict[str, object] = field(default_factory=dict)
    flashcards: list[dict[str, object]] = field(default_factory=list)
    anki_exports: list[dict[str, object]] = field(default_factory=list)
    card_metadata: dict[str, object] = field(default_factory=dict)
    quiz_items: list[dict[str, object]] = field(default_factory=list)
    quiz_metadata: dict[str, object] = field(default_factory=dict)
    pipeline_metadata: dict[str, object] = field(default_factory=dict)
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
            "slides": [slide.to_dict() for slide in self.slides],
            "correction_log": [entry.to_dict() for entry in self.correction_log],
            "transcript_metadata": self.transcript_metadata,
            "correction_metadata": self.correction_metadata,
            "search_index": self.search_index,
            "summaries": self.summaries,
            "rag_metadata": self.rag_metadata,
            "note_sections": self.note_sections,
            "note_candidates": self.note_candidates,
            "approved_note": self.approved_note,
            "note_metadata": self.note_metadata,
            "flashcards": self.flashcards,
            "anki_exports": self.anki_exports,
            "card_metadata": self.card_metadata,
            "quiz_items": self.quiz_items,
            "quiz_metadata": self.quiz_metadata,
            "pipeline_metadata": self.pipeline_metadata,
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
            segments=_segments_from_payload(payload),
            chunks=_chunks_from_payload(payload),
            issues=_issues_from_payload(payload),
            slides=_slides_from_payload(payload),
            correction_log=_correction_log_from_payload(payload),
            transcript_metadata=_as_metadata(payload.get("transcript_metadata", {})),
            correction_metadata=_as_metadata(payload.get("correction_metadata", {})),
            search_index=_as_dict_list(payload.get("search_index", [])),
            summaries=_as_metadata(payload.get("summaries", {})),
            rag_metadata=_as_metadata(payload.get("rag_metadata", {})),
            note_sections=_as_dict_list(payload.get("note_sections", [])),
            note_candidates=_as_dict_list(payload.get("note_candidates", [])),
            approved_note=_as_metadata(payload.get("approved_note", {})),
            note_metadata=_as_metadata(payload.get("note_metadata", {})),
            flashcards=_as_dict_list(payload.get("flashcards", [])),
            anki_exports=_as_dict_list(payload.get("anki_exports", [])),
            card_metadata=_as_metadata(payload.get("card_metadata", {})),
            quiz_items=_as_dict_list(payload.get("quiz_items", [])),
            quiz_metadata=_as_metadata(payload.get("quiz_metadata", {})),
            pipeline_metadata=_as_metadata(payload.get("pipeline_metadata", {})),
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


def _segments_from_payload(payload: dict[str, object]) -> list[TranscriptSegment]:
    return [
        TranscriptSegment(
            segment_id=str(segment["segment_id"]),
            start_ts=str(segment["start_ts"]),
            end_ts=str(segment["end_ts"]),
            text=str(segment["text"]),
            speaker=_optional_string(segment.get("speaker")),
            ocr_text=_optional_string(segment.get("ocr_text")),
            slide_id=_optional_string(segment.get("slide_id")),
            source_frame_ts=_optional_string(segment.get("source_frame_ts")),
        )
        for segment in _as_dict_list(payload.get("segments", []))
    ]


def _chunks_from_payload(payload: dict[str, object]) -> list[TranscriptChunk]:
    return [
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
            speaker=_optional_string(chunk.get("speaker")),
            ocr_text=_optional_string(chunk.get("ocr_text")),
        )
        for chunk in _as_dict_list(payload.get("chunks", []))
    ]


def _issues_from_payload(payload: dict[str, object]) -> list[ProcessingIssue]:
    return [
        ProcessingIssue(
            code=str(issue["code"]),
            message=str(issue["message"]),
            stage=str(issue["stage"]),
            retryable=bool(issue.get("retryable", False)),
        )
        for issue in _as_dict_list(payload.get("issues", []))
    ]


def _slides_from_payload(payload: dict[str, object]) -> list[SlideOcrResult]:
    return [
        SlideOcrResult(
            slide_id=str(slide["slide_id"]),
            source_frame_ts=str(slide["source_frame_ts"]),
            raw_ocr_text=str(slide.get("raw_ocr_text", "")),
            refined_ocr_text=str(slide.get("refined_ocr_text", "")),
            confidence=_optional_float(slide.get("confidence")),
            provider_metadata=_as_metadata(slide.get("provider_metadata", {})),
            frame_width=_optional_int(slide.get("frame_width")),
            frame_height=_optional_int(slide.get("frame_height")),
            change_score=_optional_float(slide.get("change_score")),
            status=str(slide.get("status", "succeeded")),
        )
        for slide in _as_dict_list(payload.get("slides", []))
    ]


def _correction_log_from_payload(
    payload: dict[str, object],
) -> list[CorrectionLogEntry]:
    return [
        CorrectionLogEntry(
            segment_id=str(entry["segment_id"]),
            start_ts=str(entry["start_ts"]),
            end_ts=str(entry["end_ts"]),
            original_text=str(entry.get("original_text", "")),
            corrected_text=str(entry.get("corrected_text", "")),
            confidence=_optional_float(entry.get("confidence")),
            reason=_optional_string(entry.get("reason")),
            applied=bool(entry.get("applied", False)),
            status=str(entry.get("status", "review_required")),
            provider_metadata=_as_metadata(entry.get("provider_metadata", {})),
            protected_terms=[
                str(term)
                for term in _as_string_list(entry.get("protected_terms", []))
            ],
            original_error=_optional_string(entry.get("original_error")),
            retryable=bool(entry.get("retryable", False)),
            source=_optional_string(entry.get("source")),
        )
        for entry in _as_dict_list(payload.get("correction_log", []))
    ]


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


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_metadata(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items()}

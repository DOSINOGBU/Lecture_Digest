from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
from time import perf_counter

from lecturedigest.errors import ErrorDetail, IndexingError, ValidationError
from lecturedigest.models import LectureRecord, TranscriptChunk
from lecturedigest.timecode import timestamp_to_seconds

DEFAULT_EMBEDDING_MODEL = "text-embedding-3-large"
DEFAULT_VECTOR_STORE = "qdrant"
DEFAULT_SUMMARY_MODEL = "local-extractive-v1"
DEFAULT_SUMMARY_PROMPT_VERSION = "summary-v1"
DEFAULT_RAG_PROMPT_VERSION = "rag-cited-answer-v1"
DEFAULT_TOP_K = 3
DEFAULT_MIN_SCORE = 1.0

TOKEN_PATTERN = re.compile(r"[0-9A-Za-z가-힣_]+")
STOPWORDS = {
    "그리고",
    "그래서",
    "하지만",
    "이번",
    "강의",
    "것을",
    "것은",
    "것이",
    "이렇게",
    "저희",
    "여러분",
}


@dataclass(frozen=True)
class RagCitation:
    label: str
    jump_link: str
    chunk_id: str
    start_ts: str
    end_ts: str
    segment_ids: list[str]
    score: float


@dataclass(frozen=True)
class RagAnswer:
    status: str
    answer: str
    citations: list[RagCitation]
    elapsed_ms: int


def build_search_index(
    record: LectureRecord,
    *,
    embedding_model: str = DEFAULT_EMBEDDING_MODEL,
    vector_store: str = DEFAULT_VECTOR_STORE,
) -> LectureRecord:
    _require_text(embedding_model, "embedding_model")
    _require_text(vector_store, "vector_store")
    if not record.chunks:
        raise IndexingError(
            ErrorDetail(
                code="chunks_required",
                message="Transcript chunks are required before building a RAG index.",
                stage="indexing",
                retryable=False,
            )
        )

    entries = [
        _chunk_index_entry(
            record=record,
            chunk=chunk,
            embedding_model=embedding_model,
            vector_store=vector_store,
        )
        for chunk in record.chunks
    ]
    entries.extend(
        _note_index_entry(
            record=record,
            section=section,
            embedding_model=embedding_model,
            vector_store=vector_store,
        )
        for section in record.note_sections
    )
    return replace(
        record,
        status="index_ready",
        stage="indexing",
        search_index=entries,
        rag_metadata={
            "embedding_model": embedding_model,
            "vector_store": vector_store,
            "embedding_status": "pending_external_embedding",
            "search_strategy": "local_lexical_fallback",
            "index_entry_count": len(entries),
        },
    )


def generate_summaries(
    record: LectureRecord,
    *,
    summary_model: str = DEFAULT_SUMMARY_MODEL,
    prompt_version: str = DEFAULT_SUMMARY_PROMPT_VERSION,
) -> LectureRecord:
    _require_text(summary_model, "summary_model")
    _require_text(prompt_version, "prompt_version")
    if not record.chunks:
        raise IndexingError(
            ErrorDetail(
                code="chunks_required",
                message="Transcript chunks are required before generating summaries.",
                stage="summarization",
                retryable=False,
            )
        )

    l1_items = [_l1_summary(record, chunk) for chunk in record.chunks]
    l2_items = _l2_summaries(record, l1_items)
    summaries = {
        "model": summary_model,
        "prompt_version": prompt_version,
        "strategy": "local_extractive",
        "l1": l1_items,
        "l2": l2_items,
        "l3": _l3_summary(record, l1_items, l2_items),
    }
    return replace(
        record,
        status="summaries_ready",
        stage="summarization",
        summaries=summaries,
    )


def answer_question(
    record: LectureRecord,
    *,
    question: str,
    top_k: int = DEFAULT_TOP_K,
    min_score: float = DEFAULT_MIN_SCORE,
) -> RagAnswer:
    started = perf_counter()
    normalized_question = _require_text(question, "question")
    if top_k <= 0:
        raise ValidationError(
            ErrorDetail(
                code="rag_top_k_invalid",
                message="RAG top_k must be at least 1.",
                stage="rag",
                retryable=False,
            )
        )
    if min_score < 0:
        raise ValidationError(
            ErrorDetail(
                code="rag_min_score_invalid",
                message="RAG min_score must be 0 or greater.",
                stage="rag",
                retryable=False,
            )
        )
    if not record.search_index:
        raise IndexingError(
            ErrorDetail(
                code="search_index_required",
                message="Build a RAG index before asking questions.",
                stage="rag",
                retryable=False,
            )
        )

    matches = _search(record, normalized_question, top_k=top_k)
    usable_matches = [match for match in matches if match[0] >= min_score]
    elapsed_ms = round((perf_counter() - started) * 1000)
    if not usable_matches:
        return RagAnswer(
            status="insufficient_evidence",
            answer=(
                "검색 근거가 충분하지 않아 답변을 생성하지 않았습니다. "
                "검색어를 바꾸거나 검색 범위를 넓혀보세요."
            ),
            citations=[],
            elapsed_ms=elapsed_ms,
        )

    citations = [
        _citation_from_entry(record, entry, score)
        for score, entry in usable_matches
    ]
    return RagAnswer(
        status="answered",
        answer=_extractive_answer(usable_matches, citations),
        citations=citations,
        elapsed_ms=elapsed_ms,
    )


def _chunk_index_entry(
    *,
    record: LectureRecord,
    chunk: TranscriptChunk,
    embedding_model: str,
    vector_store: str,
) -> dict[str, object]:
    indexed_text = _indexed_text(chunk.text, chunk.ocr_text)
    payload = {
        "entry_id": f"{chunk.chunk_id}:chunk",
        "kind": "chunk",
        "lecture_id": record.lecture_id,
        "title": record.title,
        "lecture_title": record.lecture_title,
        "major_category": record.major_category,
        "middle_category": record.middle_category,
        "clip_title": record.clip_title,
        "chapter": chunk.chapter,
        "chunk_id": chunk.chunk_id,
        "start_ts": chunk.start_ts,
        "end_ts": chunk.end_ts,
        "speaker": chunk.speaker,
        "segment_ids": chunk.segment_ids,
        "corrected_text": chunk.text,
        "refined_ocr_text": chunk.ocr_text,
        "indexed_text": indexed_text,
        "keywords": _keywords(indexed_text),
    }
    return {
        **payload,
        "embedding_model": embedding_model,
        "vector_store": vector_store,
        "cache_key": _cache_key(payload, embedding_model),
        "embedding_status": "pending_external_embedding",
    }


def _note_index_entry(
    *,
    record: LectureRecord,
    section: dict[str, object],
    embedding_model: str,
    vector_store: str,
) -> dict[str, object]:
    segment_ids = [
        str(segment_id)
        for segment_id in _as_list(section.get("segment_ids", []))
    ]
    indexed_text = str(section.get("text") or section.get("body") or "")
    payload = {
        "entry_id": str(section.get("note_section_id") or section.get("section_id")),
        "kind": "note_section",
        "lecture_id": record.lecture_id,
        "title": record.title,
        "chapter": str(section.get("chapter") or "unassigned"),
        "section_title": str(section.get("title") or ""),
        "start_ts": str(section.get("start_ts") or ""),
        "end_ts": str(section.get("end_ts") or ""),
        "segment_ids": segment_ids,
        "corrected_text": indexed_text,
        "refined_ocr_text": None,
        "indexed_text": indexed_text,
        "keywords": _keywords(indexed_text),
    }
    return {
        **payload,
        "embedding_model": embedding_model,
        "vector_store": vector_store,
        "cache_key": _cache_key(payload, embedding_model),
        "embedding_status": "pending_external_embedding",
    }


def _l1_summary(record: LectureRecord, chunk: TranscriptChunk) -> dict[str, object]:
    return {
        "summary_id": f"l1-{chunk.chunk_id}",
        "lecture_id": record.lecture_id,
        "chunk_id": chunk.chunk_id,
        "chapter": chunk.chapter,
        "start_ts": chunk.start_ts,
        "end_ts": chunk.end_ts,
        "segment_ids": chunk.segment_ids,
        "summary": _snippet(chunk.text, 220),
        "citation": _citation_label(record, chunk.chapter, chunk.start_ts),
    }


def _l2_summaries(
    record: LectureRecord,
    l1_items: list[dict[str, object]],
) -> list[dict[str, object]]:
    chapters = []
    seen = set()
    for item in l1_items:
        chapter = str(item["chapter"])
        if chapter in seen:
            continue
        seen.add(chapter)
        chapters.append(chapter)

    summaries = []
    for chapter in chapters:
        chapter_items = [item for item in l1_items if item["chapter"] == chapter]
        summaries.append(
            {
                "summary_id": f"l2-{len(summaries) + 1:06d}",
                "lecture_id": record.lecture_id,
                "chapter": chapter,
                "start_ts": str(chapter_items[0]["start_ts"]),
                "end_ts": str(chapter_items[-1]["end_ts"]),
                "summary": _snippet(
                    " ".join(str(item["summary"]) for item in chapter_items),
                    360,
                ),
                "source_summary_ids": [
                    str(item["summary_id"]) for item in chapter_items
                ],
                "citations": [str(item["citation"]) for item in chapter_items[:3]],
            }
        )
    return summaries


def _l3_summary(
    record: LectureRecord,
    l1_items: list[dict[str, object]],
    l2_items: list[dict[str, object]],
) -> dict[str, object]:
    combined_l1 = " ".join(str(item["summary"]) for item in l1_items)
    keywords = _keywords(combined_l1)[:5]
    return {
        "lecture_id": record.lecture_id,
        "title": record.title,
        "tldr": _snippet(combined_l1, 420),
        "overview": _snippet(
            " ".join(str(item["summary"]) for item in l2_items),
            600,
        ),
        "learning_goals": [
            f"{keyword} 관련 핵심 흐름을 출처와 함께 설명할 수 있다."
            for keyword in keywords[:3]
        ],
        "source_summary_ids": [str(item["summary_id"]) for item in l2_items],
    }


def _search(
    record: LectureRecord,
    question: str,
    *,
    top_k: int,
) -> list[tuple[float, dict[str, object]]]:
    query_tokens = set(_tokens(question))
    scored = []
    for entry in record.search_index:
        entry_tokens = set(_tokens(str(entry.get("indexed_text", ""))))
        if not entry_tokens:
            continue
        overlap = query_tokens.intersection(entry_tokens)
        score = float(len(overlap))
        if score:
            scored.append((score, entry))
    scored.sort(key=lambda item: (-item[0], str(item[1].get("start_ts", ""))))
    return scored[:top_k]


def _extractive_answer(
    matches: list[tuple[float, dict[str, object]]],
    citations: list[RagCitation],
) -> str:
    lines = ["검색된 원문 근거 기준으로 답변합니다."]
    for (_score, entry), citation in zip(matches, citations):
        text = _snippet(str(entry.get("corrected_text") or ""), 180)
        lines.append(f"- {text} {citation.label}")
    return "\n".join(lines)


def _citation_from_entry(
    record: LectureRecord,
    entry: dict[str, object],
    score: float,
) -> RagCitation:
    chapter = str(entry.get("chapter") or "unassigned")
    start_ts = str(entry.get("start_ts") or "00:00:00.000")
    end_ts = str(entry.get("end_ts") or start_ts)
    return RagCitation(
        label=_citation_label(record, chapter, start_ts),
        jump_link=_jump_link(record, start_ts),
        chunk_id=str(entry.get("chunk_id") or entry.get("entry_id") or ""),
        start_ts=start_ts,
        end_ts=end_ts,
        segment_ids=[
            str(segment_id)
            for segment_id in _as_list(entry.get("segment_ids", []))
        ],
        score=score,
    )


def _citation_label(record: LectureRecord, chapter: str, start_ts: str) -> str:
    return f"[{record.title} - {chapter} - {_display_timestamp(start_ts)}]"


def _display_timestamp(timestamp: str) -> str:
    try:
        total_seconds = round(timestamp_to_seconds(timestamp))
    except ValueError:
        return timestamp
    minutes, seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def _jump_link(record: LectureRecord, start_ts: str) -> str:
    try:
        seconds = round(timestamp_to_seconds(start_ts))
    except ValueError:
        seconds = 0
    return f"lecturedigest://lecture/{record.lecture_id}?t={seconds}"


def _indexed_text(text: str, ocr_text: str | None) -> str:
    if not ocr_text:
        return text
    return f"{text}\n\n{ocr_text}"


def _cache_key(payload: dict[str, object], embedding_model: str) -> str:
    digest = hashlib.sha256(
        json.dumps(
            {"embedding_model": embedding_model, "payload": payload},
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    return f"embedding:{embedding_model}:{digest}"


def _keywords(text: str) -> list[str]:
    seen = set()
    keywords = []
    for token in _tokens(text):
        if token in STOPWORDS or token in seen or len(token) < 2:
            continue
        seen.add(token)
        keywords.append(token)
    return keywords[:20]


def _tokens(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_PATTERN.findall(text)]


def _snippet(text: str, max_chars: int) -> str:
    compact = " ".join(text.split())
    if len(compact) <= max_chars:
        return compact
    trimmed = compact[: max_chars + 1].rsplit(" ", maxsplit=1)[0]
    return f"{trimmed or compact[:max_chars]}..."


def _require_text(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValidationError(
            ErrorDetail(
                code=f"{field_name}_required",
                message=f"{field_name} is required.",
                stage="rag",
                retryable=False,
            )
        )
    return normalized


def _as_list(value: object) -> list[object]:
    if not isinstance(value, list):
        return []
    return value

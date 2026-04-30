from __future__ import annotations

import json
from dataclasses import dataclass, replace

from lecturedigest.errors import ErrorDetail, IndexingError, ValidationError
from lecturedigest.models import LectureRecord, ProcessingIssue
from lecturedigest.openai_client import OpenAIClient, format_dry_run_result, json_body
from lecturedigest.openai_types import (
    OpenAICallMetadata,
    OpenAIClientResult,
    OpenAIRequest,
)
from lecturedigest.rag import DEFAULT_EMBEDDING_MODEL
from lecturedigest.rag_vector import (
    attach_embedding,
    mark_embedding_failed,
    needs_embedding,
)

OPENAI_EMBEDDINGS_ENDPOINT = "/v1/embeddings"
OPENAI_EMBEDDINGS_USE_CASE = "rag_embedding"
OPENAI_EMBEDDINGS_PROMPT_VERSION = "embedding-v1"
EMBEDDING_STAGE = "indexing"


@dataclass(frozen=True)
class OpenAIEmbeddingIndexResult:
    record: LectureRecord
    client_result: OpenAIClientResult
    requested_entry_count: int
    dry_run: bool = False

    @property
    def failed_request_count(self) -> int:
        if self.client_result.metadata.status in {"succeeded", "dry_run", "skipped"}:
            return 0
        return 1


@dataclass(frozen=True)
class OpenAIQueryEmbeddingResult:
    embedding: list[float]
    client_result: OpenAIClientResult
    dry_run: bool = False


def embed_search_index_with_openai(
    record: LectureRecord,
    *,
    client: OpenAIClient | None = None,
    model: str = DEFAULT_EMBEDDING_MODEL,
    force: bool = False,
    dry_run: bool = False,
) -> OpenAIEmbeddingIndexResult:
    if not record.search_index:
        raise IndexingError(
            ErrorDetail(
                code="search_index_required",
                message="Build a RAG index before embedding search entries.",
                stage=EMBEDDING_STAGE,
                retryable=False,
            )
    )

    targets = [entry for entry in record.search_index if needs_embedding(entry, force=force)]
    if not targets:
        return OpenAIEmbeddingIndexResult(
            record=record,
            client_result=_skipped_result(model),
            requested_entry_count=0,
            dry_run=dry_run,
        )
    request = build_embedding_request(
        [str(entry.get("indexed_text") or "") for entry in targets],
        model=model,
    )
    openai_client = client or OpenAIClient()
    result = openai_client.send(request, dry_run=dry_run)
    if dry_run:
        return OpenAIEmbeddingIndexResult(
            record=record,
            client_result=result,
            requested_entry_count=len(targets),
            dry_run=True,
        )
    if not result.succeeded:
        return OpenAIEmbeddingIndexResult(
            record=_record_with_failed_embeddings(record, targets, result),
            client_result=result,
            requested_entry_count=len(targets),
            dry_run=False,
        )

    vectors = parse_embedding_response(result.body, expected_count=len(targets))
    updated_entries = _entries_with_embeddings(record.search_index, targets, vectors, result)
    return OpenAIEmbeddingIndexResult(
        record=replace(
            record,
            status="index_ready",
            stage="indexing",
            search_index=updated_entries,
            rag_metadata={
                **record.rag_metadata,
                "embedding_model": model,
                "embedding_status": "ready",
                "embedding_entry_count": len(targets),
                "last_embedding_call": result.metadata.to_dict(),
            },
        ),
        client_result=result,
        requested_entry_count=len(targets),
        dry_run=False,
    )


def embed_query_with_openai(
    question: str,
    *,
    client: OpenAIClient | None = None,
    model: str = DEFAULT_EMBEDDING_MODEL,
    dry_run: bool = False,
) -> OpenAIQueryEmbeddingResult:
    normalized_question = question.strip()
    if not normalized_question:
        raise ValidationError(
            ErrorDetail(
                code="question_required",
                message="question is required.",
                stage="rag",
                retryable=False,
            )
        )
    request = build_embedding_request([normalized_question], model=model)
    openai_client = client or OpenAIClient()
    result = openai_client.send(request, dry_run=dry_run)
    if dry_run:
        return OpenAIQueryEmbeddingResult(
            embedding=[],
            client_result=result,
            dry_run=True,
        )
    if not result.succeeded:
        issue = result.to_processing_issue(stage="rag")
        raise IndexingError(
            ErrorDetail(
                code=issue.code if issue else "openai_embedding_failed",
                message=issue.message if issue else "OpenAI query embedding failed.",
                stage="rag",
                retryable=issue.retryable if issue else False,
            )
        )
    embedding = parse_embedding_response(result.body, expected_count=1)[0]
    return OpenAIQueryEmbeddingResult(
        embedding=embedding,
        client_result=result,
        dry_run=False,
    )


def build_embedding_request(
    texts: list[str],
    *,
    model: str = DEFAULT_EMBEDDING_MODEL,
) -> OpenAIRequest:
    normalized_texts = [text for text in texts if text.strip()]
    if not normalized_texts:
        normalized_texts = ["No text requires embedding."]
    body = json_body({"model": model, "input": normalized_texts})
    return OpenAIRequest(
        endpoint=OPENAI_EMBEDDINGS_ENDPOINT,
        use_case=OPENAI_EMBEDDINGS_USE_CASE,
        model=model,
        prompt_version=OPENAI_EMBEDDINGS_PROMPT_VERSION,
        body=body,
        input_size_bytes=len(body),
        external_data_boundary="indexed transcript and note text to OpenAI Embeddings API",
    )


def parse_embedding_response(
    data: bytes | str,
    *,
    expected_count: int,
) -> list[list[float]]:
    payload = _decode_json(data)
    raw_data = payload.get("data")
    if not isinstance(raw_data, list):
        raise _embedding_error(
            "embedding_response_malformed",
            "Embedding response `data` must be a list.",
        )
    vectors_by_index: dict[int, list[float]] = {}
    for item in raw_data:
        if not isinstance(item, dict):
            continue
        index = _optional_int(item.get("index"))
        vector = _embedding_vector(item.get("embedding"))
        if index is None or vector is None:
            raise _embedding_error(
                "embedding_response_malformed",
                "Embedding response items must include index and embedding vector.",
            )
        vectors_by_index[index] = vector
    if sorted(vectors_by_index) != list(range(expected_count)):
        raise _embedding_error(
            "embedding_response_count_mismatch",
            "Embedding response count did not match requested input count.",
        )
    vectors = [vectors_by_index[index] for index in range(expected_count)]
    return vectors


def format_embedding_dry_run(result: OpenAIEmbeddingIndexResult) -> str:
    return "\n".join(
        [
            format_dry_run_result(result.client_result),
            (
                "[LectureIndexing] embedding dry-run "
                f"{{ entries={result.requested_entry_count}; "
                "externalDataBoundary=indexed transcript and note text to "
                "OpenAI Embeddings API; willUpload=false; willSave=false }}"
            ),
        ]
    )


def format_query_embedding_dry_run(result: OpenAIQueryEmbeddingResult) -> str:
    return "\n".join(
        [
            format_dry_run_result(result.client_result),
            (
                "[LectureRAG] query-embedding dry-run "
                "{ externalDataBoundary=question text to OpenAI Embeddings API; "
                "willUpload=false; willSave=false }"
            ),
        ]
    )


def _entries_with_embeddings(
    entries: list[dict[str, object]],
    targets: list[dict[str, object]],
    vectors: list[list[float]],
    result: OpenAIClientResult,
) -> list[dict[str, object]]:
    vector_by_entry_id = {
        str(entry.get("entry_id")): vector
        for entry, vector in zip(targets, vectors)
    }
    updated = []
    for entry in entries:
        vector = vector_by_entry_id.get(str(entry.get("entry_id")))
        if vector is None:
            updated.append(entry)
            continue
        updated.append(
            attach_embedding(
                entry,
                vector,
                metadata={"openai_call": result.metadata.to_dict()},
            )
        )
    return updated


def _skipped_result(model: str) -> OpenAIClientResult:
    return OpenAIClientResult(
        metadata=OpenAICallMetadata(
            provider="openai",
            endpoint=OPENAI_EMBEDDINGS_ENDPOINT,
            use_case=OPENAI_EMBEDDINGS_USE_CASE,
            model=model,
            prompt_version=OPENAI_EMBEDDINGS_PROMPT_VERSION,
            input_size_bytes=0,
            duration_ms=0,
            status="skipped",
            retryable=False,
            estimated_cost="unknown",
            external_data_boundary=(
                "indexed transcript and note text to OpenAI Embeddings API"
            ),
        )
    )


def _record_with_failed_embeddings(
    record: LectureRecord,
    targets: list[dict[str, object]],
    result: OpenAIClientResult,
) -> LectureRecord:
    target_ids = {str(entry.get("entry_id")) for entry in targets}
    updated_entries = [
        (
            mark_embedding_failed(
                entry,
                metadata={"openai_call": result.metadata.to_dict()},
                error_code=result.error_code or "openai_embedding_failed",
            )
            if str(entry.get("entry_id")) in target_ids
            else entry
        )
        for entry in record.search_index
    ]
    issue = result.to_processing_issue(stage="indexing") or ProcessingIssue(
        code="openai_embedding_failed",
        message="OpenAI embedding request failed.",
        stage="indexing",
        retryable=result.metadata.retryable,
    )
    return replace(
        record,
        status="embedding_failed",
        stage="indexing",
        search_index=updated_entries,
        issues=[*record.issues, issue],
        rag_metadata={
            **record.rag_metadata,
            "embedding_status": "failed",
            "last_embedding_call": result.metadata.to_dict(),
        },
    )


def _decode_json(data: bytes | str) -> dict[str, object]:
    text = data.decode("utf-8", errors="replace") if isinstance(data, bytes) else data
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise _embedding_error(
            "embedding_response_invalid_json",
            f"Embedding response JSON could not be parsed: {exc.msg}",
        ) from exc
    if not isinstance(payload, dict):
        raise _embedding_error(
            "embedding_response_malformed",
            "Embedding response must be a JSON object.",
        )
    return payload


def _embedding_vector(value: object) -> list[float] | None:
    if not isinstance(value, list) or not value:
        return None
    vector = []
    for item in value:
        try:
            vector.append(float(item))
        except (TypeError, ValueError):
            return None
    return vector


def _optional_int(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _embedding_error(code: str, message: str) -> IndexingError:
    return IndexingError(
        ErrorDetail(
            code=code,
            message=message,
            stage=EMBEDDING_STAGE,
            retryable=False,
        )
    )

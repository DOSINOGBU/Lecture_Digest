from __future__ import annotations

import hashlib
import math
from copy import deepcopy

EMBEDDING_STATUS_READY = "ready"
EMBEDDING_STATUS_PENDING = "pending_external_embedding"
EMBEDDING_STATUS_STALE = "stale"
VECTOR_SCORE_SCALE = 10.0


def source_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def merge_embedding_cache(
    entries: list[dict[str, object]],
    previous_entries: list[dict[str, object]],
) -> list[dict[str, object]]:
    previous_by_id = {
        str(entry.get("entry_id")): entry
        for entry in previous_entries
        if entry.get("entry_id") is not None
    }
    merged = []
    for entry in entries:
        previous = previous_by_id.get(str(entry.get("entry_id")))
        if previous is None:
            merged.append(entry)
            continue
        merged.append(_merge_entry_cache(entry, previous))
    return merged


def vector_search(
    entries: list[dict[str, object]],
    query_embedding: list[float],
    *,
    top_k: int,
) -> list[tuple[float, dict[str, object]]]:
    scored = []
    for entry in entries:
        vector = _embedding_vector(entry)
        if vector is None:
            continue
        similarity = _cosine_similarity(query_embedding, vector)
        if similarity <= 0:
            continue
        scored.append((similarity * VECTOR_SCORE_SCALE, entry))
    scored.sort(key=lambda item: (-item[0], str(item[1].get("start_ts", ""))))
    return scored[:top_k]


def has_ready_embeddings(entries: list[dict[str, object]]) -> bool:
    return any(_embedding_vector(entry) is not None for entry in entries)


def needs_embedding(entry: dict[str, object], *, force: bool = False) -> bool:
    status = str(entry.get("embedding_status") or "")
    if force:
        return bool(str(entry.get("indexed_text") or "").strip())
    if status == EMBEDDING_STATUS_STALE:
        return False
    if status == EMBEDDING_STATUS_READY and _embedding_vector(entry) is not None:
        return False
    return bool(str(entry.get("indexed_text") or "").strip())


def attach_embedding(
    entry: dict[str, object],
    embedding: list[float],
    *,
    metadata: dict[str, object],
) -> dict[str, object]:
    updated = deepcopy(entry)
    updated["embedding_vector"] = embedding
    updated["embedding_status"] = EMBEDDING_STATUS_READY
    updated["embedding_metadata"] = metadata
    updated.pop("stale_reason", None)
    return updated


def mark_embedding_failed(
    entry: dict[str, object],
    *,
    metadata: dict[str, object],
    error_code: str,
) -> dict[str, object]:
    updated = deepcopy(entry)
    updated["embedding_status"] = "failed"
    updated["embedding_metadata"] = metadata
    updated["embedding_error_code"] = error_code
    return updated


def _merge_entry_cache(
    entry: dict[str, object],
    previous: dict[str, object],
) -> dict[str, object]:
    if _can_reuse_embedding(entry, previous):
        return {
            **entry,
            "embedding_vector": deepcopy(previous.get("embedding_vector")),
            "embedding_status": EMBEDDING_STATUS_READY,
            "embedding_metadata": deepcopy(previous.get("embedding_metadata", {})),
        }
    if previous.get("embedding_vector") is None:
        return entry
    return {
        **entry,
        "embedding_status": EMBEDDING_STATUS_STALE,
        "stale_reason": "embedding_model_or_source_hash_changed",
        "previous_embedding_model": previous.get("embedding_model"),
        "previous_source_hash": previous.get("source_hash"),
    }


def _can_reuse_embedding(
    entry: dict[str, object],
    previous: dict[str, object],
) -> bool:
    return (
        previous.get("embedding_status") == EMBEDDING_STATUS_READY
        and previous.get("embedding_vector") is not None
        and previous.get("embedding_model") == entry.get("embedding_model")
        and previous.get("source_hash") == entry.get("source_hash")
    )


def _embedding_vector(entry: dict[str, object]) -> list[float] | None:
    if entry.get("embedding_status") != EMBEDDING_STATUS_READY:
        return None
    value = entry.get("embedding_vector")
    if not isinstance(value, list):
        return None
    vector = []
    for item in value:
        try:
            vector.append(float(item))
        except (TypeError, ValueError):
            return None
    return vector if vector else None


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    dot_product = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot_product / (left_norm * right_norm)

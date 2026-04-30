from __future__ import annotations

import re
from dataclasses import dataclass

from lecturedigest.rag_vector import has_ready_embeddings, vector_search

TOKEN_PATTERN = re.compile(r"[0-9A-Za-z가-힣_]+")


@dataclass(frozen=True)
class SearchResult:
    matches: list[tuple[float, dict[str, object]]]
    strategy: str


def search_entries(
    entries: list[dict[str, object]],
    question: str,
    *,
    top_k: int,
    min_score: float,
    query_embedding: list[float] | None,
) -> SearchResult:
    if query_embedding is not None and has_ready_embeddings(entries):
        vector_matches = vector_search(entries, query_embedding, top_k=top_k)
        if any(score >= min_score for score, _entry in vector_matches):
            return SearchResult(matches=vector_matches, strategy="vector")

    lexical_matches = lexical_search(entries, question, top_k=top_k)
    if query_embedding is not None:
        return SearchResult(matches=lexical_matches, strategy="lexical_fallback")
    return SearchResult(matches=lexical_matches, strategy="local_lexical_fallback")


def lexical_search(
    entries: list[dict[str, object]],
    question: str,
    *,
    top_k: int,
) -> list[tuple[float, dict[str, object]]]:
    query_tokens = set(tokens(question))
    scored = []
    for entry in entries:
        entry_tokens = set(tokens(str(entry.get("indexed_text", ""))))
        if not entry_tokens:
            continue
        overlap = query_tokens.intersection(entry_tokens)
        score = float(len(overlap))
        if score:
            scored.append((score, entry))
    scored.sort(key=lambda item: (-item[0], str(item[1].get("start_ts", ""))))
    return scored[:top_k]


def score_metadata(
    matches: list[tuple[float, dict[str, object]]],
    min_score: float,
    search_strategy: str,
) -> dict[str, object]:
    return {
        "search_strategy": search_strategy,
        "min_score": min_score,
        "scores": [
            {
                "entry_id": str(entry.get("entry_id") or ""),
                "kind": str(entry.get("kind") or ""),
                "score": score,
                "embedding_status": str(entry.get("embedding_status") or ""),
            }
            for score, entry in matches
        ],
    }


def tokens(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_PATTERN.findall(text)]

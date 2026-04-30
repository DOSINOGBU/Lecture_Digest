from __future__ import annotations

import argparse

from lecturedigest.errors import ErrorDetail, ValidationError
from lecturedigest.rag import (
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_MIN_SCORE,
    DEFAULT_SUMMARY_MODEL,
    DEFAULT_SUMMARY_PROMPT_VERSION,
    DEFAULT_TOP_K,
    DEFAULT_VECTOR_STORE,
    RagAnswer,
    answer_question,
    build_search_index,
    generate_summaries,
)
from lecturedigest.storage import JsonLectureRepository


def index_command(
    args: argparse.Namespace,
    repository: JsonLectureRepository,
) -> int:
    record = _load_record(args.lecture_id, repository, stage="indexing")
    if record is None:
        return 0

    print(
        "[LectureIndexing] index start "
        f"{{ lectureId={args.lecture_id}; embeddingModel={args.embedding_model}; "
        f"vectorStore={args.vector_store} }}"
    )
    updated = build_search_index(
        record,
        embedding_model=args.embedding_model,
        vector_store=args.vector_store,
    )
    repository.save(updated)
    print(
        "[LectureIndexing] index success "
        f"{{ lectureId={updated.lecture_id}; status={updated.status}; "
        f"stage={updated.stage}; entries={len(updated.search_index)}; "
        "embeddingStatus=pending_external_embedding }}"
    )
    return 0


def summarize_command(
    args: argparse.Namespace,
    repository: JsonLectureRepository,
) -> int:
    record = _load_record(args.lecture_id, repository, stage="summarization")
    if record is None:
        return 0

    print(
        "[LectureSummary] summarize start "
        f"{{ lectureId={args.lecture_id}; summaryModel={args.summary_model}; "
        f"promptVersion={args.prompt_version} }}"
    )
    updated = generate_summaries(
        record,
        summary_model=args.summary_model,
        prompt_version=args.prompt_version,
    )
    repository.save(updated)
    print(
        "[LectureSummary] summarize success "
        f"{{ lectureId={updated.lecture_id}; status={updated.status}; "
        f"stage={updated.stage}; l1={len(updated.summaries.get('l1', []))}; "
        f"l2={len(updated.summaries.get('l2', []))}; l3=1 }}"
    )
    return 0


def ask_command(
    args: argparse.Namespace,
    repository: JsonLectureRepository,
) -> int:
    record = _load_record(args.lecture_id, repository, stage="rag")
    if record is None:
        return 0

    print(
        "[LectureRAG] ask start "
        f"{{ lectureId={args.lecture_id}; topK={args.top_k}; "
        f"minScore={args.min_score} }}"
    )
    answer = answer_question(
        record,
        question=args.question,
        top_k=args.top_k,
        min_score=args.min_score,
    )
    print(format_rag_answer(answer))
    return 0


def add_rag_parsers(subparsers: argparse._SubParsersAction) -> None:
    index_parser = subparsers.add_parser("index")
    index_parser.add_argument("--lecture-id", required=True)
    index_parser.add_argument("--embedding-model", default=DEFAULT_EMBEDDING_MODEL)
    index_parser.add_argument("--vector-store", default=DEFAULT_VECTOR_STORE)

    summarize_parser = subparsers.add_parser("summarize")
    summarize_parser.add_argument("--lecture-id", required=True)
    summarize_parser.add_argument("--summary-model", default=DEFAULT_SUMMARY_MODEL)
    summarize_parser.add_argument(
        "--prompt-version",
        default=DEFAULT_SUMMARY_PROMPT_VERSION,
    )

    ask_parser = subparsers.add_parser("ask")
    ask_parser.add_argument("--lecture-id", required=True)
    ask_parser.add_argument("--question", required=True)
    ask_parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    ask_parser.add_argument("--min-score", type=float, default=DEFAULT_MIN_SCORE)


def format_rag_answer(answer: RagAnswer) -> str:
    citation_count = len(answer.citations)
    header = (
        "[LectureRAG] ask "
        f"{answer.status} {{ citations={citation_count}; "
        f"durationMs={answer.elapsed_ms} }}"
    )
    if not answer.citations:
        return f"{header}\n{answer.answer}"

    citation_lines = [
        f"- {citation.label} {citation.jump_link}"
        for citation in answer.citations
    ]
    return f"{header}\n{answer.answer}\n\nCitations:\n" + "\n".join(citation_lines)


def _load_record(
    lecture_id: str,
    repository: JsonLectureRepository,
    *,
    stage: str,
):
    lectures = repository.list_lectures()
    if not lectures:
        print("No lectures registered yet. Add one with `register`.")
        return None

    record = repository.get_lecture(lecture_id)
    if record is None:
        raise ValidationError(
            ErrorDetail(
                code="lecture_not_found",
                message=f"Lecture not found: {lecture_id}",
                stage=stage,
                retryable=False,
            )
        )
    return record

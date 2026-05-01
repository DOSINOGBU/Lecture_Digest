from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any

from lecturedigest.errors import ErrorDetail, LectureDigestError, ValidationError
from lecturedigest.models import LectureRecord, ProcessingIssue
from lecturedigest.note_generation import approve_note_candidate
from lecturedigest.note_quality import inspect_note_quality
from lecturedigest.openai_client import load_openai_api_key
from lecturedigest.auto_pipeline_steps import (
    cards_step,
    chunk_step,
    correct_step,
    index_step,
    notes_step,
    ocr_step,
    quizzes_step,
    transcribe_step,
)
from lecturedigest.storage import JsonLectureRepository

AUTO_PIPELINE_STAGE = "auto_pipeline"
AUTO_PIPELINE_STEPS = [
    "transcribe",
    "ocr",
    "finalize_transcript",
    "chunk",
    "index",
    "generate_notes",
    "auto_approve_note",
    "generate_cards",
    "generate_quizzes",
]


@dataclass(frozen=True)
class AutoPipelineOptions:
    openai: bool = True
    include_ocr: bool = False
    resume: bool = False
    dry_run: bool = False
    time_budget_seconds: float | None = None
    note_candidate_count: int = 3


@dataclass(frozen=True)
class AutoPipelineResult:
    record: LectureRecord
    steps: list[dict[str, object]]
    status: str
    dry_run: bool = False


@dataclass(frozen=True)
class AutoPipelineDependencies:
    require_api_key: Callable[[], str] = load_openai_api_key
    transcribe: Callable[[LectureRecord, AutoPipelineOptions], LectureRecord] = field(
        default_factory=lambda: transcribe_step
    )
    ocr: Callable[[LectureRecord, AutoPipelineOptions], LectureRecord] = field(
        default_factory=lambda: ocr_step
    )
    correct: Callable[[LectureRecord, AutoPipelineOptions], LectureRecord] = field(
        default_factory=lambda: correct_step
    )
    chunk: Callable[[LectureRecord, AutoPipelineOptions], LectureRecord] = field(
        default_factory=lambda: chunk_step
    )
    index: Callable[[LectureRecord, AutoPipelineOptions], LectureRecord] = field(
        default_factory=lambda: index_step
    )
    generate_notes: Callable[[LectureRecord, AutoPipelineOptions, Callable[[LectureRecord], None]], LectureRecord] = field(
        default_factory=lambda: notes_step
    )
    generate_cards: Callable[[LectureRecord, AutoPipelineOptions, Callable[[LectureRecord], None]], LectureRecord] = field(
        default_factory=lambda: cards_step
    )
    generate_quizzes: Callable[[LectureRecord, AutoPipelineOptions, Callable[[LectureRecord], None]], LectureRecord] = field(
        default_factory=lambda: quizzes_step
    )


def process_lecture_with_auto_ai(
    repository: JsonLectureRepository,
    *,
    lecture_id: str,
    options: AutoPipelineOptions | None = None,
    dependencies: AutoPipelineDependencies | None = None,
) -> AutoPipelineResult:
    opts = options or AutoPipelineOptions()
    deps = dependencies or AutoPipelineDependencies()
    record = _require_record(repository, lecture_id)
    try:
        _validate_start(record, opts)
    except LectureDigestError as exc:
        if not opts.dry_run:
            repository.save(_record_failed_step(record, "preflight", exc))
        raise
    steps = planned_auto_pipeline_steps(record, include_ocr=opts.include_ocr)

    if opts.dry_run:
        return AutoPipelineResult(
            record=record,
            steps=[_planned_step(step) for step in steps],
            status="dry_run",
            dry_run=True,
        )

    deps.require_api_key()
    started = time.perf_counter()
    record = _with_pipeline_metadata(
        record,
        status="running",
        current_step=steps[0] if steps else "",
        completed_steps=_completed_steps(record) if opts.resume else [],
        time_budget_seconds=opts.time_budget_seconds,
        time_budget_exhausted=False,
    )
    repository.save(record)

    executed: list[dict[str, object]] = []
    for step in steps:
        if opts.resume and step in _completed_steps(record):
            executed.append({"step": step, "status": "skipped"})
            continue
        if _time_budget_exhausted(started, opts.time_budget_seconds):
            record = _with_pipeline_metadata(
                record,
                status="partial",
                current_step=step,
                completed_steps=_completed_steps(record),
                time_budget_seconds=opts.time_budget_seconds,
                time_budget_exhausted=True,
            )
            repository.save(record)
            executed.append({"step": step, "status": "pending_time_budget"})
            return AutoPipelineResult(record=record, steps=executed, status="partial")
        try:
            record = _run_step(step, record, opts, deps, repository.save)
        except Exception as exc:
            record = _record_failed_step(record, step, exc)
            repository.save(record)
            raise
        completed = [*_completed_steps(record), step]
        record = _with_pipeline_metadata(
            record,
            status="running",
            current_step=step,
            completed_steps=_unique(completed),
            time_budget_seconds=opts.time_budget_seconds,
            time_budget_exhausted=False,
        )
        repository.save(record)
        executed.append({"step": step, "status": "completed"})

    record = _with_pipeline_metadata(
        record,
        status="completed",
        current_step="",
        completed_steps=_completed_steps(record),
        time_budget_seconds=opts.time_budget_seconds,
        time_budget_exhausted=False,
        finished_at=_now(),
    )
    repository.save(record)
    return AutoPipelineResult(record=record, steps=executed, status="completed")


def planned_auto_pipeline_steps(record: LectureRecord, *, include_ocr: bool) -> list[str]:
    _validate_record_can_process(record)
    steps: list[str] = []
    if not record.segments and record.transcript_source == "stt_pending":
        steps.append("transcribe")
    if include_ocr:
        steps.append("ocr")
    steps.extend(
        [
            "finalize_transcript",
            "chunk",
            "index",
            "generate_notes",
            "auto_approve_note",
            "generate_cards",
            "generate_quizzes",
        ]
    )
    return steps


def select_best_note_candidate(record: LectureRecord) -> str:
    result = inspect_note_quality(record)
    ranked = sorted(
        (
            item
            for item in _dict_list(result.get("items"))
            if item.get("gate_status") in {"review_ready", "needs_review"}
        ),
        key=_note_quality_rank,
    )
    if not ranked:
        raise ValidationError(
            ErrorDetail(
                code="auto_note_candidate_blocked",
                message="No non-blocked note candidate is available for auto approval.",
                stage=AUTO_PIPELINE_STAGE,
                retryable=False,
            )
        )
    return str(ranked[0].get("candidate_id") or "")


def auto_approve_best_note_candidate(record: LectureRecord) -> LectureRecord:
    candidate_id = select_best_note_candidate(record)
    approved = approve_note_candidate(record, candidate_id=candidate_id)
    quality = inspect_note_quality(approved, candidate_id=candidate_id)
    item = _dict_list(quality.get("items"))[0]
    return replace(
        approved,
        approved_note={
            **approved.approved_note,
            "approval_mode": "auto_best_candidate",
            "auto_quality_gate": item.get("gate_status"),
            "auto_quality_warnings": item.get("warnings", []),
        },
        note_metadata={
            **approved.note_metadata,
            "approval_mode": "auto_best_candidate",
            "auto_quality_gate": item.get("gate_status"),
            "auto_quality_warnings": item.get("warnings", []),
        },
    )


def format_auto_pipeline_result(result: AutoPipelineResult) -> str:
    lines = [
        "[LecturePipeline] process-lecture "
        f"{result.status} {{ lectureId={result.record.lecture_id}; "
        f"dryRun={result.dry_run}; steps={len(result.steps)} }}"
    ]
    for step in result.steps:
        lines.append(f"- {step.get('step')} status={step.get('status')}")
    return "\n".join(lines)


def _run_step(
    step: str,
    record: LectureRecord,
    options: AutoPipelineOptions,
    deps: AutoPipelineDependencies,
    checkpoint: Callable[[LectureRecord], None],
) -> LectureRecord:
    if step == "transcribe":
        return deps.transcribe(record, options)
    if step == "ocr":
        return deps.ocr(record, options)
    if step == "finalize_transcript":
        return deps.correct(record, options)
    if step == "chunk":
        return deps.chunk(record, options)
    if step == "index":
        return deps.index(record, options)
    if step == "generate_notes":
        return deps.generate_notes(record, options, checkpoint)
    if step == "auto_approve_note":
        return auto_approve_best_note_candidate(record)
    if step == "generate_cards":
        return deps.generate_cards(record, options, checkpoint)
    if step == "generate_quizzes":
        return deps.generate_quizzes(record, options, checkpoint)
    raise ValidationError(
        ErrorDetail(
            code="auto_pipeline_step_unknown",
            message=f"Unknown auto pipeline step: {step}",
            stage=AUTO_PIPELINE_STAGE,
            retryable=False,
        )
    )


def _validate_start(record: LectureRecord, options: AutoPipelineOptions) -> None:
    if not options.openai:
        raise ValidationError(
            ErrorDetail(
                code="openai_required_for_auto_pipeline",
                message="Auto AI pipeline requires --openai.",
                stage=AUTO_PIPELINE_STAGE,
                retryable=False,
            )
        )
    _validate_record_can_process(record)


def _validate_record_can_process(record: LectureRecord) -> None:
    if record.transcript_source == "subtitle_unmatched" or record.status == "subtitle_unmatched":
        raise ValidationError(
            ErrorDetail(
                code="subtitle_unmatched_auto_ai_blocked",
                message="Auto AI pipeline will not route subtitle_unmatched clips to STT.",
                stage=AUTO_PIPELINE_STAGE,
                retryable=False,
            )
        )
    if not record.segments and record.transcript_source != "stt_pending":
        raise ValidationError(
            ErrorDetail(
                code="segments_or_stt_required",
                message="Auto AI pipeline requires transcript segments or stt_pending source.",
                stage=AUTO_PIPELINE_STAGE,
                retryable=False,
            )
        )


def _record_failed_step(record: LectureRecord, step: str, exc: Exception) -> LectureRecord:
    retryable = False
    code = exc.__class__.__name__
    message = str(exc)
    if isinstance(exc, LectureDigestError):
        code = exc.detail.code
        message = exc.detail.message
        retryable = exc.detail.retryable
    issue = ProcessingIssue(
        code=code,
        message=message,
        stage=AUTO_PIPELINE_STAGE,
        retryable=retryable,
    )
    return replace(
        _with_pipeline_metadata(
            record,
            status="failed",
            current_step=step,
            completed_steps=_completed_steps(record),
            failed_step=step,
            failure={"code": code, "message": message, "retryable": retryable},
        ),
        issues=[*record.issues, issue],
    )


def _with_pipeline_metadata(
    record: LectureRecord,
    *,
    status: str,
    current_step: str,
    completed_steps: list[str],
    time_budget_seconds: float | None = None,
    time_budget_exhausted: bool = False,
    failed_step: str = "",
    failure: dict[str, object] | None = None,
    finished_at: str | None = None,
) -> LectureRecord:
    metadata = {
        **record.pipeline_metadata,
        "status": status,
        "started_at": record.pipeline_metadata.get("started_at") or _now(),
        "finished_at": finished_at or record.pipeline_metadata.get("finished_at") or "",
        "current_step": current_step,
        "completed_steps": completed_steps,
        "failed_step": failed_step,
        "resume_supported": True,
        "time_budget_seconds": time_budget_seconds,
        "time_budget_exhausted": time_budget_exhausted,
    }
    if failure is not None:
        metadata["failure"] = failure
    elif status in {"running", "completed", "partial"}:
        metadata.pop("failure", None)
    return replace(record, pipeline_metadata=metadata)


def _note_quality_rank(item: dict[str, object]) -> tuple[int, int, int, float, float]:
    gate_order = 0 if item.get("gate_status") == "review_ready" else 1
    warnings = len(_list(item.get("warnings")))
    acronym_gap = int(item.get("acronym_metadata_gap_count") or 0)
    expected = max(1, int(item.get("expected_difficult_concept_count") or 0))
    difficulty = int(item.get("difficulty_explanation_count") or 0)
    coverage = float(item.get("source_coverage_ratio") or 0.0)
    return (gate_order, warnings, acronym_gap, -(difficulty / expected), -coverage)


def _planned_step(step: str) -> dict[str, object]:
    return {"step": step, "status": "planned", "external_data_boundary": _boundary(step)}


def _boundary(step: str) -> str:
    boundaries = {
        "transcribe": "lecture audio/video to OpenAI transcription API",
        "ocr": "representative frame images to OpenAI Vision OCR API",
        "finalize_transcript": "transcript segments to OpenAI Responses API",
        "index": "chunk text and approved note text to OpenAI embeddings API",
        "generate_notes": "corrected transcript and OCR text to OpenAI Responses API",
        "generate_cards": "approved note sections and source snippets to OpenAI Responses API",
        "generate_quizzes": "approved note, ready cards, and source snippets to OpenAI Responses API",
    }
    return boundaries.get(step, "local metadata only")


def _require_record(repository: JsonLectureRepository, lecture_id: str) -> LectureRecord:
    record = repository.get_lecture(lecture_id)
    if record is None:
        raise ValidationError(
            ErrorDetail(
                code="lecture_not_found",
                message=f"Lecture not found: {lecture_id}",
                stage=AUTO_PIPELINE_STAGE,
                retryable=False,
            )
        )
    return record


def _completed_steps(record: LectureRecord) -> list[str]:
    return [str(item) for item in _list(record.pipeline_metadata.get("completed_steps"))]


def _time_budget_exhausted(started: float, budget: float | None) -> bool:
    return budget is not None and time.perf_counter() - started >= budget


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


def _dict_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _list(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def _now() -> str:
    return datetime.now(UTC).isoformat()

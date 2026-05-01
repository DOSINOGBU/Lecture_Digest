from __future__ import annotations

from lecturedigest.models import LectureRecord
from lecturedigest.note_markdown import NoteSourceUnit
from lecturedigest.note_profile import NoteContentProfile
from lecturedigest.openai_client import OpenAIClient
from lecturedigest.openai_note_parse import parse_note_response
from lecturedigest.openai_note_progress import time_budget_exhausted
from lecturedigest.openai_note_prompt import DEFAULT_OPENAI_NOTE_MODEL, NOTE_VARIANTS
from lecturedigest.openai_note_repair import build_note_repair_request
from lecturedigest.openai_types import OpenAIClientResult


def repair_longform_candidates(
    record: LectureRecord,
    candidates: list[dict[str, object]],
    *,
    source_units: list[NoteSourceUnit],
    content_profile: NoteContentProfile,
    client: OpenAIClient,
    client_results: list[OpenAIClientResult],
    tone: str,
    model: str = DEFAULT_OPENAI_NOTE_MODEL,
    prompt_version: str,
    max_repair_attempts: int,
    started_at: float,
    time_budget_seconds: float | None,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    repaired_candidates: list[dict[str, object]] = []
    repair_summaries: list[dict[str, object]] = []
    for variant_index, candidate in enumerate(candidates, start=1):
        if validation_status(candidate) != "flagged":
            repaired_candidates.append(candidate)
            continue
        current = candidate
        summary: dict[str, object] = {}
        for attempt in range(1, max_repair_attempts + 1):
            if time_budget_exhausted(started_at, time_budget_seconds):
                summary = repair_summary(current, attempt=attempt, applied=False)
                summary["skipped_reason"] = "time_budget_exhausted"
                current["repair_metadata"] = summary
                break
            request = build_note_repair_request(
                record,
                source_units=source_units,
                candidate=current,
                tone=tone,
                model=model,
                prompt_version=prompt_version,
                variant=str(current.get("variant") or NOTE_VARIANTS[variant_index - 1]),
                content_profile=content_profile,
            )
            result = client.send(request, dry_run=False)
            client_results.append(result)
            if not result.succeeded:
                summary = repair_summary(
                    current,
                    attempt=attempt,
                    applied=False,
                    result=result,
                )
                current["repair_metadata"] = summary
                break
            repaired = parse_note_response(
                result.body,
                record=record,
                source_units=source_units,
                tone=tone,
                model=model,
                prompt_version=prompt_version,
                client_result=result,
                content_profile=content_profile,
                expected_count=1,
                variant_index_start=variant_index,
            )[0]
            applied = is_repair_improvement(current, repaired)
            summary = repair_summary(
                current,
                repaired=repaired,
                attempt=attempt,
                applied=applied,
                result=result,
            )
            if applied:
                repaired["repair_metadata"] = summary
                current = repaired
            else:
                current["repair_metadata"] = summary
            if validation_status(current) != "flagged":
                break
        repair_summaries.append(summary)
        repaired_candidates.append(current)
    return repaired_candidates, repair_summaries


def repair_summary(
    original: dict[str, object],
    *,
    attempt: int,
    applied: bool,
    result: OpenAIClientResult | None = None,
    repaired: dict[str, object] | None = None,
) -> dict[str, object]:
    repaired_validation = validation(repaired or original)
    return {
        "candidate_id": original.get("candidate_id"),
        "variant": original.get("variant"),
        "attempt": attempt,
        "applied": applied,
        "initial_status": validation_status(original),
        "initial_failed_rules": failed_rules(original),
        "repaired_status": repaired_validation.get("status"),
        "repaired_failed_rules": _string_list(repaired_validation.get("failed_rules")),
        "openai_call": result.metadata.to_dict() if result else {},
        "error_code": result.error_code if result else None,
    }


def is_repair_improvement(
    original: dict[str, object],
    repaired: dict[str, object],
) -> bool:
    if validation_status(repaired) != "flagged":
        return True
    if len(failed_rules(repaired)) < len(failed_rules(original)):
        return True
    return _markdown_chars(repaired) >= _markdown_chars(original) + 500


def first_auto_approvable_candidate_id(candidates: list[dict[str, object]]) -> str:
    for candidate in candidates:
        if validation_status(candidate) != "flagged":
            return str(candidate.get("candidate_id") or "")
    return ""


def validation_status(candidate: dict[str, object]) -> str:
    return str(validation(candidate).get("status") or "unknown")


def failed_rules(candidate: dict[str, object]) -> list[str]:
    return _string_list(validation(candidate).get("failed_rules"))


def validation(candidate: dict[str, object] | None) -> dict[str, object]:
    if not isinstance(candidate, dict):
        return {}
    value = candidate.get("validation")
    return value if isinstance(value, dict) else {}


def _markdown_chars(candidate: dict[str, object]) -> int:
    return len(str(candidate.get("markdown") or ""))


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]

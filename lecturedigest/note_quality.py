from __future__ import annotations

from lecturedigest.errors import ErrorDetail, ValidationError
from lecturedigest.models import LectureRecord
from lecturedigest.note_depth import visible_source_artifacts

NOTE_QUALITY_STAGE = "note_quality"


def inspect_note_quality(
    record: LectureRecord,
    *,
    candidate_id: str | None = None,
) -> dict[str, object]:
    candidates = _select_candidates(record, candidate_id)
    items = [_candidate_quality(record, candidate) for candidate in candidates]
    return {
        "lecture_id": record.lecture_id,
        "candidate_count": len(record.note_candidates),
        "inspected_count": len(items),
        "approved_candidate_id": str(record.approved_note.get("candidate_id") or ""),
        "items": items,
        "summary": _summary(items),
    }


def format_note_quality_result(result: dict[str, object]) -> str:
    summary = _dict(result.get("summary"))
    candidate_count = int(result.get("candidate_count") or 0)
    lecture_id = str(result.get("lecture_id") or "")
    if candidate_count == 0:
        return (
            "[LectureNotes] inspect-note-quality empty "
            f"{{ lectureId={lecture_id}; candidates=0 }}"
        )

    lines = [
        "[LectureNotes] inspect-note-quality success "
        f"{{ lectureId={lecture_id}; inspected={result.get('inspected_count')}; "
        f"overall={summary.get('overall_status')}; "
        f"reviewReady={summary.get('review_ready_count')}; "
        f"needsReview={summary.get('needs_review_count')}; "
        f"blocked={summary.get('blocked_count')}; "
        f"warnings={summary.get('warning_count')}; "
        f"visibleSourceArtifacts={summary.get('visible_source_artifact_count')}; "
        f"sourceMappingGaps={summary.get('source_mapping_gap_count')} }}"
    ]
    for item in _dict_list(result.get("items")):
        lines.extend(_format_candidate_lines(item))
    return "\n".join(lines)


def _candidate_quality(
    record: LectureRecord,
    candidate: dict[str, object],
) -> dict[str, object]:
    validation = _dict(candidate.get("validation"))
    difficulty = _dict(validation.get("difficulty_explanations"))
    difficulty_metrics = _dict(difficulty.get("metrics"))
    generator_notes = _dict(candidate.get("generator_notes"))
    explanations = _dict_list(generator_notes.get("difficulty_explanations"))
    failed_rules = _str_list(validation.get("failed_rules"))
    warnings = _str_list(validation.get("warnings"))
    quality_flags = _str_list(validation.get("quality_flags"))
    artifacts = _visible_artifacts(candidate, validation)
    source_gaps = _source_mapping_gaps(candidate, validation)
    known_expected = int(difficulty_metrics.get("known_acronym_count") or 0)
    known_explained = _known_acronym_explanation_count(explanations)
    gate_status = _gate_status(
        failed_rules=failed_rules,
        warnings=warnings,
        visible_artifacts=artifacts,
        source_gaps=source_gaps,
    )
    return {
        "candidate_id": str(candidate.get("candidate_id") or ""),
        "variant": str(candidate.get("variant") or ""),
        "candidate_status": str(candidate.get("status") or ""),
        "validation_status": str(validation.get("status") or "unknown"),
        "gate_status": gate_status,
        "approved": _is_approved(record, candidate),
        "failed_rules": failed_rules,
        "warnings": warnings,
        "quality_flags": quality_flags,
        "visible_source_artifacts": artifacts,
        "source_mapping_gaps": source_gaps,
        "difficulty_explanation_count": len(explanations),
        "expected_difficult_concept_count": int(
            difficulty_metrics.get("expected_count") or 0
        ),
        "known_acronym_expected_count": known_expected,
        "known_acronym_explained_count": known_explained,
        "acronym_metadata_gap_count": max(0, known_expected - known_explained),
        "easy_marker_count": int(difficulty_metrics.get("easy_marker_count") or 0),
        "source_coverage_ratio": _source_coverage_ratio(validation),
    }


def _select_candidates(
    record: LectureRecord,
    candidate_id: str | None,
) -> list[dict[str, object]]:
    candidates = list(record.note_candidates)
    if not candidate_id:
        return candidates
    selected = [
        candidate
        for candidate in candidates
        if str(candidate.get("candidate_id") or "") == candidate_id
    ]
    if selected:
        return selected
    raise ValidationError(
        ErrorDetail(
            code="note_candidate_not_found",
            message=f"Note candidate not found: {candidate_id}",
            stage=NOTE_QUALITY_STAGE,
            retryable=False,
        )
    )


def _summary(items: list[dict[str, object]]) -> dict[str, object]:
    blocked = sum(1 for item in items if item.get("gate_status") == "blocked")
    needs_review = sum(1 for item in items if item.get("gate_status") == "needs_review")
    review_ready = sum(1 for item in items if item.get("gate_status") == "review_ready")
    warning_count = sum(len(_str_list(item.get("warnings"))) for item in items)
    visible_source_count = sum(
        len(_str_list(item.get("visible_source_artifacts"))) for item in items
    )
    source_gap_count = sum(len(_str_list(item.get("source_mapping_gaps"))) for item in items)
    acronym_gap_count = sum(int(item.get("acronym_metadata_gap_count") or 0) for item in items)
    return {
        "overall_status": _overall_status(
            item_count=len(items),
            blocked=blocked,
            needs_review=needs_review,
            review_ready=review_ready,
        ),
        "review_ready_count": review_ready,
        "needs_review_count": needs_review,
        "blocked_count": blocked,
        "warning_count": warning_count,
        "visible_source_artifact_count": visible_source_count,
        "source_mapping_gap_count": source_gap_count,
        "acronym_metadata_gap_count": acronym_gap_count,
    }


def _overall_status(
    *,
    item_count: int,
    blocked: int,
    needs_review: int,
    review_ready: int,
) -> str:
    if item_count == 0:
        return "empty"
    if blocked == item_count:
        return "blocked"
    if blocked or needs_review:
        return "needs_review"
    if review_ready:
        return "review_ready"
    return "unknown"


def _gate_status(
    *,
    failed_rules: list[str],
    warnings: list[str],
    visible_artifacts: list[str],
    source_gaps: list[str],
) -> str:
    if failed_rules or visible_artifacts or source_gaps:
        return "blocked"
    if warnings:
        return "needs_review"
    return "review_ready"


def _visible_artifacts(
    candidate: dict[str, object],
    validation: dict[str, object],
) -> list[str]:
    artifacts = _str_list(validation.get("visible_source_artifacts"))
    for item in visible_source_artifacts(str(candidate.get("markdown") or "")):
        if item not in artifacts:
            artifacts.append(item)
    return artifacts


def _source_mapping_gaps(
    candidate: dict[str, object],
    validation: dict[str, object],
) -> list[str]:
    gaps = _str_list(validation.get("unmapped_sections"))
    for section in _dict_list(candidate.get("sections")):
        section_key = str(section.get("section_key") or section.get("note_section_id") or "")
        if section_key and not section.get("segment_ids") and section_key not in gaps:
            gaps.append(section_key)
    return gaps


def _known_acronym_explanation_count(explanations: list[dict[str, object]]) -> int:
    count = 0
    for item in explanations:
        if item.get("expansion_known") is not True:
            continue
        if not str(item.get("expanded_form") or "").strip():
            continue
        if not str(item.get("plain_explanation") or "").strip():
            continue
        count += 1
    return count


def _source_coverage_ratio(validation: dict[str, object]) -> float:
    body_depth = _dict(validation.get("body_depth"))
    metrics = _dict(body_depth.get("metrics"))
    value = metrics.get("source_coverage_ratio")
    return float(value) if isinstance(value, (int, float)) else 0.0


def _is_approved(record: LectureRecord, candidate: dict[str, object]) -> bool:
    candidate_id = str(candidate.get("candidate_id") or "")
    approved_id = str(record.approved_note.get("candidate_id") or "")
    return bool(candidate_id and candidate_id == approved_id)


def _format_candidate_lines(item: dict[str, object]) -> list[str]:
    lines = [
        "- "
        f"{item.get('candidate_id')} "
        f"variant={item.get('variant') or 'unknown'} "
        f"candidateStatus={item.get('candidate_status') or 'unknown'} "
        f"validation={item.get('validation_status')} "
        f"gate={item.get('gate_status')} "
        f"approved={item.get('approved')} "
        f"difficulty={item.get('difficulty_explanation_count')}/"
        f"{item.get('expected_difficult_concept_count')} "
        f"knownAcronyms={item.get('known_acronym_explained_count')}/"
        f"{item.get('known_acronym_expected_count')} "
        f"sourceCoverage={item.get('source_coverage_ratio')}"
    ]
    if item.get("failed_rules"):
        lines.append(f"  failed={','.join(_str_list(item.get('failed_rules')))}")
    if item.get("warnings"):
        lines.append(f"  warnings={','.join(_str_list(item.get('warnings')))}")
    if item.get("visible_source_artifacts"):
        lines.append(
            "  visibleSourceArtifacts="
            + ",".join(_str_list(item.get("visible_source_artifacts")))
        )
    if item.get("source_mapping_gaps"):
        lines.append("  sourceMappingGaps=" + ",".join(_str_list(item.get("source_mapping_gaps"))))
    return lines


def _dict(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _dict_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _str_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]

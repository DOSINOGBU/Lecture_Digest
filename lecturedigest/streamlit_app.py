from __future__ import annotations

from pathlib import Path

import streamlit as st

from lecturedigest.cli import DEFAULT_STORE
from lecturedigest.errors import LectureDigestError
from lecturedigest.models import CorrectionLogEntry, LectureRecord
from lecturedigest.storage import JsonLectureRepository
from lecturedigest.streamlit_registration import render_registration
from lecturedigest.ui_actions import (
    approve_correction,
    approve_note,
    reject_correction,
    reject_note,
)
from lecturedigest.ui_state import (
    card_review_state,
    correction_review_queue,
    cost_or_quota_issues,
    has_openai_api_key,
    lecture_label,
    load_library,
    note_candidates,
    note_quality_review,
    paid_action_previews,
    quiz_review_state,
    status_counts,
)


def main() -> None:
    st.set_page_config(page_title="LectureDigest", layout="wide")
    st.title("LectureDigest")

    store_path = Path(
        st.sidebar.text_input("Lecture store", str(DEFAULT_STORE))
    )
    repository = JsonLectureRepository(store_path)
    render_registration(repository)

    with st.spinner("Loading lecture library"):
        library = load_library(repository)

    if library.error_message:
        st.error("Lecture store could not be loaded.")
        st.code(library.error_message)
        return

    if library.is_empty:
        st.info("No lectures registered yet.")
        st.caption("Register a local video path from the sidebar to start.")
        _render_api_key_state()
        return

    selected_id = st.sidebar.selectbox(
        "Lecture",
        [record.lecture_id for record in library.lectures],
        format_func=lambda lecture_id: _label_for_id(library.lectures, lecture_id),
    )
    record = next(item for item in library.lectures if item.lecture_id == selected_id)
    _render_api_key_state()
    _render_lecture(record, repository)


def _render_api_key_state() -> None:
    if has_openai_api_key():
        st.sidebar.success("OPENAI_API_KEY is available.")
    else:
        st.sidebar.warning("OPENAI_API_KEY is not set. Paid OpenAI actions are unavailable.")


def _render_lecture(
    record: LectureRecord,
    repository: JsonLectureRepository,
) -> None:
    st.subheader(record.title)
    st.caption(f"{record.instructor} | {record.category} | {record.lecture_id}")

    tabs = st.tabs(
        [
            "Status",
            "Note Review",
            "Correction Review",
            "Anki Preview",
            "Quiz Preview",
            "Paid Actions",
        ]
    )
    with tabs[0]:
        _render_status(record)
    with tabs[1]:
        _render_note_review(record, repository)
    with tabs[2]:
        _render_correction_review(record, repository)
    with tabs[3]:
        _render_cards(record)
    with tabs[4]:
        _render_quizzes(record)
    with tabs[5]:
        _render_paid_actions(record)


def _render_status(record: LectureRecord) -> None:
    counts = status_counts(record)
    columns = st.columns(4)
    columns[0].metric("Status", record.status)
    columns[1].metric("Stage", record.stage)
    columns[2].metric("Segments", counts["segments"])
    columns[3].metric("Issues", counts["issues"])

    st.write("Pipeline counts")
    st.json(counts)

    quota_messages = cost_or_quota_issues(record)
    if quota_messages:
        st.warning("Cost or quota related issue detected.")
        for message in quota_messages:
            st.write(message)

    if record.issues:
        st.write("Issues")
        for issue in record.issues:
            st.error(f"{issue.stage}: {issue.code} | retryable={issue.retryable}")
            st.caption(issue.message)
    else:
        st.success("No recorded issues.")

    st.write("Metadata")
    st.json(
        {
            "transcript": record.transcript_metadata,
            "correction": record.correction_metadata,
            "rag": record.rag_metadata,
            "note": record.note_metadata,
            "cards": record.card_metadata,
            "quiz": record.quiz_metadata,
            "pipeline": record.pipeline_metadata,
        }
    )


def _render_note_review(
    record: LectureRecord,
    repository: JsonLectureRepository,
) -> None:
    _render_note_quality(record)
    candidates = note_candidates(record)
    if not candidates:
        st.info("No note candidates are available for review.")
        return

    for candidate in candidates:
        candidate_id = str(candidate.get("candidate_id") or "")
        with st.expander(
            f"{candidate_id} | {candidate.get('status', 'unknown')}",
            expanded=candidate.get("status") not in {"rejected", "approved"},
        ):
            markdown = str(candidate.get("markdown") or candidate.get("text") or "")
            if markdown:
                st.markdown(markdown)
            else:
                st.info("This note candidate has no Markdown preview.")
            st.json(candidate.get("validation", {}))
            left, right = st.columns(2)
            if left.button("Approve", key=f"approve-note-{candidate_id}"):
                _run_action(
                    lambda value=candidate_id: approve_note(
                        repository,
                        lecture_id=record.lecture_id,
                        candidate_id=value,
                    ),
                    success_message="Note candidate approved.",
                )
            reason = right.text_input(
                "Reject reason",
                key=f"reject-note-reason-{candidate_id}",
            )
            if right.button("Reject", key=f"reject-note-{candidate_id}"):
                _run_action(
                    lambda value=candidate_id, text=reason: reject_note(
                        repository,
                        lecture_id=record.lecture_id,
                        candidate_id=value,
                        reason=text,
                    ),
                    success_message="Note candidate rejected.",
                )


def _render_note_quality(record: LectureRecord) -> None:
    state = note_quality_review(record)
    if state.error_message:
        st.error("Note quality could not be inspected.")
        st.code(state.error_message)
        return

    result = state.result
    summary = _dict(result.get("summary"))
    overall = str(summary.get("overall_status") or "unknown")
    columns = st.columns(5)
    columns[0].metric("Quality", overall)
    columns[1].metric("Review ready", int(summary.get("review_ready_count") or 0))
    columns[2].metric("Needs review", int(summary.get("needs_review_count") or 0))
    columns[3].metric("Blocked", int(summary.get("blocked_count") or 0))
    columns[4].metric("Warnings", int(summary.get("warning_count") or 0))

    if overall == "blocked":
        st.error("At least one note candidate is blocked by quality gates.")
    elif overall == "needs_review":
        st.warning("At least one note candidate is approved or readable but still needs review.")
    elif overall == "review_ready":
        st.success("Note candidates are ready for human review.")
    elif overall == "empty":
        st.info("No note candidates are available for quality inspection.")

    detail = {
        "visible_source_artifacts": summary.get("visible_source_artifact_count", 0),
        "source_mapping_gaps": summary.get("source_mapping_gap_count", 0),
        "known_acronym_gaps": summary.get("acronym_metadata_gap_count", 0),
    }
    st.caption("Quality gate details")
    st.json(detail)

    for item in _dict_list(result.get("items")):
        label = (
            f"{item.get('candidate_id')} | gate={item.get('gate_status')} "
            f"| approved={item.get('approved')}"
        )
        with st.expander(label, expanded=item.get("gate_status") != "review_ready"):
            st.json(
                {
                    "candidate_status": item.get("candidate_status"),
                    "validation_status": item.get("validation_status"),
                    "failed_rules": item.get("failed_rules", []),
                    "warnings": item.get("warnings", []),
                    "quality_flags": item.get("quality_flags", []),
                    "visible_source_artifacts": item.get("visible_source_artifacts", []),
                    "source_mapping_gaps": item.get("source_mapping_gaps", []),
                    "difficulty_explanations": {
                        "actual": item.get("difficulty_explanation_count"),
                        "expected": item.get("expected_difficult_concept_count"),
                    },
                    "known_acronyms": {
                        "explained": item.get("known_acronym_explained_count"),
                        "expected": item.get("known_acronym_expected_count"),
                    },
                    "source_coverage_ratio": item.get("source_coverage_ratio"),
                }
            )


def _render_correction_review(
    record: LectureRecord,
    repository: JsonLectureRepository,
) -> None:
    queue = correction_review_queue(record)
    if not queue:
        st.info("No correction candidates require review.")
        return

    for entry in queue:
        _render_correction_entry(record, repository, entry)


def _render_correction_entry(
    record: LectureRecord,
    repository: JsonLectureRepository,
    entry: CorrectionLogEntry,
) -> None:
    with st.container(border=True):
        st.write(f"Segment `{entry.segment_id}` | confidence={entry.confidence}")
        left, right = st.columns(2)
        left.text_area("Original", entry.original_text, height=140, disabled=True)
        right.text_area("Corrected", entry.corrected_text, height=140, disabled=True)
        st.caption(entry.reason or "No reason provided.")
        approve_col, reject_col = st.columns(2)
        if approve_col.button("Approve correction", key=f"approve-correction-{entry.segment_id}"):
            _run_action(
                lambda value=entry.segment_id: approve_correction(
                    repository,
                    lecture_id=record.lecture_id,
                    segment_id=value,
                ),
                success_message="Correction approved.",
            )
        reason = reject_col.text_input(
            "Reject reason",
            key=f"reject-correction-reason-{entry.segment_id}",
        )
        if reject_col.button("Reject correction", key=f"reject-correction-{entry.segment_id}"):
            _run_action(
                lambda value=entry.segment_id, text=reason: reject_correction(
                    repository,
                    lecture_id=record.lecture_id,
                    segment_id=value,
                    reason=text,
                ),
                success_message="Correction rejected.",
            )


def _render_cards(record: LectureRecord) -> None:
    state = card_review_state()
    _render_review_errors(state.error_messages)
    if state.manifest:
        st.caption("Card review source of truth")
        st.json(
            {
                "manifest": state.manifest_path,
                "source_policy": state.manifest.get("source_policy"),
                "selected_set": state.manifest.get("selected_set"),
                "default_exportable_scope": _dict(
                    state.manifest.get("review_policy")
                ).get("default_exportable_scope"),
            }
        )
        expected = state.expected_counts
        columns = st.columns(4)
        columns[0].metric("Ready cards", expected.get("ready_cards", len(state.items)))
        columns[1].metric("Excluded flagged", expected.get("excluded_flagged_cards", 0))
        columns[2].metric("Source gaps", expected.get("source_mapping_missing", 0))
        columns[3].metric("Visible sources", expected.get("visible_source_artifacts", 0))
        st.write("Card type distribution")
        st.json(state.manifest.get("type_counts", {}))
        excluded = _dict_list(state.manifest.get("excluded_cards"))
        if excluded:
            st.warning("Excluded flagged cards remain visible as review context.")
            st.table(excluded)

    cards = state.items or [item for item in record.flashcards if isinstance(item, dict)]
    if not cards:
        st.info("No Anki card preview is available.")
        return

    st.caption(f"Showing {len(cards)} card review items.")
    for index, card in enumerate(cards, start=1):
        label = (
            f"{index}. {card.get('card_type', 'card')} | "
            f"{card.get('status', 'unknown')} | {card.get('card_id', '')}"
        )
        with st.expander(label, expanded=False):
            st.write(card.get("front") or card.get("cloze_text") or "")
            st.caption(card.get("back") or card.get("extra") or "")
            st.json(
                {
                    "source_segment_ids": card.get("source_segment_ids", []),
                    "start_ts": card.get("start_ts"),
                    "end_ts": card.get("end_ts"),
                    "jump_link": card.get("jump_link"),
                    "tags": card.get("tags", []),
                    "validation": card.get("validation", {}),
                }
            )


def _render_quizzes(record: LectureRecord) -> None:
    state = quiz_review_state()
    _render_review_errors(state.error_messages)
    if state.manifest:
        st.caption("Quiz review source of truth")
        columns = st.columns(4)
        columns[0].metric("Expected total", state.expected_counts.get("expected_total", 0))
        columns[1].metric("Loaded total", len(state.items))
        columns[2].metric("Sources", len(state.source_counts))
        columns[3].metric("Dedupe", str(state.summary.get("dedupe_policy") or ""))
        st.write("Source counts")
        st.json(state.source_counts)

    quizzes = state.items or [item for item in record.quiz_items if isinstance(item, dict)]
    if not quizzes:
        st.info("No quiz preview is available.")
        return

    st.caption(f"Showing {len(quizzes)} quiz review items.")
    for index, item in enumerate(quizzes, start=1):
        badge = str(item.get("_review_source_badge") or "lecture_store")
        label = (
            f"{index}. {badge} | {item.get('question_type', 'quiz')} | "
            f"{item.get('status', 'unknown')}"
        )
        with st.expander(label, expanded=False):
            st.write(item.get("question") or "")
            choices = item.get("choices", [])
            if isinstance(choices, list) and choices:
                st.table(choices)
            else:
                st.caption(str(item.get("expected_answer") or ""))
            st.json(
                {
                    "source_badge": badge,
                    "source": item.get("source", {}),
                    "source_card_ids": item.get("source_card_ids", []),
                    "validation": item.get("validation", {}),
                }
            )


def _render_paid_actions(record: LectureRecord) -> None:
    if not has_openai_api_key():
        st.warning("OPENAI_API_KEY is missing. Use dry-run before paid actions.")
    for preview in paid_action_previews(record):
        with st.container(border=True):
            st.write(preview["name"])
            st.caption(
                "External boundary: "
                f"{preview['external_boundary']} | model={preview['model']}"
            )
            st.metric("Estimated input bytes", int(preview["input_size_bytes"]))
            st.code(str(preview["dry_run"]))
            st.button(
                "Paid execution disabled in MVP UI",
                key=f"paid-disabled-{preview['name']}",
                disabled=True,
                use_container_width=True,
            )


def _run_action(action, *, success_message: str) -> None:
    try:
        action()
    except LectureDigestError as exc:
        st.error(f"{exc.detail.stage}: {exc.detail.code}")
        st.caption(exc.detail.message)
        return
    except Exception as exc:
        st.error(f"{exc.__class__.__name__}: {exc}")
        return
    st.success(success_message)
    st.rerun()


def _render_review_errors(messages: list[str]) -> None:
    for message in messages:
        st.warning(message)


def _label_for_id(records: list[LectureRecord], lecture_id: str) -> str:
    for record in records:
        if record.lecture_id == lecture_id:
            return lecture_label(record)
    return lecture_id


def _dict(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _dict_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


if __name__ == "__main__":
    main()

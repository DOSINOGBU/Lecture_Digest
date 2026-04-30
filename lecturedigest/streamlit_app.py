from __future__ import annotations

from pathlib import Path

import streamlit as st

from lecturedigest.cli import DEFAULT_STORE
from lecturedigest.errors import LectureDigestError
from lecturedigest.models import CorrectionLogEntry, LectureRecord
from lecturedigest.storage import JsonLectureRepository
from lecturedigest.ui_actions import (
    approve_correction,
    approve_note,
    register_lecture_from_paths,
    reject_correction,
    reject_note,
)
from lecturedigest.ui_state import (
    correction_review_queue,
    cost_or_quota_issues,
    has_openai_api_key,
    lecture_label,
    load_library,
    note_candidates,
    paid_action_previews,
    status_counts,
)


def main() -> None:
    st.set_page_config(page_title="LectureDigest", layout="wide")
    st.title("LectureDigest")

    store_path = Path(
        st.sidebar.text_input("Lecture store", str(DEFAULT_STORE))
    )
    repository = JsonLectureRepository(store_path)
    _render_registration(repository)

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


def _render_registration(repository: JsonLectureRepository) -> None:
    with st.sidebar.expander("Register lecture", expanded=False):
        video_path = st.text_input("Video path")
        subtitle_path = st.text_input("Subtitle path")
        title = st.text_input("Title")
        instructor = st.text_input("Instructor")
        category = st.text_input("Category")
        if st.button("Register", use_container_width=True):
            if not video_path or not title or not instructor or not category:
                st.error("Video path, title, instructor, and category are required.")
                return
            _run_action(
                lambda: register_lecture_from_paths(
                    repository,
                    video_path=video_path,
                    subtitle_path=subtitle_path or None,
                    title=title,
                    instructor=instructor,
                    category=category,
                ),
                success_message="Lecture registered.",
            )


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
        }
    )


def _render_note_review(
    record: LectureRecord,
    repository: JsonLectureRepository,
) -> None:
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
    if not record.flashcards:
        st.info("No Anki card preview is available.")
        return
    for card in record.flashcards:
        with st.container(border=True):
            st.write(f"{card.get('card_type')} | {card.get('status')}")
            st.write(card.get("front") or card.get("cloze_text") or "")
            st.caption(card.get("back") or card.get("extra") or "")
            st.json(card.get("source", {}))


def _render_quizzes(record: LectureRecord) -> None:
    if not record.quiz_items:
        st.info("No quiz preview is available.")
        return
    for item in record.quiz_items:
        with st.container(border=True):
            st.write(f"{item.get('question_type')} | {item.get('status')}")
            st.write(item.get("question") or "")
            choices = item.get("choices", [])
            if isinstance(choices, list) and choices:
                st.table(choices)
            else:
                st.caption(str(item.get("expected_answer") or ""))
            st.json(item.get("source", {}))


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


def _label_for_id(records: list[LectureRecord], lecture_id: str) -> str:
    for record in records:
        if record.lecture_id == lecture_id:
            return lecture_label(record)
    return lecture_id


if __name__ == "__main__":
    main()

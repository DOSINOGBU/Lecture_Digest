from __future__ import annotations

import streamlit as st

from lecturedigest.errors import LectureDigestError
from lecturedigest.storage import JsonLectureRepository
from lecturedigest.ui_actions import register_lecture_from_paths
from lecturedigest.ui_state import has_openai_api_key


def render_registration(repository: JsonLectureRepository) -> None:
    with st.sidebar.expander("Register lecture", expanded=False):
        video_path = st.text_input("Video path")
        subtitle_path = st.text_input("Subtitle path")
        title = st.text_input("Title")
        instructor = st.text_input("Instructor")
        category = st.text_input("Category")

        auto_ai = st.checkbox("Run AI pipeline after registration")
        include_ocr = st.checkbox("Include OCR", disabled=not auto_ai)
        time_budget = st.number_input(
            "AI time budget seconds",
            min_value=60,
            max_value=3600,
            value=900,
            step=60,
            disabled=not auto_ai,
        )
        if auto_ai:
            st.caption(
                "External boundary: video/audio/subtitle text and approved metadata "
                "can be sent to OpenAI. OCR is sent only when Include OCR is enabled."
            )
            if not has_openai_api_key():
                st.warning("OPENAI_API_KEY is required before the AI pipeline can run.")

        if st.button("Register", use_container_width=True):
            if not video_path or not title or not instructor or not category:
                st.error("Video path, title, instructor, and category are required.")
                return
            if auto_ai and not has_openai_api_key():
                st.error("OPENAI_API_KEY is required for auto AI processing.")
                return
            spinner_text = (
                "Registering lecture and running AI pipeline"
                if auto_ai
                else "Registering lecture"
            )
            with st.spinner(spinner_text):
                _run_registration(
                    repository,
                    lambda: register_lecture_from_paths(
                        repository,
                        video_path=video_path,
                        subtitle_path=subtitle_path or None,
                        title=title,
                        instructor=instructor,
                        category=category,
                        auto_ai=auto_ai,
                        include_ocr=include_ocr,
                        time_budget_seconds=float(time_budget) if auto_ai else None,
                    ),
                    success_message=(
                        "Lecture registered and AI pipeline finished."
                        if auto_ai
                        else "Lecture registered."
                    ),
                )


def _run_registration(
    repository: JsonLectureRepository,
    action,
    *,
    success_message: str,
) -> None:
    try:
        lecture_id = str(action())
    except LectureDigestError as exc:
        st.error(f"{exc.detail.stage}: {exc.detail.code}")
        st.caption(exc.detail.message)
        return
    except Exception as exc:
        st.error(f"{exc.__class__.__name__}: {exc}")
        return
    record = repository.get_lecture(lecture_id)
    pipeline_status = (record.pipeline_metadata or {}).get("status") if record else None
    if pipeline_status == "partial":
        st.warning("Lecture registered, and the AI pipeline saved a partial checkpoint.")
    else:
        st.success(success_message)
    st.rerun()

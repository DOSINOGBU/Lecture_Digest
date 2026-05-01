# Auto AI Pipeline Streamlit UI Validation - 2026-05-01

## Summary

Validated the Streamlit registration flow for the opt-in automatic AI pipeline in the in-app browser at `http://localhost:8501/`.

The goal was to confirm that a user can register a lecture from the UI, explicitly enable the paid AI pipeline, see the external data boundary warning, and then view the completed results in the existing review UI.

## Test Input

- Lecture id: `lec_23e7187d5980`
- Title: `Streamlit Auto AI Smoke`
- Input artifact: local generated smoke video under `.lecturedigest/smoke-auto-ai/`
- Subtitle artifact: local generated smoke subtitle under `.lecturedigest/smoke-auto-ai/`
- Transcript source: subtitle
- OCR: disabled
- STT: skipped because a subtitle file was provided

## Browser Flow Checked

- Opened Streamlit at `http://localhost:8501/`.
- Expanded the `Register lecture` panel.
- Confirmed `OPENAI_API_KEY is available`.
- Filled video path, subtitle path, title, instructor, and category.
- Confirmed `Include OCR` starts disabled.
- Enabled `Run AI pipeline after registration`.
- Confirmed `Include OCR` and `AI time budget seconds` became enabled.
- Confirmed the external data boundary notice appeared:
  - video/audio/subtitle text and approved metadata can be sent to OpenAI
  - OCR is sent only when `Include OCR` is enabled
- Submitted registration from the UI.
- Selected the resulting lecture in the UI.
- Confirmed the UI displays `Streamlit Auto AI Smoke (quizzes_ready)`.

## Result

- Pipeline status: `completed`
- Final lecture status: `quizzes_ready`
- Final stage: `quiz`
- Segment count: 3
- Chunks: 1
- Search index entries: 1
- Note candidates: 3
- Auto-approved note: `note-candidate-openai-d6db5ad6b1-02`
- Approval mode: `auto_best_candidate`
- Cards: 8
- Quizzes: 6
- Issues: none recorded

## Completed Steps

- `finalize_transcript`
- `chunk`
- `index`
- `generate_notes`
- `auto_approve_note`
- `generate_cards`
- `generate_quizzes`

## Observations

- The UI kept automatic AI execution opt-in.
- The UI warned about external OpenAI transmission before submission.
- The final results appeared through the existing lecture selector and status tab.
- Generated artifacts remain under `.lecturedigest` and are not committed.

## Remaining Validation

- Large-media split routing was validated in `docs/validation/auto-ai-pipeline-large-media-2026-05-01.md`.
- Long real-lecture completion through cards and quizzes remains blocked by note auto-approval quality on the large sample.

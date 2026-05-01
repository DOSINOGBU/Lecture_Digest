# Auto AI Pipeline Smoke Validation - 2026-05-01

## Summary

Ran a real paid OpenAI smoke test for the opt-in automatic AI pipeline using a tiny local subtitle-backed lecture.

The goal was to validate the full orchestration path with minimal cost:

`subtitle transcript -> correction -> chunk/index -> embeddings -> OpenAI notes -> auto best note approval -> OpenAI cards -> OpenAI quizzes`

## Test Input

- Lecture id: `lec_1ba2d656846f`
- Title: `Auto AI Smoke`
- Input type: local synthetic smoke artifact under `.lecturedigest/smoke-auto-ai/`
- Transcript source: subtitle
- Segment count: 3
- OCR: disabled
- STT: skipped because a subtitle file was provided
- Command:

```powershell
python -m lecturedigest process-lecture --lecture-id lec_1ba2d656846f --openai --resume --time-budget-seconds 840
```

## Result

- Pipeline status: `completed`
- Final lecture status: `quizzes_ready`
- Final stage: `quiz`
- Completed steps:
  - `finalize_transcript`
  - `chunk`
  - `index`
  - `generate_notes`
  - `auto_approve_note`
  - `generate_cards`
  - `generate_quizzes`
- Chunks: 1
- Search index entries: 1
- Note candidates: 3
- Auto-approved note: `note-candidate-openai-4849d2157c-02`
- Approval mode: `auto_best_candidate`
- Cards: 8
- Quizzes: 6
- Issues: none recorded

## Observations

- The dry-run correctly planned 7 steps and skipped STT/OCR.
- The actual run completed within the configured 840 second time budget.
- The pipeline checkpoint metadata recorded every completed stage.
- The generated artifacts live in `.lecturedigest` and are intentionally not committed.

## Remaining Validation

- STT routing, large-media split routing, and Streamlit opt-in registration were validated in separate 2026-05-01 records.
- Long real-lecture completion through cards and quizzes remains blocked by note auto-approval quality on the large sample.
- Review the generated smoke note/card/quiz quality manually only if this smoke artifact is kept as a reference sample.

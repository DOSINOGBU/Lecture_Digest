# Auto AI Pipeline STT Smoke Validation - 2026-05-01

## Summary

Ran a real paid OpenAI smoke test for the automatic AI pipeline on a lecture without subtitles.

The goal was to validate that the orchestrator starts with STT when `transcript_source=stt_pending`, then continues through correction, indexing, note generation, card generation, and quiz generation.

## Test Input

- Lecture id: `lec_5b7505cd8ea1`
- Title: `Auto AI STT Smoke`
- Input artifact: local generated speech mp4 under `.lecturedigest/smoke-auto-ai-stt/`
- Subtitle: none
- Original registration status: `stt_required`
- Original transcript source: `stt_pending`
- File size: 219,848 bytes
- OCR: disabled
- Command:

```powershell
python -m lecturedigest process-lecture --lecture-id lec_5b7505cd8ea1 --openai --resume --time-budget-seconds 840
```

## Result

- Pipeline status: `completed`
- Final lecture status: `quizzes_ready`
- Final stage: `quiz`
- Transcript source after run: `stt`
- STT provider: `openai_transcriptions`
- STT model: `gpt-4o-transcribe-diarize`
- STT response format: `diarized_json`
- STT input size: 219,848 bytes
- STT call status: `succeeded`
- STT duration: 6,848 ms
- Segment count: 6
- Chunks: 1
- Search index entries: 1
- Note candidates: 3
- Auto-approved note: `note-candidate-openai-4be96b8aab-01`
- Approval mode: `auto_best_candidate`
- Cards: 8
- Quizzes: 6
- Issues: none recorded

## Completed Steps

- `transcribe`
- `finalize_transcript`
- `chunk`
- `index`
- `generate_notes`
- `auto_approve_note`
- `generate_cards`
- `generate_quizzes`

## Observations

- Dry-run correctly planned `transcribe` as the first step.
- The actual run completed within the configured 840 second time budget.
- STT metadata recorded provider, model, response format, input size, duration, and external data boundary.
- Checkpoint metadata recorded all completed stages.
- Generated artifacts remain under `.lecturedigest` and are not committed.

## Remaining Validation

- Large-media split routing and Streamlit opt-in registration were validated in separate 2026-05-01 records.
- Long real-lecture completion through cards and quizzes remains blocked by note auto-approval quality on the large sample.

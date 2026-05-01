# 25. Auto AI Pipeline Validation

## Status

Partial

## Goal

Validate the automatic AI pipeline before using it as the default assisted workflow for newly registered lectures.

## Scope

- Unit-test routing and checkpoint behavior with fake OpenAI dependencies.
- Validate CLI dry-run output without sending data externally.
- Verify Python compile and harness checks.
- Record remaining manual/paid smoke tests separately.

## Validation Completed

- Subtitle lecture dry-run plans correction, chunk, index, notes, cards, and quizzes without STT.
- `stt_pending` lecture plans STT before downstream steps.
- OCR is only planned when requested.
- `subtitle_unmatched` is blocked in preflight.
- Failed preflight saves `pipeline_metadata.status=failed` during actual runs.
- Resume skips already completed steps.
- Time budget exhaustion saves partial metadata.

## Validation Not Completed

- A real paid OpenAI end-to-end smoke test was not run in this implementation pass.
- A real Streamlit click-through was not run in browser in this pass.
- Large media split plus automatic pipeline was not run against a real >25MB lecture.

## Result

- Implementation is ready for dry-run and fake-client validation.
- Actual API smoke should use a small lecture first, with OCR disabled unless explicitly needed.

# Auto AI Pipeline Validation - 2026-05-01

## Summary

Implemented an opt-in automatic AI pipeline for LectureDigest.

The pipeline is intentionally not triggered by normal registration. It runs only through:

- `process-lecture --lecture-id <id> --openai`
- `register --auto-ai`
- `register-folder --auto-ai`
- Streamlit registration checkbox: `Run AI pipeline after registration`

## Validated Behavior

- Subtitled lectures skip STT.
- Lectures without subtitles use STT only when `transcript_source=stt_pending`.
- `subtitle_unmatched` is blocked instead of being silently routed to STT.
- OCR is excluded by default and added only by `--include-ocr` or the UI checkbox.
- Dry-run reports the planned steps without requiring an API key or saving pipeline metadata.
- Actual runs require `OPENAI_API_KEY`.
- Failed preflight saves failure metadata for non-dry-run execution.
- Each completed stage records a checkpoint in `pipeline_metadata.completed_steps`.
- Resume skips previously completed stages.
- Time budget exhaustion saves a partial state.

## Checks Run During Implementation

- `python -m unittest discover -s tests -p test_auto_pipeline.py`
- `python -m unittest discover -s tests -p test_cli.py`
- `python -m compileall lecturedigest tests`
- `python -m lecturedigest --help`
- `python -m lecturedigest process-lecture --help`

## Remaining Manual Validation

- Run a real paid OpenAI smoke test on a very small lecture.
- Run the same flow on a lecture that needs STT.
- Run a large >25MB lecture after media splitting is confirmed in the same pipeline.
- Click through the Streamlit registration flow and confirm status/error messages.

## Risk Notes

- The auto-approved note is a draft workflow approval, not a human golden approval.
- OCR can add significant cost and latency, so it remains opt-in.
- Long note/card/quiz generation can still exceed a single terminal window's patience, but checkpoints and resume now preserve completed work.

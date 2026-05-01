# 23. Auto AI Pipeline Orchestrator

## Status

Completed

## Goal

Add a single use case that can run the paid AI pipeline after a lecture is registered, while keeping paid execution opt-in and resumable.

## Scope

- Add `lecturedigest/auto_pipeline.py` as the orchestration layer.
- Reuse the existing STT, correction, chunk, index, OpenAI note, OpenAI card, and OpenAI quiz use cases.
- Save a checkpoint after each stage through `JsonLectureRepository.save()`.
- Support `dry_run`, `resume`, `include_ocr`, `time_budget_seconds`, and 3 note candidates by default.
- Add `pipeline_metadata` to `LectureRecord` with backward-compatible default `{}`.

## Decisions

- `OPENAI_API_KEY` is required before a non-dry-run auto pipeline starts.
- Subtitled lectures skip STT.
- `stt_pending` lectures include STT.
- `subtitle_unmatched` lectures are blocked in preflight and are not routed to STT automatically.
- OCR is excluded by default and runs only when `include_ocr` is true.
- Notes are generated first, then the best non-blocked candidate is selected for draft auto approval.
- Auto approval uses `approval_mode=auto_best_candidate`; it is not a human golden approval.

## Validation

- `tests/test_auto_pipeline.py` covers dry-run, STT skip/include routing, OCR opt-in, preflight block, resume, time budget partial state, and blocked note candidate handling.
- `python -m unittest discover -s tests -p test_auto_pipeline.py` passed.
- `python -m compileall lecturedigest tests` passed during implementation.

## Result

- Implemented `process_lecture_with_auto_ai()`.
- Implemented plan formatting for CLI dry-runs.
- Added stage metadata and checkpoint behavior.
- Remaining actual paid API smoke validation is tracked in plan 25.

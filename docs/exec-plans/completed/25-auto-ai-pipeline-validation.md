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
- A real paid OpenAI smoke test completed with a tiny subtitle-backed lecture:
  - Lecture id: `lec_1ba2d656846f`
  - Completed steps: correction, chunk, index, notes, auto approval, cards, quizzes
  - Output counts: 3 note candidates, 8 cards, 6 quizzes
  - Validation record: `docs/validation/auto-ai-pipeline-smoke-2026-05-01.md`
- A real paid OpenAI STT smoke test completed with a tiny no-subtitle lecture:
  - Lecture id: `lec_5b7505cd8ea1`
  - Completed steps: STT, correction, chunk, index, notes, auto approval, cards, quizzes
  - Transcript source changed from `stt_pending` to `stt`
  - Output counts: 6 STT segments, 3 note candidates, 8 cards, 6 quizzes
  - Validation record: `docs/validation/auto-ai-pipeline-stt-smoke-2026-05-01.md`
- A real Streamlit click-through completed with the auto AI checkbox enabled:
  - Lecture id: `lec_23e7187d5980`
  - UI confirmed `Include OCR` starts disabled and is enabled after auto AI opt-in
  - UI confirmed the external data boundary notice appears before registration
  - Final UI state displayed `Streamlit Auto AI Smoke (quizzes_ready)`
  - Output counts: 3 note candidates, 8 cards, 6 quizzes
  - Validation record: `docs/validation/auto-ai-pipeline-streamlit-ui-2026-05-01.md`
- A real paid OpenAI large-media smoke test validated the >25MB split STT path:
  - Lecture id: `lec_175a02f179a6`
  - Input file size: 320,541,502 bytes
  - Duration: 2,181.912 seconds
  - Split audio chunks: 4
  - STT calls: 4 succeeded
  - Segment count: 219
  - Chunk count: 30
  - Search index entries: 30
  - Validation record: `docs/validation/auto-ai-pipeline-large-media-2026-05-01.md`
- Large-media validation surfaced and fixed two reliability issues:
  - Windows ffprobe output is now read as UTF-8 so Korean paths do not fail with `UnicodeDecodeError`.
  - STT calls now use a transcription-specific 600 second timeout instead of the general 60 second timeout.
- Auto pipeline failure handling was tightened so failed STT does not get marked as a completed `transcribe` step.

## Validation Not Completed

- Full large-media automatic pipeline completion through cards and quizzes is not completed yet.
- The large lecture stopped at `auto_approve_note` because all generated note candidates were blocked by note validation.

## Result

- Implementation passed dry-run, fake-client validation, one small subtitle-backed paid OpenAI smoke test, one small no-subtitle STT paid OpenAI smoke test, one Streamlit UI click-through, and one large-media split STT paid OpenAI smoke test.
- Status remains `Partial` until long-lecture note generation produces at least one auto-approvable candidate and the large-media pipeline reaches cards and quizzes.

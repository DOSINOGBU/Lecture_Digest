# Auto AI Pipeline Large Media Validation - 2026-05-01

## Summary

Ran a real paid OpenAI validation against a 25MB+ lecture to verify that automatic processing routes through the large-media split STT path.

The large-media transcription path succeeded after two reliability fixes:

- ffprobe/ffmpeg text output is read as UTF-8 on Windows paths with Korean characters.
- OpenAI STT calls use a transcription-specific 600 second timeout instead of the general 60 second timeout.

## Test Input

- Lecture id: `lec_175a02f179a6`
- Title: `Large Media Auto AI Smoke`
- Input file: local 320,541,502 byte mp4
- Duration: 2,181.912 seconds
- Resolution: 1920x1080
- Subtitle: none
- OCR: disabled
- Command:

```powershell
python -m lecturedigest process-lecture --lecture-id lec_175a02f179a6 --openai --resume --time-budget-seconds 2400
```

## Result

- Final pipeline status: `failed`
- Failed step: `auto_approve_note`
- Failure code: `auto_note_candidate_blocked`
- Transcription result: succeeded
- Transcript source after STT: `stt`
- STT provider: `openai_transcriptions`
- STT model: `gpt-4o-transcribe-diarize`
- Split audio chunks: 4
- STT calls: 4 succeeded
- STT call durations: 183,577 ms, 187,806 ms, 194,342 ms, 121,179 ms
- Segment count: 219
- Chunk count: 30
- Search index entries: 30
- Note candidates: 3
- Cards: 0
- Quizzes: 0

## Completed Steps

- `transcribe`
- `finalize_transcript`
- `chunk`
- `index`
- `generate_notes`

## Blocked Step

The pipeline correctly stopped at `auto_approve_note` because all generated note candidates were blocked by validation.

Candidate validation failures included:

- `body_too_short`
- `topic_body_too_shallow`
- `unsupported_acronym_expansion`

Warnings included:

- `missing_flow_diagram`
- `missing_comparison_table`
- `coverage_too_sparse`

## Observations

- The >25MB input was not uploaded directly.
- The media preflight detected split-required status and extracted four local audio chunks.
- The chunk paths were not persisted in metadata; only safe chunk names and sizes were recorded.
- The STT timeout issue observed in the first attempt did not recur after the 600 second STT timeout fix.
- The auto pipeline no longer marks `transcribe` complete when STT fails; failed STT now stops the pipeline at the transcribe step.
- A resume attempt with the blocked note candidates preserved `time_budget_seconds=2400.0` in failure metadata.
- The remaining blocker is note quality on long real lectures, not large-media routing.

## Remaining Validation

- Improve long-lecture note generation so at least one candidate passes the auto-approval gate.
- Re-run the same lecture until the pipeline proceeds through cards and quizzes.

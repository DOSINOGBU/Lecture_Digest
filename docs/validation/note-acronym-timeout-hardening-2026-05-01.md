# Note Acronym And Timeout Hardening Validation

Date: 2026-05-01

## Scope

Validated the 18e note generation hardening work:

- Known acronym expansion metadata.
- Unknown acronym expansion rejection.
- OpenAI prompt v6 acronym rules.
- Candidate checkpoint, resume, candidate limit, and time budget handling.

## Timeout Analysis

The timeout happened because OpenAI note generation could run a long sequential chain:

- 3 initial candidate calls.
- Up to 5 repair attempts per candidate when configured that way.
- Up to 240 seconds per OpenAI call.
- Results saved only after the whole workflow finished.

That means a full run could exceed the command execution window and lose candidates that had already succeeded.

## Fix Summary

- Save partial records after each successful candidate generation.
- Export previews during checkpoint saves when `--export-preview-dir` is provided.
- Add `--resume` to skip already completed variants for the same model, prompt version, and source hash.
- Add `--candidate-limit` and `--variant` to run one candidate safely.
- Add `--time-budget-seconds` to stop before a long command window is exhausted.
- Store `note_metadata.generation_progress` for completed, pending, failed, skipped, and partial state.

## Automated Validation

- `python -m unittest discover -s tests` -> 208 tests OK.
- `python -m compileall lecturedigest tests` -> OK.
- `python -m lecturedigest generate-notes --help` -> new `--variant`, `--candidate-limit`, `--resume`, and `--time-budget-seconds` options shown.
- `python -m lecturedigest --store .lecturedigest/e2e-real-lecture-validation.json generate-notes --lecture-id lec_3f51e7be057c --openai --dry-run --repair --max-repair-attempts 1 --variant balanced --candidate-limit 1 --resume --time-budget-seconds 840` -> one OpenAI note request planned, `willUpload=false`, `willSave=false`.
- `git diff --check` -> OK. Git reported LF-to-CRLF working-copy notices only.
- `powershell -ExecutionPolicy Bypass -File scripts/validate-harness.ps1 -Mode Project` -> errors 0, warnings 0.
- `powershell -ExecutionPolicy Bypass -File scripts/validate-harness.ps1 -CodeHealth -Mode Project` -> errors 0, warnings 0 after splitting progress/checkpoint logic into `openai_note_progress.py` and deduplicating repeated test lines.

## Manual Validation

Recommended smoke command:

```powershell
python -m lecturedigest --store .lecturedigest/e2e-real-lecture-validation.json generate-notes --lecture-id lec_3f51e7be057c --openai --repair --max-repair-attempts 1 --variant balanced --candidate-limit 1 --resume --time-budget-seconds 840 --export-preview-dir .lecturedigest/note-previews/18e-gpt41-balanced
```

Expected result:

- One balanced candidate is saved or resumed.
- Preview Markdown is written even if later candidates are not run.
- `generation_progress` records completed and pending variants.
- Visible Markdown does not show segment IDs or timestamps.
- Known acronyms such as HTML, CSS, DOM, API, and UI have beginner-friendly explanations when present in source-backed note content.

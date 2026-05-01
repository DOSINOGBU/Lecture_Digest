# 24. Register Auto AI Opt-In

## Status

Completed

## Goal

Connect the auto AI pipeline to CLI and Streamlit registration flows without making paid API calls by default.

## Scope

- Add `process-lecture --lecture-id ... --openai` CLI.
- Add `--auto-ai`, `--include-ocr`, and `--time-budget-seconds` to `register`.
- Add `--auto-ai`, `--include-ocr`, and `--time-budget-seconds` to `register-folder`.
- Add Streamlit registration checkboxes for auto AI and OCR opt-in.
- Show API-key warnings and external data boundary notes in the Streamlit registration panel.

## Decisions

- Registration alone remains free/local.
- `register --auto-ai` and `register-folder --auto-ai` run the orchestrator immediately after registration.
- Folder registration handles each clip independently; a blocked clip does not automatically route to STT.
- Streamlit blocks auto AI execution when `OPENAI_API_KEY` is missing.
- Pipeline metadata is visible in the Streamlit status metadata panel.

## Validation

- `tests/test_cli.py` covers `process-lecture --dry-run --openai` and missing `--openai`.
- `python -m unittest discover -s tests -p test_cli.py` passed.
- `python -m lecturedigest --help` shows `process-lecture`.
- `python -m lecturedigest process-lecture --help` shows pipeline options.
- Streamlit import/smoke is tracked in plan 25.

## Result

- CLI opt-in path is implemented.
- Streamlit registration opt-in path is implemented.
- Paid execution still requires explicit user action and an API key.

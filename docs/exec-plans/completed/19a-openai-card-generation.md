# 19a. OpenAI Card Generation

## Status

Completed.

## Goal

Add an opt-in OpenAI path for generating Anki card candidates directly from approved learning notes while preserving the local card generator as the offline fallback.

## Scope

- Add `generate-cards --openai` with dry-run, resume, time-budget, and section-batch controls.
- Use approved note sections and source segment snippets as the OpenAI input.
- Parse OpenAI JSON card responses into the existing card/export shape.
- Reuse existing card validation and flagged-card export behavior.
- Do not automatically fall back to local cards when OpenAI generation fails.

## Steps

- [x] Add OpenAI card prompt/request builder for Responses API.
- [x] Add OpenAI card response parser.
- [x] Add batch-based OpenAI card generator with checkpoint, resume, partial, and dry-run support.
- [x] Extend `generate-cards` CLI with `--openai`, `--dry-run`, `--resume`, `--time-budget-seconds`, and `--batch-size-sections`.
- [x] Keep local `generate-cards` behavior available without `--openai`.
- [x] Add tests for dry-run, successful AI card generation, missing source mapping, visible source artifacts, duplicate removal, resume, partial timeout, and retryable OpenAI failure metadata.

## Validation

- `python -m unittest discover -s tests`
- `python -m compileall lecturedigest tests`
- `git diff --check`
- `powershell -ExecutionPolicy Bypass -File scripts/validate-harness.ps1 -Mode Project`
- `powershell -ExecutionPolicy Bypass -File scripts/validate-harness.ps1 -CodeHealth -Mode Project`

## Result

Completed.

- Added an OpenAI card generation path using the existing `OpenAIClient` and Responses API request shape.
- AI generation is opt-in through `generate-cards --openai`; local generation remains the default.
- Dry-run reports external data boundary and input size without saving.
- Batch checkpointing, resume, and partial state metadata are recorded in `card_metadata.generation_progress`.
- OpenAI-generated cards flow through the same validator and Anki TSV/JSON export behavior as local cards.

# 18e. Acronym Expansion And Note Generation Timeout Hardening

## Status

Completed on 2026-05-01.

## Goal

Make generated study notes friendlier for beginners by expanding known acronyms, and make OpenAI note generation resilient to long-running candidate and repair workflows.

## Scope

- Add a known-acronym glossary for common technical acronyms such as HTML, CSS, DOM, API, UI, URL, HTTP, JSON, OCR, STT, RAG, LLM, and CLI.
- Preserve source traceability in metadata while keeping rendered Markdown free of visible segment IDs and timestamps.
- Move the OpenAI note prompt to `openai-markdown-note-prd-v6`.
- Save OpenAI note candidates after each successful candidate generation.
- Add resume, candidate limit, single-variant, and time-budget controls to `generate-notes`.
- Keep repair bounded so repair timeout does not erase already generated candidates.

## Decisions

- Known acronyms must include `expanded_form`, `expansion_known=true`, `plain_explanation`, and `source_segment_ids` in `notes.difficulty_explanations`.
- Unknown acronyms must not receive invented full names. They must use `expansion_known=false` and an empty `expanded_form`.
- Checkpoint saves use the existing lecture repository and optional preview export directory.
- A run can finish as `note_candidates_partial` when the time budget is exhausted, a variant fails, or not all requested variants are complete.
- `--resume` skips variants already saved for the same model, prompt version, and source hash.

## Changes

- Extended difficulty detection and validation with acronym metadata and failure flags:
  - `acronym_explanation_missing`
  - `unsupported_acronym_expansion`
- Updated local fallback explanations to reuse acronym metadata.
- Added OpenAI prompt and repair prompt rules for acronym expansion.
- Added `generate-notes` options:
  - `--variant balanced|concept_focused|action_focused`
  - `--candidate-limit N`
  - `--resume`
  - `--time-budget-seconds`
- Added generation progress metadata:
  - requested, completed, pending, failed, and skipped variants
  - call count and call metadata
  - time budget state
  - max possible call count

## Timeout Root Cause

The previous flow generated all three candidates sequentially, then optionally ran repairs sequentially. With `--max-repair-attempts 5`, worst case could reach 18 OpenAI calls. Each call could wait up to 240 seconds, while command execution can be interrupted around the 15-minute mark. Because candidates were only saved at the end, a timeout could lose already completed work.

## Validation

- Unit coverage was added for acronym metadata, unsupported acronym expansion, candidate limit, checkpoint save, resume skip, and time-budget partial state.
- Required repository validation is tracked in `docs/validation/note-acronym-timeout-hardening-2026-05-01.md`.

## Follow-Up

- Run a real OpenAI smoke test with `--variant balanced --candidate-limit 1 --resume` before using the output as a golden note.
- Continue to 19 only after the user reviews and approves at least one generated note candidate.

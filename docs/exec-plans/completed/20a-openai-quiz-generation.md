# 20a. OpenAI Quiz Generation

## Status

Completed.

## Goal

Add an opt-in OpenAI quiz generation path that produces quiz candidates from the approved note and ready cards, then passes those candidates through the local validator.

## Scope

- Add `generate-quizzes --openai`.
- Use `gpt-4.1` by default.
- Use prompt version `openai-quiz-prd-v1`.
- Input only approved note sections and ready cards.
- Generate `multiple_choice` and `written` questions.
- Preserve `source_note_candidate_id`, `source_card_ids`, `source_segment_ids`, timestamps, and jump links.
- Keep source/timestamp text out of visible questions.
- Add `--dry-run`, `--resume`, `--time-budget-seconds`, and batch checkpoint behavior.

## Out Of Scope

- Quiz session lifecycle.
- AI grading of user answers.
- Streamlit quiz UI.

## Steps

- [x] Add OpenAI quiz prompt builder and JSON parser.
- [x] Add batch/checkpoint generator with resume support.
- [x] Route `generate-quizzes --openai` through the OpenAI path.
- [x] Reuse local quiz validation for parsed AI output.
- [x] Record provider, model, prompt version, generation progress, retryable failures, and partial status.
- [x] Add tests for dry-run, parser, resume, timeout, source mapping, duplicate removal, and retryable failures.

## Validation

- `python -m unittest discover -s tests -p "test_openai_quizzes.py"` passed.
- `python -m unittest discover -s tests -p "test_quiz*.py"` passed.
- Full required validation should be run before commit.

## Result

Implemented opt-in OpenAI quiz generation.

- `generate-quizzes --openai` now uses the existing OpenAI Responses client.
- Default model is `gpt-4.1`; default prompt version is `openai-quiz-prd-v1`.
- Dry-run reports the external data boundary and does not save.
- Batch generation supports checkpointing, resume, time budget partial state, and retryable failure metadata.
- AI response parsing preserves source note, card ids, segment ids, timestamps, jump links, model, prompt version, and provider metadata.
- Parsed AI items reuse local quiz validation, duplicate removal, and ready/flagged status rules.
- Follow-up quiz session and AI rubric grading remain in `20b`.

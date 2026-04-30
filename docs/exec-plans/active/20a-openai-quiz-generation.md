# 20a. OpenAI Quiz Generation

## Status

Ready.

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

- [ ] Add OpenAI quiz prompt builder and JSON parser.
- [ ] Add batch/checkpoint generator with resume support.
- [ ] Route `generate-quizzes --openai` through the OpenAI path.
- [ ] Reuse local quiz validation for parsed AI output.
- [ ] Record provider, model, prompt version, generation progress, retryable failures, and partial status.
- [ ] Add tests for dry-run, parser, resume, timeout, source mapping, duplicate removal, and retryable failures.

## Validation

- `python -m unittest discover -s tests`
- `python -m compileall lecturedigest tests`
- `git diff --check`
- `powershell -ExecutionPolicy Bypass -File scripts/validate-harness.ps1 -Mode Project`
- `powershell -ExecutionPolicy Bypass -File scripts/validate-harness.ps1 -CodeHealth -Mode Project`

## Assumptions

- OpenAI quiz generation is opt-in.
- Local generation remains the offline fallback.
- Actual API smoke testing is manual and uses the approved golden note/card sample.

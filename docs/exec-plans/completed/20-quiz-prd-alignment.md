# 20. Quiz PRD Alignment

## Status

Completed.

## Goal

Align the existing local quiz generator with the quiz PRD before adding OpenAI quiz generation or session grading.

## Scope

- Require an approved note before quiz generation.
- Prefer ready Anki cards as quiz inputs.
- Exclude flagged and rejected cards.
- Fall back to approved note sections only when ready cards are insufficient.
- Keep source/timestamp data in metadata, not visible question text.
- Apply adaptive quiz counts from note size and profile.
- Strengthen local validation for multiple-choice and written questions.

## Out Of Scope

- OpenAI quiz generation.
- Quiz session lifecycle.
- AI rubric grading.
- Streamlit quiz workflow changes.

## Steps

- [x] Replace the blocked PRD placeholder with executable quiz PRD alignment scope.
- [x] Add adaptive quiz count policy.
- [x] Add quiz validation helpers.
- [x] Update local quiz generation to use ready cards first and approved note sections as fallback.
- [x] Update CLI output to show ready/flagged counts, source, strategy, and target quiz count.
- [x] Add regression tests for card inputs, flagged exclusion, fallback, source mapping, seed behavior, and adaptive counts.

## Validation

- `python -m unittest discover -s tests -p "test_quiz*.py"` passed.
- Full required validation should be run before commit.

## Result

Implemented local quiz PRD alignment.

- `generate-quizzes` now treats approved note as required and ready cards as the preferred source.
- Flagged/rejected cards are excluded from quiz inputs.
- Approved note sections fill gaps when ready cards do not provide enough quiz candidates.
- Adaptive quiz count policy now supports `tiny`, `compact`, `short`, `standard`, `expanded`, and `chaptered` profiles.
- Quiz metadata records generation plan, selected source (`approved_note`, `ready_cards`, or `mixed`), removed duplicate count, ready count, and flagged count.
- Quiz validation now catches missing source mapping, invalid multiple-choice shape, missing written rubric/answer, visible source artifacts in questions, broad questions, and answer leakage.
- Follow-up OpenAI generation and quiz session grading are split into `20a` and `20b`.

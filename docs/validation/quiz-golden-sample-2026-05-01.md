# Quiz Golden Sample Validation - 2026-05-01

## Decision

The user selected quiz candidate set 3 as the golden quiz sample for the browser understanding lecture.

## Source

- Lecture: `lec_3f51e7be057c`
- Source candidate set: `.lecturedigest/quiz-candidate-sets/20a-gpt41-standard/set-3-preview.md`
- Golden local preview: `.lecturedigest/quiz-candidate-sets/20a-gpt41-standard/golden-set-3-preview.md`
- Golden local JSON: `.lecturedigest/quiz-candidate-sets/20a-gpt41-standard/golden-set-3-quizzes.json`

The local `.lecturedigest` files are not committed because they are generated learning artifacts.

## Hardening Applied

- Reassigned all golden quiz IDs to remove duplicate IDs.
- Randomized multiple-choice answer labels.
- Recomputed `correct_answer` after choice shuffling.
- Preserved source metadata on each quiz item.
- Kept source segment IDs and timestamps out of visible questions.

## Result

| Metric | Value |
| --- | ---: |
| Total questions | 35 |
| Ready questions | 35 |
| Flagged questions | 0 |
| Multiple choice | 26 |
| Written | 9 |
| Duplicate quiz IDs | 0 |

Answer distribution after hardening:

| Label | Count |
| --- | ---: |
| A | 5 |
| B | 8 |
| C | 5 |
| D | 8 |

## Code Hardening

OpenAI quiz parsing now:

- Adds a stable hash suffix to generated quiz IDs.
- Shuffles multiple-choice choices deterministically.
- Recomputes `correct_answer` from the shuffled `is_correct` choice.

## Remaining Review

- Human review still needs to confirm question clarity and conceptual coverage.
- If only a few questions are weak, curate the golden sample instead of regenerating the whole set.

## Combined Source Of Truth Update

Set 3 remains the hardened golden source, but it is not the only quiz review source.
The official review pool is now the combined manifest:

- `docs/golden-samples/quiz-browser-understanding-combined.json`

That manifest keeps both source streams:

- `legacy_e2e`: 8 existing quiz items from `.lecturedigest/e2e-real-lecture-validation.json`
- `golden_set_3`: 35 hardened quiz items from `.lecturedigest/quiz-candidate-sets/20a-gpt41-standard/golden-set-3-store.json`

UI review and 22 revalidation should use the combined 43-question pool and preserve the source badge for each item.

# 20c. Quiz Golden Sample Hardening

## Status

Completed.

## Goal

Select quiz candidate set 3 as the golden quiz sample and harden quiz generation so multiple-choice answers are not pinned to option A.

## Scope

- Treat generated quiz set 3 as the approved golden quiz sample.
- Preserve source metadata while keeping source/timestamp text out of visible questions.
- Randomize multiple-choice answer labels in the golden sample.
- Make generated OpenAI quiz IDs more collision-resistant.
- Randomize OpenAI multiple-choice choice order during parsing for future generations.

## Out Of Scope

- Rewriting quiz questions by hand.
- Changing quiz count policy.
- Adding Streamlit review UI.

## Steps

- [x] Record user selection of set 3 as the golden sample.
- [x] Create a hardened local golden sample export from set 3.
- [x] Reassign golden sample quiz IDs to remove duplicate IDs.
- [x] Shuffle multiple-choice choices and recompute `correct_answer`.
- [x] Update OpenAI quiz parsing so future multiple-choice choices are deterministically shuffled.
- [x] Add parser tests for answer label randomization and similar-question quiz ID uniqueness.

## Validation

- `python -m unittest discover -s tests -p "test_openai_quizzes.py"`
- Full validation should be run before commit.

## Result

- Local golden sample files were written under `.lecturedigest/quiz-candidate-sets/20a-gpt41-standard/`.
- Golden sample selected set: `set-3`.
- Golden sample total questions: 35.
- Golden sample ready questions: 35.
- Golden sample flagged questions: 0.
- Golden sample multiple-choice questions: 26.
- Golden sample written questions: 9.
- Duplicate quiz IDs after hardening: 0.
- Multiple-choice answer distribution after hardening: A=5, B=8, C=5, D=8.
- Future OpenAI quiz parsing now appends a stable hash suffix to generated quiz IDs and shuffles multiple-choice choices with a deterministic seed.

## Follow-Up

- Use the hardened golden sample as the baseline for quiz quality review.
- If the user rejects individual questions, add a small curation pass rather than regenerating the entire set.

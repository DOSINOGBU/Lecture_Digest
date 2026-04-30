# 20b. Quiz Session And AI Rubric Grading

## Status

Completed.

## Goal

Add a quiz session workflow so users can take a randomized quiz, submit answers, and receive AI rubric feedback for written questions.

## Scope

- Add `start-quiz-session`.
- Add `submit-quiz-answer`.
- Add `grade-quiz-session --openai`.
- Use generated ready quiz items only.
- Mix multiple-choice and written questions by seed.
- Store session status, answers, score, feedback, and grading metadata.
- Use AI rubric grading for written answers.

## Out Of Scope

- OpenAI quiz item generation.
- Streamlit quiz UI.
- External LMS export.

## Steps

- [x] Define quiz session payloads inside `LectureRecord.quiz_metadata` or a dedicated compatible field.
- [x] Add CLI commands for starting sessions and submitting answers.
- [x] Implement deterministic random ordering with seed support.
- [x] Auto-grade multiple-choice answers locally.
- [x] Add OpenAI rubric grading for written answers.
- [x] Store model, prompt version, source question ids, feedback, score, and retryable failure metadata.
- [x] Add loading, empty, success, and error states in CLI output.

## Validation

- `python -m unittest discover -s tests`
- `python -m compileall lecturedigest tests`
- `git diff --check`
- `powershell -ExecutionPolicy Bypass -File scripts/validate-harness.ps1 -Mode Project`
- `powershell -ExecutionPolicy Bypass -File scripts/validate-harness.ps1 -CodeHealth -Mode Project`

## Result

- Added quiz session state under `LectureRecord.quiz_metadata.sessions`.
- Added `start-quiz-session`, `submit-quiz-answer`, and `grade-quiz-session --openai`.
- Multiple-choice answers are graded locally at submit time.
- Written answers are kept as `pending_ai_grading` until OpenAI rubric grading runs.
- OpenAI grading stores model, prompt version, call metadata, retryable failure details, score, feedback, and rubric results.
- CLI output includes start, empty, success, and error states.

## Assumptions

- Session grading is learning feedback, not exam-grade scoring.
- Written grading requires explicit `--openai`.
- Streamlit will consume the stored session state later.

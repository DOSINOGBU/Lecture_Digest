# 20b. Quiz Session And AI Rubric Grading

## Status

Ready.

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

- [ ] Define quiz session payloads inside `LectureRecord.quiz_metadata` or a dedicated compatible field.
- [ ] Add CLI commands for starting sessions and submitting answers.
- [ ] Implement deterministic random ordering with seed support.
- [ ] Auto-grade multiple-choice answers locally.
- [ ] Add OpenAI rubric grading for written answers.
- [ ] Store model, prompt version, source question ids, feedback, score, and retryable failure metadata.
- [ ] Add loading, empty, success, and error states in CLI output.

## Validation

- `python -m unittest discover -s tests`
- `python -m compileall lecturedigest tests`
- `git diff --check`
- `powershell -ExecutionPolicy Bypass -File scripts/validate-harness.ps1 -Mode Project`
- `powershell -ExecutionPolicy Bypass -File scripts/validate-harness.ps1 -CodeHealth -Mode Project`

## Assumptions

- Session grading is learning feedback, not exam-grade scoring.
- Written grading requires explicit `--openai`.
- Streamlit will consume the stored session state later.

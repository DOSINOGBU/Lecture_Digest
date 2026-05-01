# Real Lecture Quality Revalidation - 2026-05-01

## Scope

- Plan: `docs/exec-plans/completed/22-real-lecture-quality-revalidation.md`
- Main lecture: `lec_3f51e7be057c`
- Source store: `.lecturedigest/e2e-real-lecture-validation.json`
- Result: `Partial`

## Inputs

- Note source: approved OpenAI note candidate in the E2E store
- Card source of truth: `docs/golden-samples/card-browser-understanding-set-3.json`
- Quiz source of truth: `docs/golden-samples/quiz-browser-understanding-combined.json`
- Streamlit UI: `http://localhost:8501`

## Note Revalidation

Command:

```powershell
python -m lecturedigest --store .lecturedigest\e2e-real-lecture-validation.json inspect-note-quality --lecture-id lec_3f51e7be057c
```

Observed:

- Candidates inspected: 3
- Overall status: `needs_review`
- Review ready: 0
- Needs review: 2
- Blocked: 1
- Visible source artifacts: 0
- Source mapping gaps: 0
- Approved candidate: `note-candidate-openai-25fc9d1376-03`
- Approved candidate validation: `review_required`
- Approved candidate failed rules: none

Approved note warnings:

- `missing_flow_diagram`
- `missing_comparison_table`
- `missing_code_block`
- `coverage_too_sparse`

Decision:

- Note status is `Partial`.
- The approved note is usable for review, but it should not be promoted to a clean golden note until warnings are fixed or intentionally waived.

## Card Revalidation

Source:

```text
docs/golden-samples/card-browser-understanding-set-3.json
```

Observed:

- Ready cards: 42
- Excluded flagged cards: 1
- Excluded reason: `bad_cloze`
- Duplicate ID excess: 0
- Source mapping missing: 0
- Visible source artifacts in card front/back/cloze: 0
- Anki TSV exists: yes
- Type counts: `qa=29`, `cloze=11`, `application=2`, `code=0`

Decision:

- Card manifest/count/source checks passed.
- Human memorization usefulness spot-check remains recommended before final golden promotion.

## Quiz Revalidation

Source:

```text
docs/golden-samples/quiz-browser-understanding-combined.json
```

Observed:

- Combined quiz items: 43
- `legacy_e2e`: 8
- `golden_set_3`: 35
- Duplicate ID excess: 0
- Source mapping missing: 0
- Visible source artifacts in question text: 0
- Visible source artifacts in explanation: 8, all from `legacy_e2e`
- Multiple-choice answer distribution: `A=5`, `B=8`, `C=7`, `D=10`

Decision:

- Quiz combined source/count/badge checks passed.
- Legacy explanations still contain source text artifacts, so UI should avoid treating explanation text as polished learner-facing content until reviewed.

## Streamlit Review Check

Command:

```powershell
Invoke-WebRequest -Uri http://localhost:8501 -UseBasicParsing -TimeoutSec 10
```

Observed:

- HTTP status: 200
- The endpoint is reachable.

Decision:

- Server smoke passed.
- Full browser visual review was not performed in this automated pass.

## Tiny Or Short Sample

Observed:

- Current `.lecturedigest/lectures.json` contains newly registered transcript-only lectures.
- Those lectures do not yet have AI note/card/quiz outputs.

Decision:

- Tiny/short end-to-end quality revalidation is not run in this pass.
- Follow-up requires one short lecture to complete AI note/card/quiz generation or an explicitly approved synthetic fixture.

## Overall Decision

- Overall status: `Partial`
- Blocking failures for approved note/card/quiz source checks: none
- Remaining warning-level items:
  - Approved note still has four documented quality warnings.
  - Legacy quiz explanations expose source artifacts.
  - Tiny/short sample revalidation is still pending.

# 20d. Quiz Combined Source Of Truth

## Status

Completed on 2026-05-01.

## Goal

Make the official quiz review pool unambiguous by combining the legacy E2E quiz output and the hardened golden set 3 output through a committed manifest.

## Decisions

- Source policy: `combined_manifest`.
- Dedupe policy: `keep_all_tagged`.
- The combined review pool keeps all 43 questions:
  - 8 questions from `.lecturedigest/e2e-real-lecture-validation.json`.
  - 35 questions from `.lecturedigest/quiz-candidate-sets/20a-gpt41-standard/golden-set-3-store.json`.
- The source badge for the E2E questions is `legacy_e2e`.
- The source badge for the hardened golden questions is `golden_set_3`.
- The generated `.lecturedigest` artifacts are not rewritten and are not committed.

## Steps

- [x] Confirm the E2E store still contains 8 local quiz items.
- [x] Confirm the hardened golden set 3 store contains 35 quiz items.
- [x] Add a committed combined manifest under `docs/golden-samples/`.
- [x] Update quiz golden validation notes to explain the combined pool role.
- [x] Update 21 UI and 22 revalidation plans to use the combined manifest.
- [x] Run manifest count validation.

## Validation

- Combined manifest: `docs/golden-samples/quiz-browser-understanding-combined.json`.
- Validation record: `docs/validation/quiz-combined-source-of-truth-2026-05-01.md`.
- Full command validation is reported in the implementation handoff.

## Result

- The official quiz review source of truth is now the combined manifest.
- UI and quality revalidation should inspect 43 questions total.
- The two source streams remain traceable through source badges instead of being physically merged into one generated store.

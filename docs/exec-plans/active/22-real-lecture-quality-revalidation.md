# 22. 실제 강의 품질 재검증

## 상태

대기

## 목표

강의노트, 카드, 퀴즈, 검토 워크플로우 PRD 반영이 끝난 뒤 실제 산출물 품질을 다시 검증한다.

## 범위

- 최소 하나의 tiny 또는 short 강의 샘플과 약 25분 강의 샘플 하나를 검증한다.
- 노트 깊이, 출처 커버리지, 환각 위험, OCR 사용 여부, Anki 전환 가능성, 퀴즈 유용성을 확인한다.
- 저장소에는 승인된 baseline 요약, 비교표, 제한된 골든 노트 샘플만 포함한다.
- 원본 영상, 전체 자막, 전체 OCR 원문, API 키, 로컬 처리 산출물은 커밋하지 않는다.

## 작업 단계

1. 샘플 입력은 저장소 밖 또는 ignored 로컬 저장소에 준비한다.
2. 입력, STT/자막 import, OCR enrichment, 교정, RAG, 노트, 카드, 퀴즈까지 전체 파이프라인을 실행한다.
3. 생성된 노트를 강의노트 PRD와 사람 승인 기준에 맞춰 비교한다.
4. 카드/퀴즈 PRD가 제공된 뒤에는 카드와 퀴즈도 각 PRD 기준으로 비교한다.
5. 발견한 문제, 품질 격차, 후속 작업을 validation 문서와 tech debt tracker에 기록한다.

## 검증

- `python -m unittest discover -s tests`
- `python -m compileall lecturedigest tests`
- `git diff --check`
- `powershell -ExecutionPolicy Bypass -File scripts/validate-harness.ps1 -Mode Project`
- `powershell -ExecutionPolicy Bypass -File scripts/validate-harness.ps1 -CodeHealth -Mode Project`
- 타임스탬프 커버리지와 환각 없음 기준으로 수동 품질 검토

## 열린 질문

- 골든 노트/카드/퀴즈 샘플의 최종 승인 담당자가 필요하다.
- 25분 샘플을 현재 실제 강의로 할지, 다른 대표 강의로 바꿀지 결정해야 한다.

## 20d Quiz Source Of Truth

- Quiz revalidation must use `docs/golden-samples/quiz-browser-understanding-combined.json` as the quiz source of truth.
- The expected quiz review pool is 43 total items: 8 `legacy_e2e` items plus 35 `golden_set_3` items.
- Revalidation should report combined metrics and source-level breakdowns.
- The existing E2E store quiz list is only one source in the combined pool, not the complete quiz baseline.

## 18f Note Revalidation Gate

- Note revalidation must run or reproduce `inspect-note-quality` for the real lecture.
- The current approved note is expected to be `needs_review`, not clean pass.
- Known warning flags must be recorded explicitly:
  - `missing_flow_diagram`
  - `missing_comparison_table`
  - `missing_code_block`
  - `coverage_too_sparse`
- Revalidation should separate blocking failures from warning-level waivers.
- A clean golden-note promotion requires either fixing or intentionally waiving those warnings.

## 19b Card Revalidation Source

- Card revalidation must use `docs/golden-samples/card-browser-understanding-set-3.json`.
- The expected card review pool is 42 ready cards.
- The excluded flagged card count is 1, with reason `bad_cloze`.
- Revalidation should report type breakdown, source mapping gaps, visible source artifacts, and Anki TSV availability.
- Human spot-check should review whether the 42 ready cards are actually useful for memorization.

## Pass And Partial Criteria

- Note: `Partial` is acceptable if the approved note has no blocking failures but still has documented warning flags.
- Cards: `Passed` requires 42 ready cards, 0 duplicate IDs, 0 source mapping gaps, and 0 visible source artifacts.
- Quiz: `Passed` requires the combined 43-item manifest counts to match both sources and source badges to remain distinguishable.
- Overall lecture revalidation should be `Partial` if any of note, card, or quiz criteria remain warning-only but not blocking.

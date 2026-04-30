# Plan: End-To-End Real Lecture Validation

## Goal

실제 강의 1개를 사용해 입력, STT/OCR, 교정, RAG, 노트, Anki, 퀴즈까지 전체 흐름을 검증하고 MVP 품질 기준을 확인한다.

## Scope

- 원본 영상, 전체 자막, 전체 OCR 원문은 저장소에 포함하지 않는다.
- baseline/비교표와 일부 승인된 골든 노트 샘플만 저장소에 포함한다.
- 실제 OpenAI 호출은 수동 smoke test로 수행하고 비용/모델/처리 시간 metadata를 기록한다.
- 검증 기준은 출처 timestamp 100% 연결, 핵심 개념 누락 없음, 환각 없음, OCR 필요 부분 표시, Anki 전환 가능이다.
- NotebookLM은 초기 검증 범위에 포함하지 않는다.
- 결과가 기준에 미달하면 기능을 완료 처리하지 않고 후속 active 계획을 만든다.

## Steps

- [ ] 테스트할 실제 강의 파일과 자막 유무를 기록한다.
- [ ] 파일/폴더 등록부터 최종 산출물까지 수동 시나리오를 실행한다.
- [ ] STT 결과 segment, OCR slide, 교정 log, chunk, index, note, cards, quizzes를 표본 검수한다.
- [ ] 골든 노트 후보를 생성하고 사람이 승인한 샘플만 저장소 포함 대상으로 정리한다.
- [ ] baseline/비교표를 작성한다.
- [ ] 실패/누락/비용 문제를 risk backlog 또는 새 exec-plan으로 분리한다.
- [ ] active 계획이 모두 완료되었는지 확인하고 다음 Phase 계획을 제안한다.

## Validation

- 수동 시나리오 로그에 명령, 입력, 산출물 위치, 관찰 결과를 남긴다.
- 출처 timestamp 연결률을 표본이 아니라 전체 note/card/quiz 대상으로 확인한다.
- OCR이 필요한 화면 구간이 표시되는지 확인한다.
- Anki TSV/JSON export가 승인된 노트만 사용했는지 확인한다.
- 저장소에 원본 영상, 전체 자막, 전체 OCR 원문, API 키, 로컬 민감 경로가 포함되지 않는지 확인한다.
- `python -m unittest discover -s tests`
- `python -m compileall lecturedigest tests`
- `git diff --check`
- `powershell -ExecutionPolicy Bypass -File scripts/validate-harness.ps1 -Mode Project`
- `powershell -ExecutionPolicy Bypass -File scripts/validate-harness.ps1 -CodeHealth -Mode Project`

## Result

작성 전.

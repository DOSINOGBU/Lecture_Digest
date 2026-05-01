# 18a. 노트 PRD 품질 Repair

## 상태

완료

## 목표

18번에서 PRD 구조는 반영됐지만 실제 OpenAI 노트 후보 3개가 모두 `flagged`로 남았다. 19번 카드 PRD 반영으로 넘어가기 전에, 실제 강의 기준으로 사람이 읽고 승인/반려할 수 있는 최소 1개 이상의 `review_required` 후보를 만든다.

## 범위

- OpenAI 노트 생성 경로에 `generation -> validation -> repair -> revalidation` 단계를 추가한다.
- repair는 명시적으로 요청한 경우에만 실행한다.
- repair는 전체 재생성이 아니라 validation 실패 항목을 중심으로 부족한 섹션만 보강하도록 요청한다.
- 생성된 후보 Markdown을 사람이 읽을 수 있는 preview 파일로 내보낸다.
- 실제 강의 샘플의 초기 후보와 repair 후보 비교 결과를 validation 문서에 기록한다.
- 골든 노트 승인은 자동화하지 않는다.
- 카드, 퀴즈, Streamlit UI 구현은 변경하지 않는다.

## 작업 단계

1. 18번 현재 변경을 보존한 상태에서 18a 계획을 active에 추가한다.
2. OpenAI 노트 후보 validation 결과가 `flagged`이면 repair 요청을 만들 수 있는 프롬프트/요청 빌더를 추가한다.
3. repair 요청에는 content profile, 실패 규칙, 경고, 기존 후보 섹션, 사용 가능한 source chunk를 포함한다.
4. repair 응답을 기존 PRD parser와 validator로 다시 검증한다.
5. repair 전후 validation status, failed rules, warnings, counts를 metadata에 남긴다.
6. `generate-notes --openai`에 명시적 repair 옵션과 preview export 옵션을 추가한다.
7. 부족 항목별 repair trigger와 repair 후 상태 변화를 unit test로 검증한다.
8. 실제 강의 샘플로 dry-run, 실제 generation/repair, preview export를 수행한다.
9. 최소 1개 후보가 `review_required`가 되면 결과를 validation 문서에 기록하고 이 계획을 completed로 이동한다.

## 완료 기준

- 실제 강의 샘플에서 OpenAI 후보 3개를 생성한다.
- `flagged` 후보에 repair를 적용한다.
- repair 후 최소 1개 후보가 `review_required` 상태가 된다.
- 후보 Markdown preview를 로컬 출력 경로에 생성한다.
- validation report에 초기 후보와 repair 후보 비교를 기록한다.
- 골든 노트 승인은 사용자 결정으로 남긴다.

## 검증

- `python -m unittest discover -s tests`
- `python -m compileall lecturedigest tests`
- `git diff --check`
- `powershell -ExecutionPolicy Bypass -File scripts/validate-harness.ps1 -Mode Project`
- `powershell -ExecutionPolicy Bypass -File scripts/validate-harness.ps1 -CodeHealth -Mode Project`
- `powershell -ExecutionPolicy Bypass -File scripts/recommend-version-control.ps1 -VerificationStatus Passed`
- 실제 강의 `lec_3f51e7be057c` 기준 OpenAI dry-run
- 실제 OpenAI generation + repair
- preview Markdown 파일 수동 확인

## 열린 질문

- repair 후보 중 어떤 후보를 골든 노트 샘플로 승인할지는 사용자가 직접 결정한다.
- repair 품질 기준이 카드/퀴즈 PRD와 충돌하면 19번/20번에서 추가 조정한다.

## 결과

구현 완료.

- OpenAI 노트 생성에 명시적 `--repair` 옵션을 추가했다.
- `flagged` 후보는 validation 실패 규칙, warning, content profile, 기존 섹션, source chunk를 포함한 repair 요청으로 보강할 수 있다.
- repair 응답은 기존 PRD parser/validator를 다시 통과하며, repair 전후 상태와 OpenAI call metadata를 후보 metadata와 note metadata에 기록한다.
- `--export-preview-dir` 옵션으로 후보 Markdown을 사람이 읽을 수 있는 로컬 preview 파일로 내보낼 수 있다.
- 실제 강의 `lec_3f51e7be057c`에서 OpenAI generation + repair를 실행했고, 후보 3개 모두 `review_required` 상태가 됐다.
- preview 파일은 `.lecturedigest/note-previews/18a/`에 생성했다. 이 경로는 저장소에 포함하지 않는다.
- validation report는 `docs/validation/note-prd-quality-repair-2026-04-30.md`에 기록했다.
- 골든 노트 승인은 아직 사용자가 직접 결정해야 한다.

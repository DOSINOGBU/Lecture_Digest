# 20. 퀴즈 PRD 반영

## 상태

차단

## 목표

강의노트와 카드 구조 결정이 정리된 뒤, 추후 제공될 퀴즈 PRD에 맞춰 퀴즈 생성을 정렬한다.

## 차단 사유

퀴즈 PRD가 아직 제공되지 않았다.

## 범위

- 객관식과 서술형이 섞인 퀴즈 항목을 계속 지원한다.
- 모든 퀴즈 항목에 출처 타임스탬프와 segment ID를 필수로 요구한다.
- 퀴즈 개수는 강의 시간이 아니라 `estimated_tokens`에 따라 조절한다.
- 승인된 PRD 반영 노트를 소비하는 것 외에는 이 계획에서 노트 생성을 변경하지 않는다.

## 초기 적응형 정책

- `tiny`: 퀴즈 2-4개
- `short`: 퀴즈 4-6개
- `medium`: 퀴즈 6-10개
- `long`: 퀴즈 10-15개

이 범위는 퀴즈 PRD를 받기 전까지의 임시 기준이다.

## 작업 단계

1. 퀴즈 PRD가 제공되면 먼저 읽는다.
2. 현재 퀴즈 생성/미리보기 동작과 PRD 요구사항을 비교한다.
3. 필요한 경우 퀴즈 모델, 검증기, CLI 출력을 갱신한다.
4. 혼합 퀴즈 유형, 출처 메타데이터, 적응형 개수 범위 테스트를 추가한다.
5. 필요한 경우 퀴즈 생성이 승인된 노트/카드 입력만 사용하는지 검증한다.

## 검증

- `python -m unittest discover -s tests`
- `python -m compileall lecturedigest tests`
- `git diff --check`
- `powershell -ExecutionPolicy Bypass -File scripts/validate-harness.ps1 -Mode Project`
- `powershell -ExecutionPolicy Bypass -File scripts/validate-harness.ps1 -CodeHealth -Mode Project`

## 열린 질문

- 퀴즈 난이도, 해설, 채점 규칙, 재시도 동작에 대한 요구사항이 필요하다.
- 서술형 채점을 결정론적으로 할지, LLM 보조로 할지, 수동 검토로 둘지 결정해야 한다.

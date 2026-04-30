# 19. 카드 PRD 반영

## 상태

차단

## 목표

강의노트 PRD 반영이 끝난 뒤, 추후 제공될 카드 PRD에 맞춰 Anki/카드 생성을 정렬한다.

## 차단 사유

카드 PRD가 아직 제공되지 않았다.

## 범위

- 사람이 승인한 PRD 반영 노트만 카드 입력으로 사용한다.
- 내보낼 수 있는 카드에는 출처 타임스탬프와 segment ID를 필수로 유지한다.
- 카드 개수는 강의 시간이 아니라 `estimated_tokens`에 따라 조절한다.
- 이 계획에서는 퀴즈 생성을 변경하지 않는다.

## 초기 적응형 정책

- `tiny`: 카드 3-6개
- `short`: 카드 6-10개
- `medium`: 카드 10-18개
- `long`: 카드 18-30개

이 범위는 카드 PRD를 받기 전까지의 임시 기준이다.

## 작업 단계

1. 카드 PRD가 제공되면 먼저 읽는다.
2. 현재 Q&A, cloze, code 카드 동작과 PRD 요구사항을 비교한다.
3. 카드 데이터 계약과 검증 규칙을 갱신한다.
4. PRD가 필수 메타데이터를 변경하면 CLI 미리보기/내보내기 동작을 갱신한다.
5. 출처가 있는 카드, 출처 누락 거부, 적응형 개수 범위 테스트를 추가한다.

## 검증

- `python -m unittest discover -s tests`
- `python -m compileall lecturedigest tests`
- `git diff --check`
- `powershell -ExecutionPolicy Bypass -File scripts/validate-harness.ps1 -Mode Project`
- `powershell -ExecutionPolicy Bypass -File scripts/validate-harness.ps1 -CodeHealth -Mode Project`

## 열린 질문

- 카드 유형, 난이도, 태그, 내보내기 형식에 대한 카드 PRD 요구사항이 필요하다.
- 현재 TSV/JSON 브리지를 `.apkg` 또는 AnkiConnect로 대체할지 결정해야 한다.

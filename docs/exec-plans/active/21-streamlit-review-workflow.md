# 21. Streamlit 검토 워크플로우

## 상태

대기

## 목표

사용자가 PRD 반영 노트/카드/퀴즈 후보를 비교하고 명시적으로 승인할 수 있도록 Streamlit 검토 흐름을 갱신한다.

## 범위

- 노트 후보, 콘텐츠 프로필, 출처 커버리지, PRD 체크리스트 상태를 보여준다.
- 카드/퀴즈 생성 전에 노트 승인, 반려, 재생성 흐름을 지원한다.
- 비용이 발생하는 작업 전에는 외부 전송 범위와 예상 입력 크기를 표시한다.
- 로딩, 빈, 오류 상태를 포함한다.
- UI에서 새 생성 정책을 만들지 않고, 18-20번 계획의 백엔드 계약을 소비한다.

## 작업 단계

1. 현재 Streamlit 화면과 백엔드 CLI/use case 계약을 검토한다.
2. 후보 비교와 승인 상태 표시를 추가한다.
3. 노트/카드/퀴즈 산출물에 대한 PRD 체크리스트 표시를 추가한다.
4. 비용/입력 크기 경고가 있는 재생성 컨트롤을 추가한다.
5. 로딩, 빈, 오류 상태에 대한 테스트 또는 수동 검증 기록을 남긴다.

## 검증

- `python -m unittest discover -s tests`
- `python -m compileall lecturedigest tests`
- `git diff --check`
- `powershell -ExecutionPolicy Bypass -File scripts/validate-harness.ps1 -Mode Project`
- `powershell -ExecutionPolicy Bypass -File scripts/validate-harness.ps1 -CodeHealth -Mode Project`
- 앱이 실행 중이면 `http://localhost:8501/`에서 Streamlit 수동 스모크 테스트

## 열린 질문

- MVP UI에서 어떤 검토 결정까지 감사 이력으로 남길지 정해야 한다.
- 반려된 후보를 비교용으로 유지할지, 기본적으로 숨길지 결정해야 한다.

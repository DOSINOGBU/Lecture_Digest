# Plan: Streamlit Review UI

## Goal

CLI/use case 파이프라인이 안정화된 뒤, 사용자가 강의 처리 상태를 보고 노트 후보 승인, 교정 후보 검토, Anki/퀴즈 preview를 할 수 있는 Streamlit MVP UI를 만든다.

## Scope

- Streamlit은 이 계획에서 새 의존성으로 도입한다. 도입 전 `docs/DEPENDENCIES.md` 기준을 확인하고 설치/실행 문서를 함께 갱신한다.
- 첫 화면은 강의 목록 또는 강의 등록 화면이다. 마케팅형 랜딩 페이지는 만들지 않는다.
- 우선 화면은 강의 목록, 처리 상태, 노트 후보 승인, 교정 후보 검토, Anki/퀴즈 preview로 제한한다.
- 비용이 드는 작업 버튼은 실행 전 외부 전송 범위, 모델, 예상 입력 크기, dry-run 가능 여부를 보여준다.
- 로딩, 빈 상태, 오류 상태, quota/cost limit 상태를 명확히 표시한다.
- UI는 기존 use case/CLI 로직을 직접 재구현하지 않고 같은 도메인 함수를 호출한다.

## Steps

- [x] Streamlit 도입 ADR 또는 dependency 기록을 작성한다.
- [x] 앱 entrypoint와 실행 명령을 추가한다.
- [x] lecture repository를 읽어 빈 library와 lecture list 상태를 표시한다.
- [x] lecture detail에서 stage, status, issues, metadata를 표시한다.
- [x] note candidate 3개를 Markdown으로 preview하고 승인/거절 action을 연결한다.
- [x] correction review queue에서 original/corrected/confidence/reason을 보여주고 승인/거절 action을 연결한다.
- [x] Anki card와 quiz preview 화면을 추가한다.
- [x] 비용 발생 action은 confirm/dry-run 중심으로 제한한다.

## Validation

- Streamlit import 가능 여부와 실행 명령을 확인한다.
- 빈 store, 강의 없음, note 후보 없음, correction 후보 없음, API 키 없음, 오류 issue가 있는 강의를 수동 검증한다.
- 핵심 use case는 기존 unit test로 보호하고 UI는 최소 smoke/manual scenario로 검증한다.
- `python -m unittest discover -s tests`
- `python -m compileall lecturedigest tests`
- `git diff --check`
- `powershell -ExecutionPolicy Bypass -File scripts/validate-harness.ps1 -Mode Project`
- `powershell -ExecutionPolicy Bypass -File scripts/validate-harness.ps1 -CodeHealth -Mode Project`

## Result

완료.

- Streamlit 1.57.0을 `requirements.txt`에 pin하고 ADR/의존성/테스트/배포 문서에 설치 및 실행 경로를 기록했다.
- `lecturedigest/streamlit_app.py`를 로컬 리뷰 UI entrypoint로 추가했다.
- UI는 빈 라이브러리, 강의 목록, 등록 폼, 강의 상태, issues, metadata, API 키 없음, cost/quota issue를 표시한다.
- 노트 후보 Markdown preview와 승인/거절 action을 기존 note use case에 연결했다.
- 교정 review queue 승인/거절 action을 추가하고, 원문/수정안/confidence/reason을 보존해 표시한다.
- Anki 카드와 퀴즈 preview를 추가했다.
- 유료 OpenAI action은 UI에서 직접 실행하지 않고 외부 전송 범위, 모델, 예상 입력 크기, dry-run 명령만 표시한다.

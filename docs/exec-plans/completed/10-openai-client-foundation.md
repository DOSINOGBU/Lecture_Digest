# Plan: OpenAI Client Foundation

## Goal

OpenAI STT, Vision OCR, LLM correction, embedding 호출이 공통으로 사용할 BYOK 기반 외부 API 클라이언트 토대를 만든다. 이 계획은 실제 기능 호출을 모두 완성하는 단계가 아니라, 이후 계획들이 같은 인증, 로그, 오류, 비용 메타데이터 규칙을 공유하게 만드는 기반 작업이다.

## Scope

- `OPENAI_API_KEY` 환경 변수에서만 API 키를 읽는다.
- Python 신규 의존성은 추가하지 않고 표준 라이브러리 `urllib` 기반 HTTP 호출을 우선 구현한다.
- API 키, Authorization header, 원문 secret, 결제 정보, 전체 로컬 파일 경로는 로그와 저장 payload에 남기지 않는다.
- 모든 외부 호출 metadata는 provider, endpoint/use case, model, prompt_version, input size, duration_ms, status, retryable, estimated_cost 필드를 공유한다.
- 네트워크 호출은 unit test에서 fake transport로 대체 가능해야 한다.
- STT, Vision OCR, correction, embedding의 구체 호출 흐름은 이후 11, 13, 14, 15 계획에서 각각 구현한다.

## Steps

- [x] 기존 오류 모델과 로그 형식을 확인하고 외부 API 공통 오류 코드를 정한다.
- [x] API 키 로더를 만들고 키 누락 시 `openai_api_key_missing` 오류를 반환한다.
- [x] 공통 transport 인터페이스를 만든다.
- [x] 성공/실패 응답을 표준 metadata와 `ProcessingIssue`로 변환하는 헬퍼를 만든다.
- [x] retryable 상태를 timeout, 429, 5xx 중심으로 분류한다.
- [x] redaction 헬퍼를 추가해 키, Authorization, 민감 경로가 출력되지 않게 한다.
- [x] dry-run 모드에서 실제 네트워크 호출 없이 endpoint, model, input size, external data boundary를 출력하게 한다.

## Validation

- API 키 없음, 빈 API 키, fake 성공 응답, fake 429, fake 500, timeout을 unit test로 검증한다.
- 로그/metadata 문자열에 API 키와 Authorization 값이 포함되지 않는지 검증한다.
- `python -m unittest discover -s tests`
- `python -m compileall lecturedigest tests`
- `git diff --check`
- `powershell -ExecutionPolicy Bypass -File scripts/validate-harness.ps1 -Mode Project`
- `powershell -ExecutionPolicy Bypass -File scripts/validate-harness.ps1 -CodeHealth -Mode Project`

## Result

완료. `lecturedigest/openai_client.py`, `lecturedigest/openai_types.py`, `lecturedigest/openai_redaction.py`로 책임을 분리해 OpenAI 공통 클라이언트 기반을 추가했다. `OPENAI_API_KEY` 로더, `urllib` transport, fake transport 가능한 인터페이스, 표준 호출 metadata, retryable 분류, `ProcessingIssue` 변환, redaction, dry-run 출력 포맷을 구현했다. 검증은 `tests/test_openai_client.py`에서 API 키 누락/빈 값, fake 성공, fake 429, fake 500, timeout, dry-run, redaction, retryable 분류를 다룬다.

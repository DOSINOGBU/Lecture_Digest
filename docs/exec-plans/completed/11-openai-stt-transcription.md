# Plan: OpenAI STT Transcription

## Goal

`stt_pending` 강의를 실제 OpenAI Transcriptions API로 전사하고, 결과를 기존 `TranscriptSegment`와 SRT 호환 timestamp 구조로 저장한다.

## Scope

- 새 CLI 명령은 `transcribe --lecture-id <id>`로 추가한다.
- 기본 모델은 `gpt-4o-transcribe-diarize`로 둔다.
- 기본 응답 형식은 `diarized_json`, 기본 `chunking_strategy`는 `auto`로 둔다.
- 입력 파일 확장자는 OpenAI Speech-to-text 지원 범위인 mp3, mp4, mpeg, mpga, m4a, wav, webm만 허용한다.
- 25MB 초과 파일은 이 단계에서 자동 업로드하지 않고 `stt_file_too_large`로 차단한다. 긴 강의 분할은 12번 계획에서 처리한다.
- `--dry-run`은 API 호출 없이 파일 크기, 모델, 응답 형식, 외부 전송 범위, 예상 차단 여부만 출력한다.
- 자막이 이미 있는 강의나 transcript가 이미 있는 강의에는 STT를 적용하지 않는다.

## Steps

- [x] `transcribe` CLI parser와 command handler를 추가한다.
- [x] lecture 상태가 `stt_pending`인지 검증한다.
- [x] 파일 존재, 파일 확장자, 파일 크기, 읽기 가능 여부를 검증한다.
- [x] OpenAI 클라이언트 기반으로 Transcriptions API multipart 요청을 만든다.
- [x] `diarized_json` 응답을 기존 STT JSON parser 입력 형태로 정규화한다.
- [x] 성공 시 `segments`, `transcript_metadata`, status, stage를 저장한다.
- [x] 실패 시 retryable 여부와 provider metadata를 issue로 남긴다.
- [x] 빈 결과, malformed response, timestamp 역전, speaker 누락을 명확한 오류로 처리한다.

## Validation

- API 키 없음, unsupported extension, 25MB 초과, transcript already exists, non-`stt_pending` 상태를 테스트한다.
- fake diarized response가 segment id, speaker, start/end timestamp, text로 저장되는지 테스트한다.
- `--dry-run`이 저장소를 변경하지 않는지 테스트한다.
- 실제 OpenAI 호출은 수동 smoke test로 분리하고 기본 unit test에서는 fake transport를 사용한다.
- `python -m unittest discover -s tests`
- `python -m compileall lecturedigest tests`
- `git diff --check`
- `powershell -ExecutionPolicy Bypass -File scripts/validate-harness.ps1 -Mode Project`
- `powershell -ExecutionPolicy Bypass -File scripts/validate-harness.ps1 -CodeHealth -Mode Project`

## Result

완료. `stt_pending` 강의를 실제 OpenAI Transcriptions API 요청으로 전사하는
`transcribe` CLI 경로를 추가했다. direct upload preflight, multipart 요청 생성,
dry-run 출력, diarized JSON 응답 정규화, 성공 metadata 저장, provider 실패 issue
기록을 구현했다. 테스트는 API 키 없음, unsupported extension, 25MB 초과,
transcript already exists, non-`stt_pending`, fake diarized success, speaker 누락,
malformed response, dry-run 저장소 무변경을 포함한다. 실제 OpenAI 호출은 강의 파일
업로드와 비용이 발생하므로 계획대로 수동 smoke test로 남긴다.


# Plan: Media Preflight And Audio Splitting

## Goal

실제 긴 강의 파일을 STT/OCR 전에 안전하게 검사하고, OpenAI STT 25MB 제한을 넘는 입력을 로컬에서 오디오 분할 처리할 수 있게 만든다.

## Scope

- `ffprobe`로 duration, file size, video resolution, audio track 존재 여부를 확인한다.
- `ffmpeg`와 `ffprobe`가 없으면 명확한 오류와 설치 안내를 반환한다.
- STT용 오디오 추출과 분할은 로컬 임시 파일로만 만들고 저장소에 포함하지 않는다.
- 분할된 오디오의 segment timestamp는 원본 lecture timeline 기준으로 offset 보정한다.
- 이 계획은 OpenAI 호출 자체를 새로 만들지 않는다. 11번의 STT 호출 흐름에 긴 파일 지원을 연결한다.
- 영상 원본, 분할 오디오, 임시 프레임은 git 추적 대상이 아니어야 한다.

## Steps

- [x] media preflight use case를 추가한다.
- [x] ffmpeg/ffprobe 경로 탐지와 누락 오류를 구현한다.
- [x] ffprobe JSON 출력을 안전하게 파싱한다.
- [x] 오디오 트랙 없음, duration 없음, resolution 없음, 파일 읽기 불가 상태를 구분한다.
- [x] `transcribe --dry-run`에 preflight 결과를 표시한다.
- [x] 25MB 초과 입력의 분할 전략을 구현하고 각 chunk의 원본 offset metadata를 기록한다.
- [x] 분할 STT 결과를 병합할 때 timestamp를 원본 timeline으로 보정한다.
- [x] 임시 파일 삭제 실패는 warning issue로 남기고 원본 오류를 숨기지 않는다.

## Validation

- ffmpeg 없음, ffprobe 없음, 오디오 트랙 없음, 1080p 미만 영상, 25MB 이하/초과 입력을 테스트한다.
- fake ffprobe output으로 duration/resolution/audio track 파싱을 테스트한다.
- 분할 chunk offset이 최종 segment timestamp에 반영되는지 테스트한다.
- 임시 파일 경로가 저장소 payload와 로그에 과도하게 남지 않는지 확인한다.
- `python -m unittest discover -s tests`
- `python -m compileall lecturedigest tests`
- `git diff --check`
- `powershell -ExecutionPolicy Bypass -File scripts/validate-harness.ps1 -Mode Project`
- `powershell -ExecutionPolicy Bypass -File scripts/validate-harness.ps1 -CodeHealth -Mode Project`

## Result

완료. `media_preflight`에서 ffprobe 기반 duration/file size/resolution/audio
track 검증과 ffmpeg/ffprobe 경로 탐지를 추가했고, `media_transcription`에서
25MB 초과 강의를 로컬 임시 오디오 chunk로 분할한 뒤 기존 OpenAI STT 호출 경로를
재사용하도록 연결했다. `transcribe --dry-run`은 큰 파일에서 preflight와 split
preview를 표시한다. 분할 STT 결과는 원본 timeline offset으로 병합되며, 저장
metadata에는 chunk id, offset, duration, file size만 남기고 임시 디렉터리 경로는
보존하지 않는다. 임시 파일 삭제 실패는 `temp_cleanup_failed` warning issue로 남긴다.

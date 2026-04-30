# Plan: Vision OCR Frame Extraction

## Goal

강의 영상에서 대표 프레임을 추출하고 OpenAI Vision OCR로 화면 텍스트를 읽어, 원문 OCR은 보관하고 정제 OCR만 자막 segment와 연결한다.

## Scope

- ffmpeg 기반 scene detection 또는 일정 간격 샘플링으로 대표 프레임 후보를 만든다.
- 기본 frame detail은 `original`로 둔다.
- 원본 영상이 1920x1080 미만이면 OCR metadata와 issue에 표시한다.
- Vision OCR은 Responses API image input을 사용한다.
- raw OCR과 refined OCR을 분리해 저장한다.
- refined OCR만 `TranscriptSegment.ocr_text`와 RAG index에 반영한다.
- 중복 프레임 제거, 실패 상태, 비용 추정, 처리 시간은 provider metadata에 남긴다.

## Steps

- [ ] frame extraction use case와 CLI를 정의한다.
- [ ] ffmpeg scene detection 우선, 실패 또는 옵션 선택 시 interval sampling fallback을 제공한다.
- [ ] 프레임 후보에 source_frame_ts, frame_width, frame_height, change_score를 기록한다.
- [ ] Vision OCR 요청 payload를 만들고 `detail=original`을 기본값으로 둔다.
- [ ] OCR 응답을 raw/refined 텍스트와 confidence 가능한 metadata로 정규화한다.
- [ ] 기존 `apply_ocr_enrichment` 흐름에 실제 OCR 결과를 연결한다.
- [ ] OCR 결과가 없거나 transcript segment와 겹치지 않는 경우 빈/오류 상태를 명확히 남긴다.
- [ ] 원본 이미지/프레임 파일은 임시 파일로 처리하고 저장소에 포함하지 않는다.

## Validation

- ffmpeg 없음, 프레임 없음, Vision API 실패, malformed OCR response, segment 매핑 실패를 테스트한다.
- 1080p 미만 metadata issue가 남는지 테스트한다.
- raw OCR은 slide에 보관되고 refined OCR만 segment에 연결되는지 테스트한다.
- `--dry-run`이 네트워크와 저장소 변경 없이 프레임 후보 수와 외부 전송 범위를 보여주는지 테스트한다.
- `python -m unittest discover -s tests`
- `python -m compileall lecturedigest tests`
- `git diff --check`
- `powershell -ExecutionPolicy Bypass -File scripts/validate-harness.ps1 -Mode Project`
- `powershell -ExecutionPolicy Bypass -File scripts/validate-harness.ps1 -CodeHealth -Mode Project`

## Result

작성 전.

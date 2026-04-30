# Plan: Transcript Correction And Finalization

## Goal

자막 파일과 STT 결과 모두를 같은 자동 교정 파이프라인에 태워 교정 완료 transcript를 만들고, 낮은 confidence 후보는 검수 가능한 상태로 남깁니다.

## Scope

- 입력 원천은 `subtitle` 또는 `stt`입니다.
- 영상만 입력된 클립은 OpenAI Transcriptions API 대상입니다.
- 기본 STT 모델 후보는 `gpt-4o-transcribe-diarize`와 `diarized_json` 응답입니다.
- 자막 파일로 대체한 경우와 STT로 추출한 경우 모두 API 기반 문맥/단어/오타 교정을 수행합니다.
- 교정은 사용자 승인 없이 자동 적용하되, 고신뢰 항목만 적용합니다.
- 낮은 confidence 후보는 원문 유지 또는 검수 대기로 남기고 `correction_log`에 기록합니다.
- 교정 완료 transcript만 RAG와 학습 노트의 기본 입력으로 사용합니다.

## Out Of Scope

- 폴더 입력 구조 구현.
- OCR 처리와 자막 병합.
- 검수 UI 완성.
- 노트/카드/퀴즈 생성.

## Assumptions

- 낮은 confidence 후보는 자동 적용하지 않는 기존 프로젝트 규칙을 유지합니다.
- 고유명사, 숫자, 코드, 파일명, API 이름은 보호 규칙을 먼저 적용합니다.
- 모델/prompt 변경 시 기존 교정 결과는 stale로 표시하고 자동 재생성하지 않습니다.
- 실제 OpenAI API key는 코드나 문서에 기록하지 않습니다.

## Steps

- [ ] STT API 입력, 출력, 실행 metadata를 정의한다.
- [ ] diarized segment를 기존 transcript segment로 변환하는 규칙을 정의한다.
- [ ] 교정 전 보호 대상과 교정 후보 탐지 기준을 정한다.
- [ ] 고신뢰 자동 적용 기준과 낮은 confidence 보류 정책을 정한다.
- [ ] `correction_log` 필드와 상태 전이를 정의한다.
- [ ] 교정 완료 transcript의 저장 상태와 downstream 입력 조건을 정한다.

## Validation

- 영상만 입력한 클립은 STT 대상으로 표시됩니다.
- 자막 파일을 사용한 클립도 교정 파이프라인 대상이 됩니다.
- 고신뢰 교정만 자동 적용되고 낮은 confidence 후보는 자동 적용되지 않습니다.
- 교정 결과는 원본 segment id와 timestamp 매핑을 유지합니다.
- 교정 실패 시 원본 오류, 모델명, prompt 버전, retryable 여부가 남습니다.

## Risks

- 자동 교정 false positive가 학습 내용을 왜곡할 수 있습니다.
- 전문 용어와 한국어+코드 혼합 문장에서 STT/교정 오류가 누적될 수 있습니다.
- OpenAI STT 사용은 기존 로컬 중심 경계보다 클라우드 전송 범위가 넓습니다.

## Result

진행 전입니다.

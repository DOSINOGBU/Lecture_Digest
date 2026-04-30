# Plan: Slide Change Detection And OCR Enrichment

## Goal

영상 프레임 변화로 슬라이드 구간을 찾고, 원본 해상도 기준 OCR 결과를 자막 타임라인과 연결할 수 있는 enrichment 단계를 설계합니다.

## Scope

- 영상 프레임을 일정 간격으로 샘플링하고 화면 변화가 임계치 이상이면 새 슬라이드로 판단합니다.
- 대표 프레임을 Vision OCR 대상으로 선정합니다.
- 원문 OCR은 보관하고, 노트/RAG에는 정제 OCR만 반영합니다.
- OCR 결과는 `slide_id`, `source_frame_ts`, 원본 OCR, 정제 OCR, confidence, provider metadata를 포함합니다.
- 세그먼트에는 같은 시간대의 정제 OCR 텍스트와 slide reference를 연결합니다.
- Vision OCR은 원본 detail 우선 정책으로 설계합니다.
- 외부 호출에는 모델명, prompt 버전, 비용 추정, 처리 시간, 실패 상태를 기록합니다.

## Out Of Scope

- 실제 영상 디코딩 라이브러리 추가.
- 실제 Vision API 호출 구현.
- OCR 기반 노트 생성과 RAG 인덱싱.
- 화면 캡처 원본 저장 위치 확정.

## Assumptions

- OCR provider는 OpenAI Vision 가능 모델을 기본 후보로 둡니다.
- 원본 강의 파일과 프레임 이미지는 저장소에 포함하지 않습니다.
- 화면 변화 임계치는 샘플 강의 검증 전까지 configurable 값으로 둡니다.
- OCR 실패는 transcript 처리를 막지 않고 enrichment issue로 남깁니다.

## Steps

- [ ] 슬라이드 후보 감지 입력/출력 스키마를 정의한다.
- [ ] 프레임 샘플링 간격과 화면 변화 threshold의 기본값을 정한다.
- [ ] OCR payload에서 원문 OCR과 정제 OCR 필드를 분리한다.
- [ ] OCR 결과와 transcript segment의 타임라인 연결 규칙을 정의한다.
- [ ] Vision API 호출 metadata와 실패 상태를 정의한다.
- [ ] OCR이 없거나 실패한 경우 노트/RAG 입력에서 제외되는 흐름을 정한다.

## Validation

- 화면 변화가 있는 구간만 슬라이드 후보로 잡히는지 대표 영상으로 검수합니다.
- OCR 텍스트가 같은 시간대 자막 segment에 연결됩니다.
- 원문 OCR과 정제 OCR이 분리되어 저장됩니다.
- OCR 실패가 전체 transcript/chunk 생성 실패로 번지지 않습니다.
- 원본 1080p 프레임 기준 OCR 품질을 표본 검수합니다.

## Risks

- 화면 변화가 잦은 코딩 강의에서 OCR 호출 비용이 급증할 수 있습니다.
- 너무 낮은 threshold는 중복 슬라이드를 많이 만들 수 있습니다.
- 너무 높은 threshold는 중요한 화면 전환을 놓칠 수 있습니다.
- 화면 캡처에는 코드, 계정, 개인정보가 포함될 수 있어 로그 제한이 필요합니다.

## Result

진행 전입니다.

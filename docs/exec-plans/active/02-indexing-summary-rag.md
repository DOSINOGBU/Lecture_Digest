# Plan: Indexing, Summaries, And Cited RAG

## Goal

시간축 세그먼트를 검색 가능한 청크로 만들고, 임베딩 저장, L1/L2/L3 요약, 출처 기반 RAG 답변까지 연결합니다.

## Scope

- 60~90초 기본 청크와 15초 오버랩.
- 청크 payload에 lecture_id, chapter, start_ts, end_ts, speaker, text, ocr_text 포함.
- 임베딩 모델 후보: `text-embedding-3-large` 또는 `voyage-3`.
- Qdrant 기본 후보 저장.
- L1 섹션 요약, L2 챕터 요약, L3 강의 개요/TL;DR/학습 목표.
- RAG 답변에 `[강의명 - 챕터 - 12:34]` 형식 인용과 점프 링크 포함.
- 정제 학습 노트를 RAG 인덱스에 포함하되 원본 segment 역추적 payload를 유지.
- 원문 OCR은 보관하고, RAG에는 정제 OCR만 반영.

## Out Of Scope

- 정제 학습 노트 생성.
- 교정 검수 UI.
- 개념 그래프.

## Assumptions

- 챕터 정보가 없는 강의의 자동 분할 기준은 미정입니다.
- hybrid BM25+dense와 reranker는 MVP에서 단순 검색 후 고도화할 수 있습니다.
- 모델/prompt 변경으로 인덱스가 stale 상태가 되어도 자동 재생성하지 않고 수동 재생성 액션을 둡니다.

## Steps

- [x] 청크 스키마와 원본 segment 매핑 규칙을 정의한다.
- [ ] 임베딩 저장 payload와 캐시 키를 정의한다.
- [ ] L1/L2/L3 요약 입력과 출력 형식을 정의한다.
- [ ] RAG 검색 필터와 답변 인용 형식을 정의한다.
- [ ] 근거 부족 시 답변 거부/검색 범위 안내 흐름을 구현한다.
- [ ] 수동 표본 검수 기준을 만든다.

## Validation

- 청크가 원본 segment id와 타임스탬프를 보존합니다.
- RAG 답변은 모든 핵심 주장에 출처를 표시합니다.
- 근거가 부족한 질문은 답변을 꾸며내지 않습니다.
- 일반 질의 응답 시간은 30초 이내를 목표로 측정합니다.
- 정제 노트 인덱스 결과도 원본 segment로 역추적됩니다.

## Risks

- 청크 경계가 부적절하면 RAG 답변 근거가 끊길 수 있습니다.
- 임베딩/LLM 호출 비용이 긴 강의에서 급증할 수 있습니다.

## Result

표준 라이브러리 기반으로 transcript segment를 60~90초 계열의 검색 준비 청크로 나누는 스키마와 로직을 구현했습니다. 원본 `segment_ids`, 시작/종료 타임스탬프, 챕터, 텍스트를 보존하며 CLI에서 빈/진행/오류 상태를 확인할 수 있습니다. 임베딩, Qdrant 저장, 요약, RAG 답변 생성은 후속 작업입니다.

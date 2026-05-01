# Plan: Indexing, Summaries, And Cited RAG

## Goal

교정 완료 transcript와 정제 OCR을 검색 가능한 청크로 만들고, 임베딩 저장, L1/L2/L3 요약, 출처 기반 RAG 답변까지 연결합니다.

## Scope

- 60~90초 기본 청크와 15초 오버랩.
- 청크 payload에 lecture_id, clip metadata, chapter, start_ts, end_ts, speaker, corrected_text, refined_ocr_text 포함.
- 임베딩 모델 후보: `text-embedding-3-large` 또는 `voyage-3`.
- Qdrant 기본 후보 저장.
- L1 섹션 요약, L2 챕터 요약, L3 강의 개요/TL;DR/학습 목표.
- RAG 답변에 `[강의명 - 챕터 - 12:34]` 형식 인용과 점프 링크 포함.
- 정제 학습 노트를 RAG 인덱스에 포함하되 원본 segment 역추적 payload를 유지.
- 원문 OCR은 보관하고, RAG에는 정제 OCR만 반영.

## Out Of Scope

- 폴더 입력과 STT 호출.
- OCR 추출 자체.
- 정제 학습 노트 생성.
- 교정 검수 UI.
- 개념 그래프.

## Assumptions

- 챕터 정보가 없는 강의의 자동 분할 기준은 미정입니다.
- hybrid BM25+dense와 reranker는 MVP에서 단순 검색 후 고도화할 수 있습니다.
- 모델/prompt 변경으로 인덱스가 stale 상태가 되어도 자동 재생성하지 않고 수동 재생성 액션을 둡니다.
- RAG 입력은 교정 완료 transcript를 우선 사용합니다.

## Steps

- [x] 청크 스키마와 원본 segment 매핑 규칙을 정의한다.
- [x] 임베딩 저장 payload와 캐시 키를 정의한다.
- [x] L1/L2/L3 요약 입력과 출력 형식을 정의한다.
- [x] RAG 검색 필터와 답변 인용 형식을 정의한다.
- [x] 근거 부족 시 답변 거부/검색 범위 안내 흐름을 구현한다.
- [x] 수동 표본 검수 기준을 만든다.

## Manual Validation Criteria

- 대표 질문은 5개 이상 만들고, 기대 timestamp가 top 3 검색 결과에 들어오는지 기록합니다.
- RAG 답변의 모든 핵심 문장에는 `[강의명 - 챕터 - 12:34]` 형식 인용이 있어야 합니다.
- jump link는 `lecturedigest://lecture/{lecture_id}?t={seconds}` 형식으로 원본 segment 위치를 역추적할 수 있어야 합니다.
- 근거가 부족한 질문은 답변을 꾸며내지 않고 `insufficient_evidence` 상태와 검색 범위 조정 안내를 반환해야 합니다.
- 정제 노트 section을 인덱싱할 때도 `segment_ids`, `start_ts`, `end_ts` 중 가능한 원본 매핑을 보존해야 합니다.
- 일반 질의는 CLI 기준 30초 이내 응답을 목표로 하고, 출력의 `durationMs`를 확인합니다.

## Validation

- 청크가 원본 segment id와 타임스탬프를 보존합니다.
- RAG 답변은 모든 핵심 주장에 출처를 표시합니다.
- 근거가 부족한 질문은 답변을 꾸며내지 않습니다.
- 일반 질의 응답 시간은 30초 이내를 목표로 측정합니다.
- 정제 노트 인덱스 결과도 원본 segment로 역추적됩니다.
- 대표 질문 top 3 안에 예상 timestamp chunk가 들어오는지 검수합니다.

## Risks

- 청크 경계가 부적절하면 RAG 답변 근거가 끊길 수 있습니다.
- 임베딩/LLM 호출 비용이 긴 강의에서 급증할 수 있습니다.
- 정제 OCR이 과도하게 섞이면 음성 근거와 화면 근거가 혼동될 수 있습니다.

## Result

표준 라이브러리 기반으로 transcript segment를 60~90초 계열의 검색 준비 청크로 나누는 스키마와 로직을 유지하고, 그 위에 로컬 lexical RAG 인덱스, embedding payload/cache key, L1/L2/L3 extractive summary, cited RAG answer를 추가했습니다. `index` 명령은 Qdrant와 `text-embedding-3-large` 후보를 metadata로 기록하되 실제 외부 embedding 호출은 하지 않고 `pending_external_embedding` 상태로 남깁니다. `summarize` 명령은 chunk 기반 L1, chapter 기반 L2, lecture 기반 L3 요약 구조를 저장합니다. `ask` 명령은 저장된 `search_index`를 검색해 `[강의명 - 챕터 - 12:34]` 인용과 `lecturedigest://` jump link를 출력하며, 근거가 부족하면 `insufficient_evidence`로 답변 생성을 거부합니다. 정제 노트 section이 들어오면 `note_section` index entry로 포함하고 원본 `segment_ids`를 보존하도록 스키마를 열어두었습니다.

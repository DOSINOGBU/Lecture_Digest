# Architecture

LectureDigest는 강의 파일을 시간축이 있는 텍스트 세그먼트로 변환하고, 검색/요약/학습 노트/복습 산출물로 이어지는 개인 학습 파이프라인입니다. 이 문서는 코드가 아직 없거나 바뀌더라도 유지해야 할 경계, 데이터 흐름, 금지된 의존성을 기록합니다.

## System Overview

사용자는 영상 파일과 선택 자막, 강의 메타데이터를 등록합니다. 시스템은 자막 파싱 또는 STT, 선택적 OCR/화자 분리, 청킹, 임베딩, 요약, RAG 답변, ScriptDigest 노트 생성을 단계별 작업으로 처리합니다. 각 단계는 원본 입력, 모델/프롬프트 버전, 캐시 키, 실패 로그를 남겨 재시도와 검수가 가능해야 합니다.

## Main Flow

```text
Lecture Registration
→ Transcript Source Selection (subtitle or STT)
→ Optional OCR / Speaker Metadata
→ Time-aligned Segments
→ Chunking and Embedding
→ L1/L2/L3 Summaries
→ RAG Search and Cited Answer
→ ScriptDigest Chapter Note
→ Validation / Correction Review
→ Flashcards and Quizzes
```

## Processing Stages

| Stage | Responsibility | Primary Outputs |
|---|---|---|
| Ingestion | 파일, 자막, 제목/강사/카테고리 메타데이터 등록 | `lecture_id`, `pending` 작업 상태 |
| Transcription | SRT/VTT 파싱 또는 Whisper/faster-whisper STT | 시간축 세그먼트 |
| Enrichment | 선택적 OCR, 화자 분리, 도메인 용어집 적용 | `ocr_text`, `slide_caption`, `speaker` |
| Indexing | 60~90초 청크, 15초 오버랩, 임베딩 저장 | 검색 청크, Qdrant payload |
| Summarization | L1 섹션, L2 챕터, L3 강의 개요 생성 | 계층 요약과 학습 목표 |
| RAG | BM25+dense hybrid 검색, 선택적 reranker, 출처 답변 | 인용이 있는 답변 |
| ScriptDigest | 챕터 단위 정제, 구조화, rewrite, 검증 | Markdown 노트와 frontmatter |
| Review/Export | 교정 후보 검수, Anki/퀴즈 생성 | 복습 산출물 |

## Layer Rules

| Layer | Responsibility | Must Not |
|---|---|---|
| UI / Presentation | 강의 등록, 작업 상태, 검색, 노트 미리보기, 검수 UI | STT/OCR/LLM 규칙을 화면 컴포넌트에 직접 구현 |
| Application / Use Case | 작업 단계 조합, 상태 전환, 재시도, 캐시 사용 결정 | 저장소 세부 구현이나 모델 호출 세부를 도메인에 누출 |
| Domain / Business | 청크 정책, 출처 정책, 교정 confidence 정책, 검증 게이트 | UI 프레임워크나 외부 API SDK에 의존 |
| Infrastructure | 파일 시스템, 벡터 DB, LLM/STT/OCR 클라이언트, 큐, 캐시 | 도메인 규칙을 임의 결정 |

## Dependency Direction

```text
UI → Application → Domain
Application → Infrastructure
Domain → no framework dependency
```

Domain 규칙은 프레임워크, LLM 공급자, 벡터 DB 구현과 분리합니다. Qdrant, Whisper, OpenAI/Voyage 모델은 기본 후보이지만 도메인 규칙의 유일한 표현이 되어서는 안 됩니다.

## Key Architectural Decisions From PRD

- MVP는 개인 로컬/개인 계정 기반 사용을 우선합니다.
- 초기 UI는 Streamlit을 추천하며, 파이프라인은 단일 CLI/단일 프로세스로 시작합니다.
- 초기 클라우드 경계는 LLM 호출만 클라우드로 두고, 강의 파일, STT/OCR 원본, 벡터 저장소, 캐시는 로컬 중심으로 둡니다.
- 장기 작업은 단일 프로세스 안에서도 단계별 상태를 남기고, 큐 기반 확장은 후속으로 열어둡니다.
- 각 단계 결과는 입력 해시, 모델 버전, 프롬프트 버전 기준으로 캐시합니다.
- RAG 답변과 학습 노트는 원본 segment id와 타임스탬프 매핑을 보존합니다.
- ScriptDigest는 STT/OCR을 직접 수행하지 않고 LectureDigest 전처리 파이프라인의 세그먼트와 OCR 결과를 입력으로 받습니다.
- 원문 OCR은 보관하되, 노트와 RAG에는 정제된 OCR 텍스트만 반영합니다.
- 정제된 학습 노트는 RAG 인덱스에 포함하되, 답변 인용은 원본 segment 근거로 역추적 가능해야 합니다.
- 모델 또는 prompt 변경 시 기존 산출물은 자동 재생성하지 않고 stale 표시와 수동 재생성 액션을 제공합니다.
- 능동 복습 산출물은 Anki를 먼저 구현하고 퀴즈는 후속으로 둡니다.
- prompt는 YAML 파일과 버전 태그로 관리할 수 있어야 합니다.
- 벡터 DB는 Qdrant를 기본 후보로 두되 Chroma, pgvector 대체 가능성을 닫지 않습니다.

## External Systems

| 시스템 | 용도 | 주의 |
|---|---|---|
| Whisper `large-v3` 또는 faster-whisper | 자막 없는 강의 STT | 한국어는 `--language ko`와 도메인 prompt 고려 |
| Vision OCR | 슬라이드/코드 화면 텍스트 추출 | 키프레임/중복 제거 후 호출 |
| Qdrant | 청크 임베딩 저장과 검색 | payload에 segment 메타데이터 포함 |
| Embedding model | 청크 벡터화 | `text-embedding-3-large` 또는 `voyage-3` 후보 |
| LLM | 요약, RAG 답변, ScriptDigest rewrite/보정 | 비용, prompt 버전, 캐시 키 추적 |
| Kiwi(`kiwipiepy`) | 한국어 형태소 분석 | v1 고도화 범위로 남을 수 있음 |
| AnkiConnect / `.apkg` | 카드 내보내기 | 퀴즈보다 먼저 출시 |

## Forbidden Patterns

- UI 컴포넌트에서 직접 DB, 파일 시스템, LLM, STT, OCR API를 호출하지 않습니다.
- 출처 없는 LLM 부연을 원본 강의 내용처럼 저장하거나 표시하지 않습니다.
- confidence가 낮은 교정을 사용자 몰래 확정 적용하지 않습니다.
- 전체 원본 대본, API 키, 결제/계정 정보를 로그에 남기지 않습니다.
- 캐시된 산출물을 프롬프트/모델 버전 변경 후 무조건 신뢰하지 않습니다.
- 실패를 빈 `catch`나 무의미한 기본값으로 숨기지 않습니다.

## Initial Decisions And Open Questions

| 질문 | 현재 결정 | 다음 확인 |
|---|---|---|
| MVP 실행 형태 | Streamlit 추천, 단일 프로세스 파이프라인 | Phase 0 후 최종 확정 |
| 큐 구현 | 초기에는 Redis/Celery/Prefect 없이 단일 CLI/단일 프로세스 | 장기 작업 병렬화가 필요해지면 ADR |
| 클라우드 확장 | 초기에는 LLM 호출만 클라우드, 파일/캐시/벡터 저장은 로컬 중심 | 인증, 객체 스토리지, 멀티테넌시 별도 설계 |
| 정제 노트 인덱싱 | RAG 인덱스에 포함 추천 | 원본 segment 인용 역추적 방식 설계 |
| OCR/RAG 통합 범위 | 원문 OCR은 보관, 정제 OCR만 노트/RAG 반영 | 정제 규칙과 원본 보존 필드 설계 |
| 산출물 재생성 | 자동 재생성하지 않고 수동 재생성 버튼 제공 | stale 상태와 재생성 범위 설계 |

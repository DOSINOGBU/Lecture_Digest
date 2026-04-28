# Backend Guide

LectureDigest 백엔드는 파일 등록부터 STT/OCR/임베딩/요약/RAG/ScriptDigest까지 이어지는 장기 파이프라인을 안전하게 조합해야 합니다. 라우터나 컨트롤러는 얇게 유지하고, 사용 사례와 도메인 규칙을 분리합니다.

초기 MVP는 API 서버와 별도 워커를 두기보다 Streamlit 또는 CLI에서 같은 use case를 호출하는 단일 프로세스로 시작합니다. 단, 상태 전이, 캐시, 실패 단계 기록은 나중에 Redis+Celery 또는 Prefect로 분리할 수 있게 경계를 유지합니다.

## API Principles

- 입력은 경계에서 검증합니다.
- 비즈니스 로직은 라우터나 컨트롤러에 직접 넣지 않습니다.
- 외부 시스템 실패는 원본 에러와 단계 맥락을 로그로 남깁니다.
- 응답 형식은 일관되게 유지합니다.
- 장기 작업은 즉시 결과 대신 작업 ID, 단계 상태, 재시도 가능 여부를 반환합니다.
- 서비스와 유스케이스는 검증된 입력을 받고, 실패 지점을 호출자가 추적할 수 있게 합니다.

## Target Use Cases

| Use Case | 입력 | 출력 |
|---|---|---|
| RegisterLecture | 영상 파일, 선택 자막, 제목/강사/카테고리 | `lecture_id`, `pending` 상태 |
| BuildTranscript | 자막 또는 영상 오디오 | 시간축 세그먼트 |
| EnrichSegments | 세그먼트, 선택 OCR/화자 설정 | OCR/화자 메타데이터가 병합된 세그먼트 |
| IndexLecture | 세그먼트와 청크 설정 | 임베딩, 검색 payload |
| GenerateSummaries | 청크/챕터 | L1/L2/L3 요약 |
| AskLecture | 질문, 필터, 사용자/강의 범위 | 인용과 점프 링크가 있는 답변 |
| GenerateNote | 챕터 세그먼트, OCR, 용어집, 톤 | Markdown 노트, frontmatter, validation log |
| ReviewCorrection | correction 후보와 사용자 결정 | 적용/기각 상태 |
| IndexRefinedNote | 정제 노트 섹션 | note embedding, 원본 segment 역추적 payload |
| GenerateReviewAssets | 노트/세그먼트/요약 | Anki 카드, 후속 퀴즈 |

## Data Flow

```text
Request
→ Input Validation
→ Use Case
→ Domain Rules
→ Repository / External Client
→ Job State Update
→ Response Mapping
```

## Validation Rules

- 강의 등록에는 파일 존재, 지원 확장자, 읽기 가능 여부, 필수 메타데이터를 확인합니다.
- 자막 기반 강의는 STT를 건너뛰지만 SRT/VTT 파싱 실패를 명확히 반환합니다.
- ScriptDigest 입력은 `lecture_id`, `lecture_title`, `chapter_title`, `category`, `instructor`, `{start_ts,end_ts,text}` 세그먼트를 요구합니다.
- 톤 옵션은 `formal`, `casual`, `keep_original` 중 하나이며 기본값은 `formal`입니다.
- 챕터 노트 생성은 5~30분 또는 약 3,000~15,000 토큰 권장 범위를 넘으면 분할 경고를 반환합니다.

## Error Policy

| 오류 유형 | 처리 |
|---|---|
| Validation | 사용자가 수정 가능한 메시지와 필드 반환 |
| Auth / Permission | 권한 부족을 명확히 반환하되 내부 정보는 숨김 |
| Not Found | 대상 식별자를 로그에 포함 |
| External API | 호출 단계, 모델/서비스명, 재시도 여부를 기록 |
| Low Evidence | 답변 생성을 거부하거나 근거 부족을 사용자에게 표시 |
| Unexpected | 원본 에러와 작업 맥락을 로그에 포함 |

외부 클라이언트와 저장소 계층에서 발생한 오류는 호출 단계, 대상 식별자, 재시도 여부를 함께 전달합니다.

## Background Jobs

- STT, OCR, 임베딩, 요약, 노트 생성, Anki/퀴즈 생성은 단계별 작업으로 설계합니다.
- 초기 구현은 단일 프로세스에서 순차 실행하되, 상태 모델은 나중에 큐 기반 비동기 작업으로 옮길 수 있게 둡니다.
- 각 작업은 `pending`, `running`, `succeeded`, `failed`, `flagged`, `retrying` 같은 상태를 구분합니다.
- 실패한 단계부터 재시작할 수 있도록 입력 해시, 모델 버전, prompt 버전, 중간 산출물을 기록합니다.
- 멱등하지 않은 외부 호출은 중복 실행 영향과 캐시 정책을 명시합니다.

## External Client Rules

- L1 섹션 요약과 대량 호출은 저비용 모델을 우선합니다.
- L2/L3 요약, RAG 최종 답변, ScriptDigest rewrite/보강은 품질 모델 후보를 사용할 수 있습니다.
- STT 무결성 보정은 검출 패턴에 매칭된 세그먼트만 LLM 호출합니다.
- OCR은 장면 변화 기반 키프레임과 중복 제거 후 호출합니다.
- 초기 클라우드 호출 범위는 LLM으로 제한하고, STT/OCR과 파일 보관은 로컬 중심을 우선합니다.
- 원문 OCR은 보관하되 정제 OCR만 노트/RAG에 반영합니다.
- 모든 외부 호출은 모델명, prompt 버전, 토큰/비용 추정, 처리 시간을 기록합니다.

## Initial Decisions And Open Questions

| 질문 | 현재 상태 |
|---|---|
| 백엔드 스택은 Python 단일 앱, API 서버+워커, 또는 다른 구조인가? | 초기에는 단일 CLI/단일 프로세스 |
| 큐는 Redis+Celery와 Prefect 중 무엇으로 시작할 것인가? | 초기에는 사용하지 않음 |
| 로컬 MVP에서 API 서버 없이 CLI/Streamlit으로 use case를 호출할 것인가? | 예 |
| 정제 노트를 RAG 인덱스에 포함할 것인가? | 포함 추천, 원본 segment 역추적 필수 |

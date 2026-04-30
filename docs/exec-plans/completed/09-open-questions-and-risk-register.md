# Plan: Open Questions And Risk Register

## Goal

PRD와 후속 사용자 결정에서 아직 확정되지 않은 질문, 위험, 가정을 MVP 구현 전에 추적한다. 이 계획은 기능 구현이 아니라 다음 구현 계획들이 막히지 않도록 결정 경계와 후속 확인 항목을 정리하는 문서 작업이다.

## Decisions Reflected

| Topic | Decision |
|---|---|
| Local/cloud boundary | 파일, 산출물, 인덱스는 로컬 중심으로 두고 STT, Vision OCR, LLM 호출만 OpenAI API를 사용할 수 있다. |
| MVP UI | 핵심 파이프라인은 CLI/use case로 먼저 구현하고, 승인/검토 UX가 필요한 시점에 Streamlit을 붙인다. |
| Worker model | 초기에는 단일 CLI/단일 프로세스를 사용한다. |
| Input mode | 파일 단위와 폴더 단위를 모두 지원한다. |
| Folder structure | `강의명 / 대분류 / 중분류 / 영상 클립` 구조를 기본으로 해석한다. |
| Subtitle matching | 자막 폴더가 있으면 stem 매칭, 실패 시 번호 접두사 보조 매칭을 사용한다. 일부 매칭 실패는 자동 STT로 넘기지 않고 `subtitle_unmatched`로 남긴다. |
| STT provider | OpenAI Transcriptions API를 사용한다. |
| OCR provider | Vision OCR API를 사용하고 원본 detail 우선 정책을 둔다. |
| OCR note/RAG scope | 원문 OCR은 보관하고 정제 OCR만 노트/RAG에 반영한다. |
| RAG note scope | 승인된 정제 노트는 RAG 인덱스에 포함하되 원본 segment/timestamp 역추적을 유지한다. |
| Regeneration | model/prompt 변경 시 자동 재생성하지 않고 stale 표시 후 수동 재생성만 허용한다. |
| Review feature order | Anki 카드를 먼저 출시하고 퀴즈는 이후 확장한다. |
| Note approval | AI 초안 여러 개를 만든 뒤 사람이 승인한 노트만 확정 산출물로 사용한다. |
| Cost/BYOK | MVP는 BYOK를 기본으로 하며, 유료 API 호출은 명시적 사용자 실행에서만 발생한다. 앱 레벨 hard budget은 클라우드/공유 배포 전 ADR에서 정한다. |

## Remaining Open Questions

| Question | Why It Remains Open |
|---|---|
| 챕터 정보가 없는 강의의 자동 분할 기준 | 실제 강의 유형별 자막/화면 패턴 샘플이 더 필요하다. |
| `speaker_mode=dialogue` 자동 활성 조건 | 대화형 강의와 단일 강의 구분 기준이 아직 충분히 검증되지 않았다. |
| 긴 화면 메모를 본문 핵심 내용으로 둘지 별도 블록으로 분리할지 | 노트 가독성 샘플을 보고 결정해야 한다. |
| confidence 0.7~0.9 교정 후보의 검토 UX | Streamlit 검토 화면 설계 시 함께 정한다. |
| 앱 레벨 월간/강의별 비용 상한 | BYOK MVP에서는 제공자 계정 한도를 우선 사용하며, 공유 계정/클라우드 배포 전에 정한다. |
| Cloud preview 인증, 저장소, 삭제 정책 | 로컬 MVP 이후 별도 ADR과 배포 계획에서 정한다. |

## Risks

- STT, Vision OCR, LLM API 사용으로 강의 자료 일부가 외부 API에 전송된다.
- STT 오류나 OCR 오인식이 노트, 카드, 퀴즈까지 전파될 수 있다.
- 긴 강의와 반복 재생성은 비용 급증을 만들 수 있다.
- 청크 경계가 부적절하면 RAG 검색 결과의 timestamp 근거가 약해질 수 있다.
- LLM이 원본에 없는 내용을 보강하면 학습 노트의 신뢰도가 떨어질 수 있다.
- 저작권 또는 계약 제한이 있는 강의 자료를 외부 API로 전송하면 법적/계약상 문제가 생길 수 있다.

## Follow-Up Backlog

| Area | Follow-Up |
|---|---|
| OCR quality | 원본 1080p 기준 대표 프레임 OCR 품질과 비용을 샘플로 검증한다. |
| Golden notes | 승인 기준을 만족하는 골든 노트 샘플을 일부만 저장소에 포함한다. |
| STT calls | OpenAI STT 호출의 실패 상태, 비용 추정, retry 정책을 구현 계획에 포함한다. |
| Vision OCR calls | Vision OCR의 원본 detail, 샘플링 간격, 중복 제거, 민감정보 로그 제한을 구현 계획에 포함한다. |
| Cloud deployment | 클라우드 preview 전 인증, 저장소, 사용자별 quota, 삭제 정책 ADR을 작성한다. |

## Steps

- [x] Phase 0 결과로 직접 구현 범위를 다시 평가한다.
- [x] UI와 백엔드 실행 형태의 초기 방향을 정한다.
- [x] 외부 API 전송 범위의 초기 경계를 정한다.
- [x] 능동학습 기능 우선순위를 정한다.
- [x] 파일/폴더 입력과 자막/STT 분기 정책을 반영한다.
- [x] STT와 OCR provider 방향을 반영한다.
- [x] 노트 후보 승인과 퀴즈 후속 정책을 반영한다.
- [x] 비용 한도와 BYOK 정책을 MVP 기준으로 결정한다.
- [x] 확정 항목을 관련 문서와 계획에 반영한다.

## Validation

- 각 구현 계획 시작 전에 관련 open question이 구현을 막는지 확인한다.
- 결정성 질문은 관련 문서 또는 ADR로 옮긴다.
- 외부 API 호출 계획은 보안, 비용, 실패 상태를 포함해야 한다.

## Result

MVP의 BYOK 비용 정책과 외부 API 메타데이터 기록 원칙을 `docs/COST.md`, `docs/SECURITY.md`, `docs/DATA.md`, `docs/DEPLOYMENT.md`, `docs/RUNBOOK.md`에 반영했다. 09번 계획은 완료 처리했으며, 남은 질문은 구현을 막지 않는 후속 설계/운영 결정으로 분리했다.

# Tech Debt Tracker

AI 작업 중 발견한 반복 문제와 나중에 처리할 기술 부채를 기록합니다.

| ID | 문제 | 영향 | 제안 해결 | 상태 |
|---|---|---|---|---|
| TD-001 | TODO | TODO | TODO | open |
| TD-002 | Windows 기본 CP949 환경에서 ffprobe 출력 디코딩이 실패할 수 있음 | OCR preflight가 `PYTHONUTF8=1` 없이는 실패할 수 있음 | subprocess 출력 디코딩을 UTF-8 우선으로 고정하고 실패 시 원문 stderr를 보존 | open |
| TD-003 | JSON store에 동시 쓰기 보호가 없음 | 병렬 CLI 실행 시 카드/퀴즈 결과가 덮이거나 JSON이 깨질 수 있음 | repository 저장에 파일 lock 또는 atomic write/merge 정책 추가 | open |
| TD-004 | 실제 강의 노트 후보가 모두 validation flagged 상태 | 골든 노트 승인 전 카드/퀴즈 품질 신뢰가 낮음 | 사람 승인 루브릭과 노트 품질 평가를 먼저 통과한 후보만 golden sample로 승격 | open |
| TD-005 | Vision OCR은 dry-run만 수행됨 | OCR 기반 슬라이드 보강 품질과 비용을 아직 판단할 수 없음 | 대표 프레임 소량으로 실제 Vision OCR smoke test를 수행하고 비용/정확도 기록 | open |
| TD-006 | PRD v2 OpenAI 노트 후보도 모두 validation flagged 상태 | 표준 강의 후보가 topic/question 개수와 flow/code 구조 기준을 일부 충족하지 못함 | 프롬프트를 더 강하게 조정하거나 후보 생성 후 repair pass를 추가해 PRD 체크리스트를 재검증 | open |

## 2026-04-30 Update

- TD-006 was mitigated by `18a-note-prd-quality-repair`: the real lecture sample now has 3 `review_required` OpenAI note candidates after repair. Golden note approval is still a manual decision.

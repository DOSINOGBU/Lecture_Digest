# Plan: Vector RAG Upgrade

## Goal

현재 lexical fallback RAG를 유지하면서 실제 embedding 생성과 vector 기반 검색을 추가해, 강의 검색 품질을 높이고 모든 답변 근거를 timestamp로 역추적 가능하게 한다.

## Scope

- 기본 embedding model은 기존 설정인 `text-embedding-3-large`를 사용한다.
- 외부 vector DB는 아직 도입하지 않고 로컬 JSON payload에 embedding cache를 저장한다.
- 검색은 vector score를 우선 사용하고, embedding이 없거나 근거가 부족하면 lexical fallback을 사용한다.
- indexed text는 교정 완료 자막 + 정제 OCR + 승인된 정제 노트 섹션을 대상으로 한다.
- 모든 검색 결과는 chunk id, note section id, segment ids, timestamp를 유지한다.
- embedding model 또는 indexed text hash가 바뀌면 stale로 표시하고 자동 재생성하지 않는다.

## Steps

- [ ] 기존 `search_index` payload에 embedding vector와 source hash 저장 위치를 정한다.
- [ ] OpenAI embedding 호출 client를 추가한다.
- [ ] chunk와 approved note section의 embedding 생성/캐시 정책을 구현한다.
- [ ] vector similarity 검색과 lexical fallback의 우선순위를 구현한다.
- [ ] `ask` 결과에 search strategy와 score metadata를 포함한다.
- [ ] 근거 부족 시 답변 생성을 거부하는 기존 정책을 유지한다.
- [ ] embedding stale 상태와 수동 재생성 흐름을 추가한다.

## Validation

- fake embedding으로 vector top-k 정렬을 테스트한다.
- embedding 없음 또는 stale 상태에서 lexical fallback이 동작하는지 테스트한다.
- note section이 index에 포함되되 원본 segment/timestamp 역추적이 유지되는지 테스트한다.
- 근거 부족 질문은 답변을 만들지 않는지 테스트한다.
- `python -m unittest discover -s tests`
- `python -m compileall lecturedigest tests`
- `git diff --check`
- `powershell -ExecutionPolicy Bypass -File scripts/validate-harness.ps1 -Mode Project`
- `powershell -ExecutionPolicy Bypass -File scripts/validate-harness.ps1 -CodeHealth -Mode Project`

## Result

작성 전.

# ADR-0002: Streamlit Review UI

## Status

Accepted

## Context

LectureDigest needs a local review surface for lecture status, note approval,
correction review, and Anki/quiz previews. The MVP already has CLI/use case
logic, and the product decision is to keep processing local-first while using
cloud calls only behind explicit user actions.

## Decision

Use Streamlit as the Phase 1 local UI dependency. Pin the direct dependency in
`requirements.txt` and keep UI code at the presentation layer so it calls
existing repository and domain functions instead of reimplementing STT, OCR,
LLM, RAG, note, card, or quiz rules.

## Consequences

### Positive

- Adds a fast local UI for review and approval workflows without introducing a
  frontend build pipeline.
- Keeps the first screen focused on the lecture library and registration
  instead of a marketing page.
- Makes paid external actions visible as explicit confirm/dry-run flows.

### Negative

- Adds a Python runtime dependency with transitive packages.
- UI styling and component structure remain limited compared with a dedicated
  frontend stack.
- Browser-based manual smoke checks are needed in addition to unit tests.

## Rejected Alternatives

| 대안 | 채택하지 않은 이유 |
|---|---|
| CLI only | 노트 승인, 교정 검수, 카드/퀴즈 미리보기에는 반복 조작 비용이 큼 |
| Next.js | MVP 로컬 단일 프로세스 범위에 비해 빌드/상태/배포 부담이 큼 |
| Tkinter/custom desktop UI | Markdown preview와 빠른 데이터 앱 구성 측면에서 Streamlit보다 생산성이 낮음 |

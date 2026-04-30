# Plan: Anki Card Generation And Export

## Goal

승인된 Markdown 학습 노트, 챕터 요약, 원본 segment를 기반으로 Anki 카드를 먼저 생성하고 출처 매핑을 보존합니다.

## Scope

- Cloze, Q&A, 코드 카드 후보 생성.
- 카드 입력은 승인된 학습 노트를 우선 사용하고, 부족한 근거는 원본 segment와 요약으로 보강합니다.
- 카드에는 원본 segment id, timestamp, lecture/chapter metadata를 포함합니다.
- `.apkg` 또는 AnkiConnect 내보내기 후보를 검토합니다.
- 카드 후보는 검수/flagged 상태를 가질 수 있습니다.

## Out Of Scope

- 퀴즈 생성 구현.
- 개념 그래프.
- Notion/HTML/PDF 렌더러.
- 모바일 복습 앱.

## Assumptions

- Anki를 퀴즈보다 먼저 출시합니다.
- 승인된 노트가 없으면 카드 확정 산출물을 만들지 않습니다.
- 카드와 후속 퀴즈는 원본 출처가 없는 경우 확정 산출물로 저장하지 않습니다.

## Steps

- [x] Anki 카드 입력 소스 우선순위를 정한다.
- [x] 출처 매핑 필수 필드를 정의한다.
- [x] 카드 유형별 생성 규칙을 정의한다.
- [x] 내보내기 형식과 실패 상태를 정의한다.
- [x] 표본 검수 기준을 만든다.

## Validation

- 승인된 노트만 Anki 카드 입력으로 사용됩니다.
- 카드 유효성은 직접 검수 기준 80% 이상을 목표로 합니다.
- 출처 매핑이 없는 카드는 `flagged` 또는 검수 대기로 남깁니다.
- 내보내기 실패 시 재시도 가능 여부와 실패 원인을 기록합니다.

## Risks

- 부정확한 카드는 잘못된 기억을 강화할 수 있습니다.
- 너무 많은 카드 후보는 검토 비용을 높일 수 있습니다.

## Open Questions

- `.apkg` 파일 생성과 AnkiConnect 중 어떤 방식을 우선할 것인가?

## Result

Completed.

- Added approved-note-only Anki card generation with Q&A, cloze, and code-card previews.
- Preserved source segment ids, timestamps, lecture/chapter metadata, tags, and jump links on each card.
- Added `generate-cards` and `export-anki` CLI commands with loading, empty, success, and error states.
- Added local Anki-compatible TSV and JSON preview export without adding external dependencies.
- Cards without source mappings are kept as `flagged` and skipped by export unless `--include-flagged` is used.
- `.apkg` vs AnkiConnect remains a future integration decision; this plan ships the local preview/export bridge first.
- Verification passed with `python -m unittest discover -s tests`, `python -m compileall lecturedigest tests`, and harness validation.

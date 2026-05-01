# 19. Card PRD Alignment

## Status

Completed.

## Goal

Align LectureDigest card generation with the approved card PRD v0.1 so that approved learning notes can produce Anki-ready long-term review cards.

## Scope

- Use only an approved note as the card input.
- Support `qa`, `cloze`, `code`, and `application` card types.
- Keep quiz generation out of scope.
- Calculate card count adaptively from approved note text volume, section count, and core concept count.
- Preserve source segment ids, timestamps, jump links, lecture metadata, note section id, and approved note candidate id.
- Keep cards without source mapping as `flagged`.
- Exclude flagged cards from Anki export by default.
- Keep `.apkg`, AnkiConnect, and spaced repetition scheduling as future work.

## Steps

- [x] Read the provided card PRD and compare it with the current `generate-cards` / `export-anki` implementation.
- [x] Split adaptive card count policy into a small card policy module.
- [x] Split card quality validation into a small validation module.
- [x] Add `application` card generation from approved-note action/application sections.
- [x] Add `--card-types qa,cloze,code,application` CLI filtering.
- [x] Add PRD-required card fields and tags.
- [x] Add tests for approved-note gating, source mapping, adaptive count, card type filtering, duplicate removal, flagged export exclusion, and TSV/JSON export.

## Validation

- `python -m unittest discover -s tests`
- `python -m compileall lecturedigest tests`
- `git diff --check`
- `powershell -ExecutionPolicy Bypass -File scripts/validate-harness.ps1 -Mode Project`
- `powershell -ExecutionPolicy Bypass -File scripts/validate-harness.ps1 -CodeHealth -Mode Project`
- `powershell -ExecutionPolicy Bypass -File scripts/recommend-version-control.ps1 -VerificationStatus Passed`

## Acceptance Criteria

- Approved note 1개에서 ready 카드가 생성된다.
- Ready 카드 전부 source mapping을 가진다.
- `front`에는 source/timestamp가 노출되지 않는다.
- Flagged 카드는 기본 export에서 제외된다.
- Anki TSV는 Anki import 가능한 필드 순서를 유지한다.
- 카드 표본 검수 기준 유효율 목표는 80% 이상이다.

## Result

Completed.

- Added adaptive card count planning for `tiny`, `compact`, `short`, `standard`, `expanded`, and `chaptered` notes.
- Split card policy, card factory, and card validation responsibilities into focused modules.
- Added `qa`, `cloze`, `code`, and `application` card type filtering through `generate-cards --card-types`.
- Preserved PRD-required fields including note section id, flattened source segment ids, timestamps, jump link, difficulty, model, prompt version, and source note candidate id.
- Kept flagged cards out of default TSV/JSON export while allowing `--include-flagged`.
- Added tests for approved-note gating, source mapping, application cards, code-card skipping, adaptive count, max-card cap, duplicate removal, answer leakage, and export behavior.

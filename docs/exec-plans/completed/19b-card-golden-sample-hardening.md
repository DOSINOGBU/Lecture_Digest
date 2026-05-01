# 19b. Card Golden Sample Hardening

## Status

Completed

## Goal

Lock the user-selected card candidate set 3 into a local hardened golden sample while preventing future OpenAI-generated card ID collisions.

## Scope

- Use `.lecturedigest/card-candidate-sets/19a-gpt41-standard/set-3*` as the source candidate set.
- Keep generated golden card artifacts under `.lecturedigest/.../golden-set-3-*` and out of version control.
- Record repository-visible validation results in `docs/validation/card-golden-sample-2026-05-01.md`.
- Harden OpenAI card parsing so repeated or collision-prone `card_id` values receive stable hash suffixes.
- Preserve source metadata, timestamps, and jump links while keeping front/back/cloze text free of source artifacts.

## Steps

- [x] Inspect set-3 card counts, flagged cards, duplicate IDs, and source mapping.
- [x] Generate hardened local golden artifacts from ready cards only.
- [x] Reassign golden sample card IDs as `lecture_id:golden-card:<index>-<hash>`.
- [x] Exclude flagged cards from the default golden sample and Anki TSV export.
- [x] Add stable hash suffix generation to OpenAI card parsing.
- [x] Extend source artifact validation to card back and cloze text.
- [x] Add regression tests for similar AI cards and visible source artifacts.
- [x] Record validation results.

## Validation

- `python -m unittest discover -s tests -p "test_openai_anki_cards.py"` passed.
- Full validation results are reported in the implementation handoff for this task.

## Result

- Source set had 43 cards: 42 ready and 1 flagged.
- The flagged card was excluded because of `bad_cloze`.
- Original duplicate card ID excess count was 14.
- Hardened golden sample duplicate card ID excess count is 0.
- Hardened ready cards have 0 source mapping gaps.
- Hardened ready cards have 0 visible source artifacts in front/back/cloze text.
- Local Anki TSV export was generated for the hardened sample.

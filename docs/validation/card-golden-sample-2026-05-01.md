# Card Golden Sample Validation - 2026-05-01

## Scope

- Source set: `.lecturedigest/card-candidate-sets/19a-gpt41-standard/set-3.json`
- User decision: set 3 is the golden card sample candidate.
- Generated artifacts are local only under `.lecturedigest/card-candidate-sets/19a-gpt41-standard/golden-set-3-*`.
- Repository records this validation summary only; generated card artifacts remain excluded from version control.

## Result

| Check | Result |
|---|---:|
| Original cards | 43 |
| Ready cards selected for golden sample | 42 |
| Flagged cards excluded | 1 |
| Original duplicate card ID excess count | 14 |
| Hardened duplicate card ID excess count | 0 |
| Source mapping missing in hardened ready cards | 0 |
| Visible source artifacts in front/back/cloze | 0 |
| Anki TSV generated | Passed |

## Type Distribution

| Card type | Count |
|---|---:|
| `qa` | 29 |
| `cloze` | 11 |
| `application` | 2 |

No `code` cards were selected because the approved note did not provide enough concrete code, command, function, or API examples to justify code cards.

## Excluded Flagged Card

| Original card ID | Type | Reason |
|---|---|---|
| `lec_3f51e7be057c:openai:lec_3f51e7be057c-note-topic_2-cloze-c1-c2` | `cloze` | `bad_cloze` |

The flagged card was excluded from the default golden sample and from the local Anki TSV export.

## Generated Local Artifacts

- `.lecturedigest/card-candidate-sets/19a-gpt41-standard/golden-set-3-store.json`
- `.lecturedigest/card-candidate-sets/19a-gpt41-standard/golden-set-3-cards.json`
- `.lecturedigest/card-candidate-sets/19a-gpt41-standard/golden-set-3-cards.tsv`
- `.lecturedigest/card-candidate-sets/19a-gpt41-standard/golden-set-3-preview.md`
- `.lecturedigest/card-candidate-sets/19a-gpt41-standard/golden-set-3-summary.json`

## Code Hardening

- OpenAI card parsing now creates `card_id` values with a stable hash suffix based on card type, section, front/cloze, back, and source segment IDs.
- Repeated model-provided IDs no longer force collisions when the card content differs.
- Existing source mapping validation remains strict.
- Visible source artifacts are rejected in card front, cloze text, and back text.

## Remaining Risk

- The golden card sample is still a quality baseline, not a final universal rubric.
- Human spot-check should still confirm whether the 42 ready cards are useful enough for real memorization before they become the long-term golden fixture.

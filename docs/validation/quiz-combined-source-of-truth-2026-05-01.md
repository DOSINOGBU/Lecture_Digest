# Quiz Combined Source Of Truth Validation - 2026-05-01

## Decision

The official quiz review pool for the browser understanding lecture is the combined set declared in:

- `docs/golden-samples/quiz-browser-understanding-combined.json`

This pool intentionally combines:

- `legacy_e2e`: 8 existing quiz items from `.lecturedigest/e2e-real-lecture-validation.json`
- `golden_set_3`: 35 hardened quiz items from `.lecturedigest/quiz-candidate-sets/20a-gpt41-standard/golden-set-3-store.json`

No automatic deduplication is applied. All items are kept and tagged by source.

## Validation Result

| Source | Path | Expected | Actual | Status |
|---|---|---:|---:|---|
| `legacy_e2e` | `.lecturedigest/e2e-real-lecture-validation.json` | 8 | 8 | Pass |
| `golden_set_3` | `.lecturedigest/quiz-candidate-sets/20a-gpt41-standard/golden-set-3-store.json` | 35 | 35 | Pass |
| Combined | manifest total | 43 | 43 | Pass |

## Golden Set 3 Summary

| Metric | Value |
|---|---:|
| Total | 35 |
| Ready | 35 |
| Flagged | 0 |
| Multiple choice | 26 |
| Written | 9 |
| Duplicate quiz IDs | 0 |

Answer distribution:

| Label | Count |
|---|---:|
| A | 5 |
| B | 8 |
| C | 5 |
| D | 8 |

## Usage Policy

- 21 Streamlit review workflow should load the combined manifest and show source badges.
- 22 real lecture quality revalidation should report both combined metrics and source-level breakdown.
- `.lecturedigest` generated artifacts remain local and uncommitted.
- The E2E store is not patched; it remains a source in the combined pool.

## Remaining Review

- Human review still needs to inspect whether any of the 43 questions are duplicated or low value.
- If individual items are rejected later, add a curation pass rather than overwriting the original local artifacts.

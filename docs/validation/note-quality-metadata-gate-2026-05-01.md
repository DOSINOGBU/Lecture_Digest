# Note Quality Metadata Gate Validation - 2026-05-01

## Scope

Validated the 18f note quality metadata gate against the real lecture store:

- Store: `.lecturedigest/e2e-real-lecture-validation.json`
- Lecture: `lec_3f51e7be057c`
- Network calls: none
- Original/generated note previews: kept under `.lecturedigest/` and excluded from version control

## Command

```powershell
python -m lecturedigest --store .lecturedigest/e2e-real-lecture-validation.json inspect-note-quality --lecture-id lec_3f51e7be057c
```

## Result Summary

| Metric | Result |
|---|---:|
| Inspected candidates | 3 |
| Overall gate status | `needs_review` |
| Review-ready candidates | 0 |
| Needs-review candidates | 2 |
| Blocked candidates | 1 |
| Total warnings | 12 |
| Visible source artifacts | 0 |
| Source mapping gaps | 0 |

## Candidate Results

| Candidate | Variant | Candidate status | Validation | Gate | Approved | Difficulty metadata | Known acronyms | Source coverage |
|---|---|---|---|---|---:|---:|---:|---:|
| `note-candidate-openai-ea259df092-01` | `balanced` | `rejected` | `flagged` | `blocked` | false | 2/8 | 2/4 | 0.067 |
| `note-candidate-openai-2a91ae966a-02` | `concept_focused` | `rejected` | `review_required` | `needs_review` | false | 7/8 | 4/4 | 0.039 |
| `note-candidate-openai-25fc9d1376-03` | `action_focused` | `approved` | `review_required` | `needs_review` | true | 5/8 | 4/4 | 0.041 |

## Findings

- The approved note has complete known acronym metadata coverage: 4/4.
- The approved note has no visible source artifacts in Markdown.
- The approved note has no source mapping gaps.
- The approved note still needs review because it carries warning flags:
  - `missing_flow_diagram`
  - `missing_comparison_table`
  - `missing_code_block`
  - `coverage_too_sparse`
- The blocked balanced candidate failed on `acronym_explanation_missing`.

## Interpretation

The current approved note is usable as the basis for cards and quizzes, but it should not yet be treated as a fully clean golden note. The remaining issue is not source traceability or acronym metadata; it is warning-level structure and coverage quality.

## Recommended Follow-Up

- Keep the current approved note as the temporary working sample.
- Before long-term golden note promotion, resolve or intentionally waive the expected-structure warnings.
- Surface this gate in the Streamlit review workflow so the user can see why a note is approved but still marked `needs_review`.

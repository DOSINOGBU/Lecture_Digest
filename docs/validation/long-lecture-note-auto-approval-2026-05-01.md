# Long Lecture Note Auto-Approval Validation - 2026-05-01

## Scope

- Lecture id: `lec_175a02f179a6`
- Purpose: verify that a large lecture can produce at least one auto-approvable OpenAI note candidate and continue through cards and quizzes.
- Model: `gpt-4.1`
- Prompt version: `openai-markdown-note-prd-v7-longform`

## Commands

```powershell
python -m lecturedigest generate-notes --lecture-id lec_175a02f179a6 --openai --repair --candidate-limit 1 --time-budget-seconds 1200 --export-preview-dir .lecturedigest\longform-note-preview
python -m lecturedigest inspect-note-quality --lecture-id lec_175a02f179a6
python -m lecturedigest process-lecture --lecture-id lec_175a02f179a6 --openai --resume --time-budget-seconds 1200 --note-candidate-count 1
```

## Result

- `generate-notes` completed with one OpenAI longform candidate.
- Candidate result: `flagged=0`, `reviewRequired=1`.
- Preview export:
  - `.lecturedigest\longform-note-preview\01-note-candidate-openai-372c2c6784-01.md`
- `inspect-note-quality` result:
  - overall: `needs_review`
  - blocked: `0`
  - needsReview: `1`
  - visibleSourceArtifacts: `0`
  - sourceMappingGaps: `0`
  - sourceCoverage: `0.164`
  - difficulty metadata: `4/8`
  - known acronym metadata: `2/2`
- `process-lecture --resume` completed downstream steps:
  - `finalize_transcript`: skipped
  - `chunk`: skipped
  - `index`: skipped
  - `generate_notes`: skipped
  - `auto_approve_note`: completed
  - `generate_cards`: completed
  - `generate_quizzes`: completed

## Remaining Warnings

- `missing_flow_diagram`
- `missing_code_block`

These warnings do not block the draft auto approval. They remain visible for human review because the validator did not find enough evidence to require blocking regeneration.

## Notes

- Validation gates were not weakened. Candidates with failed rules still remain blocked.
- The long lecture issue was resolved by changing generation structure to plan, section batches, assembly, local source-backed reassembly for structural failures, and targeted repair.
- Generated `.lecturedigest` artifacts are local validation outputs and are not committed.

# 26. Long Lecture Note Auto-Approval Hardening

## Status

Completed

## Goal

Make long real lectures produce at least one auto-approvable OpenAI note candidate without weakening the note validation gate.

## Scope

- Add a longform note generation path for expanded/chaptered sources and lectures with many chunks.
- Keep the existing short and medium lecture note path unchanged.
- Preserve the existing CLI surface: `generate-notes --openai --repair --resume`.
- Keep auto approval strict: candidates with failed rules remain blocked.

## Steps

- Added a longform OpenAI note generator using plan, section, and assembly passes.
- Routed `expanded`, `chaptered`, or `chunk_count >= 12` lectures to the longform generator.
- Stored longform metadata under `note_metadata.longform_generation`.
- Added source-backed local reassembly for longform structural failures such as missing source mapping, shallow body, insufficient style variety, and missing difficulty metadata.
- Kept targeted repair for remaining flagged longform candidates.
- Ensured a `review_required` candidate can be auto-approved for draft pipeline continuation.
- Recorded real large lecture validation in `docs/validation/long-lecture-note-auto-approval-2026-05-01.md`.

## Validation

- `python -m unittest discover -s tests -p test_openai_longform_notes.py`
- `python -m compileall lecturedigest tests`
- `python -m lecturedigest generate-notes --lecture-id lec_175a02f179a6 --openai --repair --candidate-limit 1 --time-budget-seconds 1200 --export-preview-dir .lecturedigest\longform-note-preview`
- `python -m lecturedigest inspect-note-quality --lecture-id lec_175a02f179a6`
- `python -m lecturedigest process-lecture --lecture-id lec_175a02f179a6 --openai --resume --time-budget-seconds 1200 --note-candidate-count 1`

Full repository validation was run after implementation; see final task report for current warning state.

## Result

- The long lecture `lec_175a02f179a6` produced one `review_required` candidate with no failed rules.
- `inspect-note-quality` reported `blocked=0`, `needsReview=1`, `visibleSourceArtifacts=0`, and `sourceMappingGaps=0`.
- The auto pipeline resumed and completed `auto_approve_note`, `generate_cards`, and `generate_quizzes`.
- Remaining note warnings are `missing_flow_diagram` and `missing_code_block`; these remain human review warnings, not auto approval blockers.

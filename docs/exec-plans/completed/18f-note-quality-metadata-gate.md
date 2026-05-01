# 18f. Note Quality Metadata Gate

## Status

Completed on 2026-05-01.

## Goal

Add a lightweight quality gate that inspects generated note candidates before UI work continues. The gate summarizes whether approved or reviewable notes preserve beginner explanations, acronym metadata, source traceability, and visible Markdown cleanliness.

## Scope

- Add a CLI command to inspect note candidate quality from the local lecture store.
- Focus on existing note outputs and metadata; do not call OpenAI.
- Report candidate status, validation failed rules, warnings, difficulty explanation counts, known acronym coverage, source mapping gaps, and visible source artifacts.
- Support an optional `--candidate-id` filter.
- Keep output readable in CLI for empty, success, and warning/error states.
- Record validation findings for the current real lecture sample.

## Out Of Scope

- Regenerating notes.
- Changing the note prompt.
- Approving or rejecting candidates automatically.
- Streamlit UI changes.

## Steps

- [x] Add note quality inspection use case.
- [x] Expose it through CLI as `inspect-note-quality`.
- [x] Add tests for empty store, missing lecture, approved candidate, flagged candidate, acronym metadata, and visible source artifact reporting.
- [x] Run the gate against the real lecture store and record findings.
- [x] Move this plan to completed with Result.

## Validation

- `python -m unittest discover -s tests -p "test_note_quality.py"` passed.
- `python -m unittest discover -s tests -p "test_note_cli.py"` passed.
- Full validation results are reported in the implementation handoff for this task.

## Result

- Added `inspect-note-quality`.
- Real lecture inspection found 3 note candidates:
  - 1 blocked candidate because of `acronym_explanation_missing`.
  - 2 needs-review candidates.
  - 0 clean review-ready candidates.
- The approved note has complete known acronym metadata coverage, no visible source artifacts, and no source mapping gaps.
- The approved note still carries warning-level structure and coverage flags, so it should remain a temporary working sample rather than a fully clean golden note.

## Validation Record

- `docs/validation/note-quality-metadata-gate-2026-05-01.md`

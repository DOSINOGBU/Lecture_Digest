# Note PRD Quality Repair Validation - 2026-04-30

## Scope

This report records validation for `docs/exec-plans/active/18a-note-prd-quality-repair.md`.

Repository policy was followed:

- Original video: excluded from repository.
- Full subtitle file: excluded from repository.
- Full generated note previews: exported locally under `.lecturedigest/` and excluded from repository.
- API key and local sensitive paths: excluded from repository.
- Golden note sample: not added because human approval is still pending.

## Input

| Item | Value |
|---|---|
| Lecture ID | `lec_3f51e7be057c` |
| Transcript source | Subtitle import, not STT |
| Segments | 564 |
| Chunks | 21 |
| Content strategy | `standard` |

## Scenario Log

```powershell
python -m lecturedigest --store .lecturedigest\e2e-real-lecture-validation.json generate-notes --lecture-id lec_3f51e7be057c --openai --dry-run --repair
python -m lecturedigest --store .lecturedigest\e2e-real-lecture-validation.json generate-notes --lecture-id lec_3f51e7be057c --openai --repair --max-repair-attempts 2 --export-preview-dir .lecturedigest\note-previews\18a
```

## API Boundary

| Operation | Actual external upload? | Model | Prompt version | Requests |
|---|---:|---|---|---:|
| OpenAI note dry-run | No | `gpt-4o` | `openai-markdown-note-prd-v2` | 3 |
| OpenAI note generation | Yes | `gpt-4o` | `openai-markdown-note-prd-v2` | 3 |
| OpenAI note repair | Yes | `gpt-4o` | `openai-markdown-note-prd-v2+repair-v1` | 2 |

Actual call metadata:

| Request | Use case | Status | Duration | Input size |
|---:|---|---|---:|---:|
| 1 | `note_generation` | succeeded | 21,560 ms | 47,055 bytes |
| 2 | `note_generation` | succeeded | 18,821 ms | 47,069 bytes |
| 3 | `note_generation` | succeeded | 17,532 ms | 47,067 bytes |
| 4 | `note_generation_repair` | succeeded | 31,668 ms | 61,451 bytes |
| 5 | `note_generation_repair` | succeeded | 13,146 ms | 58,753 bytes |

## Repair Result

| Candidate | Variant | Initial status | Initial failed rules | Final status | Final failed rules | Counts |
|---|---|---|---|---|---|---|
| `note-candidate-openai-9e00ae0441-01` | `balanced` | `flagged` | `insufficient_key_terms` | `review_required` | none | goals 4, topics 4, terms 8, questions 8 |
| `note-candidate-openai-6c1c2fe31d-02` | `concept_focused` | `review_required` | none | `review_required` | none | goals 4, topics 3, terms 8, questions 8 |
| `note-candidate-openai-948763e04f-03` | `action_focused` | `flagged` | `source_mapping_missing`, `insufficient_review_questions`, `insufficient_core_topics` | `review_required` | none | goals 4, topics 3, terms 8, questions 8 |

Common remaining warnings:

- `missing_flow_diagram`
- `missing_code_block`

These warnings do not block human review because the validator treats unsupported optional structures as review items rather than automatic approval blockers.

## Preview Export

Local preview files were generated:

| File | Size |
|---|---:|
| `.lecturedigest/note-previews/18a/01-note-candidate-openai-9e00ae0441-01.md` | 6,005 bytes |
| `.lecturedigest/note-previews/18a/02-note-candidate-openai-6c1c2fe31d-02.md` | 4,949 bytes |
| `.lecturedigest/note-previews/18a/03-note-candidate-openai-948763e04f-03.md` | 4,440 bytes |

## Quality Gate

| Criterion | Status | Evidence |
|---|---|---|
| OpenAI candidates generated | Pass | 3 candidates generated |
| Flagged candidates repaired | Pass | 2 flagged candidates repaired |
| At least one `review_required` candidate | Pass | 3 candidates are `review_required` |
| Preview export for human review | Pass | 3 Markdown files exported locally |
| Golden note approval | Blocked | Human approval is required |
| Hallucination check | Blocked | Requires human review against the lecture |

## Conclusion

The PRD note generation path is now stable enough to enter human review. All three current candidates are structurally valid and source-mapped according to the automated validator, but they are not golden notes yet. The next manual step is to read the preview files, compare them against the lecture, and approve or reject one candidate.

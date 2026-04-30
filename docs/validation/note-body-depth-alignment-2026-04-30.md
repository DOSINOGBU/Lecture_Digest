# Note Body Depth Alignment Validation - 2026-04-30

## Scope

This report records validation for `docs/exec-plans/active/18b-note-body-depth-alignment.md`.

Repository policy was followed:

- Original video: excluded from repository.
- Full subtitle file: excluded from repository.
- Full generated note previews: exported locally under `.lecturedigest/` and excluded from repository.
- API key and local sensitive paths: excluded from repository.
- User-provided reference note: used as quality reference, not copied into repository.
- Golden note sample: not added because human approval is still pending.

## Reference Note

User-provided target note:

- File name: `02. 결국 브라우저가 이해하는 것 - 강의노트.md`
- Characters: 7,858
- Lines: 343
- H2 headings: 17
- H3 headings: 5
- Code fences: 4

The target quality is a textbook-style study note, not a short cited outline.

## Implementation Notes

- Default OpenAI note model was raised from `gpt-4o` to `gpt-4.1`.
- Prompt version was raised to `openai-markdown-note-prd-v3`.
- Body depth validation now checks document length, topic body depth, H3 usage, explanatory depth, and sparse source coverage.
- `generate-notes --openai-timeout-seconds` was added because `gpt-4.1` long-form note generation exceeded the previous 60 second request timeout.

## Scenario Log

```powershell
python -m lecturedigest --store .lecturedigest\e2e-real-lecture-validation.json generate-notes --lecture-id lec_3f51e7be057c --openai --dry-run --repair
python -m lecturedigest --store .lecturedigest\e2e-real-lecture-validation.json generate-notes --lecture-id lec_3f51e7be057c --openai --repair --max-repair-attempts 5 --openai-timeout-seconds 240 --export-preview-dir .lecturedigest\note-previews\18b-gpt41
```

## API Boundary

| Operation | Actual external upload? | Model | Prompt version | Requests |
|---|---:|---|---|---:|
| OpenAI note dry-run | No | `gpt-4.1` | `openai-markdown-note-prd-v3` | 3 |
| OpenAI note generation | Yes | `gpt-4.1` | `openai-markdown-note-prd-v3` | 3 |
| OpenAI note repair | No | `gpt-4.1` | `openai-markdown-note-prd-v3+repair-v1` | 0 |

Actual generation metadata:

| Request | Use case | Status | Duration | Input size |
|---:|---|---|---:|---:|
| 1 | `note_generation` | succeeded | 82,975 ms | 49,960 bytes |
| 2 | `note_generation` | succeeded | 60,864 ms | 49,974 bytes |
| 3 | `note_generation` | succeeded | 50,566 ms | 49,972 bytes |

## Output Comparison

| Candidate | Variant | Status | Chars | Lines | H2 | H3 | Topics | Topic avg chars | Key terms | Questions |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `note-candidate-openai-c9e956126b-01` | `balanced` | `review_required` | 8,750 | 142 | 11 | 18 | 6 | 633 | 13 | 9 |
| `note-candidate-openai-ff3ebfbdd2-02` | `concept_focused` | `review_required` | 9,253 | 142 | 11 | 18 | 6 | 869 | 12 | 10 |
| `note-candidate-openai-93b9690d44-03` | `action_focused` | `review_required` | 8,179 | 150 | 11 | 18 | 6 | 630 | 14 | 15 |

Remaining warnings:

- `missing_flow_diagram`
- `missing_comparison_table` on some variants
- `missing_code_block`
- `coverage_too_sparse`

These warnings do not block human review. They indicate optional structures or source coverage characteristics that a human should inspect before approving a golden note.

## Preview Export

Local preview files were generated:

| File | Size |
|---|---:|
| `.lecturedigest/note-previews/18b-gpt41/01-note-candidate-openai-c9e956126b-01.md` | 8,750 bytes |
| `.lecturedigest/note-previews/18b-gpt41/02-note-candidate-openai-ff3ebfbdd2-02.md` | 9,253 bytes |
| `.lecturedigest/note-previews/18b-gpt41/03-note-candidate-openai-93b9690d44-03.md` | 8,179 bytes |

## Quality Gate

| Criterion | Status | Evidence |
|---|---|---|
| Body depth validator added | Pass | Body depth metrics and rules included in validation payload |
| Prompt requests textbook-style notes | Pass | `openai-markdown-note-prd-v3` includes body depth policy and H3 section guidance |
| At least one candidate passes body depth validation | Pass | 3 candidates are `review_required` |
| Generated note length is comparable to reference note | Pass | 8,179-9,253 chars vs reference 7,858 chars |
| Preview export for human review | Pass | 3 Markdown files exported locally |
| Golden note approval | Blocked | Human approval is required |
| Hallucination check | Blocked | Requires human review against the lecture |

## Conclusion

`gpt-4o` could follow the structure but repeatedly produced short outline-like notes. Raising the note generation model to `gpt-4.1` produced textbook-style candidates that pass the automated body-depth gate. The next manual step is to read the `18b-gpt41` previews and approve or reject one candidate as the golden note candidate.

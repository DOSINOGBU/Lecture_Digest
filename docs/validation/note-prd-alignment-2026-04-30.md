# Note PRD Alignment Validation - 2026-04-30

## Scope

This report records validation for `docs/exec-plans/active/18-note-structure-prd-alignment.md`.

Repository policy was followed:

- Original video: excluded from repository.
- Full subtitle file: excluded from repository.
- Full generated note candidates: excluded from repository.
- API key and local sensitive paths: excluded from repository.
- Golden note sample: not added because human approval is still pending.

## Redacted Input

| Item | Value |
|---|---|
| Lecture ID | `lec_3f51e7be057c` |
| Lecture title | `결국 브라우저가 이해하는 것` |
| Transcript source | Subtitle import, not STT |
| Segments | 564 |
| Chunks | 21 |
| Existing note candidates | Pre-PRD candidates treated as non-golden |

## Scenario Log

```powershell
python -m lecturedigest --store .lecturedigest/e2e-real-lecture-validation.json generate-notes --lecture-id lec_3f51e7be057c --openai --dry-run
python -m lecturedigest --store .lecturedigest/e2e-real-lecture-validation.json generate-notes --lecture-id lec_3f51e7be057c --openai
```

## PRD Content Profile

| Field | Value |
|---|---:|
| `estimated_tokens` | 3078 |
| `word_count` | 2948 |
| `non_space_character_count` | 9234 |
| `segment_count` | 564 |
| `topic_shift_count` | 6 |
| `has_code_or_commands` | true |
| `has_process_flow` | true |
| `has_comparison` | true |
| `strategy` | `standard` |

## API Boundary

| Operation | Actual external upload? | Model | Prompt version | Input |
|---|---:|---|---|---:|
| OpenAI note dry-run | No | `gpt-4o` | `openai-markdown-note-prd-v2` | 141,191 bytes total |
| OpenAI note generation | Yes | `gpt-4o` | `openai-markdown-note-prd-v2` | 3 requests |

Actual call metadata:

| Request | Status | Duration | Input size |
|---|---|---:|---:|
| 1 | succeeded | 23,450 ms | 47,055 bytes |
| 2 | succeeded | 26,174 ms | 47,069 bytes |
| 3 | succeeded | 33,586 ms | 47,067 bytes |

## Observed Output

| Candidate | Variant | Status | Sections | Failed rules | Counts |
|---|---|---|---:|---|---|
| `note-candidate-openai-9e00ae0441-01` | `balanced` | `flagged` | 8 | `insufficient_core_topics` | goals 4, topics 2, terms 8, questions 8 |
| `note-candidate-openai-6c1c2fe31d-02` | `concept_focused` | `flagged` | 10 | `insufficient_review_questions` | goals 4, topics 4, terms 8, questions 5 |
| `note-candidate-openai-948763e04f-03` | `action_focused` | `flagged` | 9 | `insufficient_review_questions` | goals 4, topics 3, terms 8, questions 7 |

Common warnings:

- `missing_flow_diagram`
- `missing_code_block`

## Quality Gate

| Criterion | Status | Evidence |
|---|---|---|
| PRD title first line | Pass | Generated Markdown starts with `# 결국 브라우저가 이해하는 것` |
| PRD required sections | Pass | Summary, goals, numbered topics, practical view, key terms, review questions, final summary were generated |
| Source timestamp mapping | Pass for generated sections | Generated sections retained segment IDs and timestamp citations |
| Standard note count policy | Partial | Goals and terms met minimums; topic/question counts failed on some variants |
| Flow/code structure | Partial | Source profile expected flow/code structures, but generated candidates omitted them |
| Golden note approval | Blocked | Human approval is still required |
| Hallucination check | Blocked | Requires human review against the lecture |

## Conclusion

The PRD-aligned generation path works end-to-end and produces richer Markdown structure than the previous four-section MVP note. However, all three candidates remain validation flagged and must not be promoted to golden notes yet.

Follow-up quality work is tracked in `docs/exec-plans/tech-debt-tracker.md` and should be revalidated in `22-real-lecture-quality-revalidation.md`.

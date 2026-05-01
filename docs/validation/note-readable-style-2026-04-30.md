# Note Readable Style Validation - 2026-04-30

## Scope

This report records validation for `18c-note-readable-style-and-adaptive-length`.

Repository policy was followed:

- Original video: excluded from repository.
- Full subtitle file: excluded from repository.
- Full generated note previews: exported locally under `.lecturedigest/` and excluded from repository.
- API key and local sensitive paths: excluded from repository.
- Golden note sample: not added because human approval is still pending.

## Implementation Notes

- Prompt version was raised to `openai-markdown-note-prd-v4`.
- Visible source citations were removed from the generated Markdown contract.
- Section source mapping remains required through `source_segment_ids` and internal section metadata.
- Adaptive length policy now supports `tiny`, `compact`, `short`, `standard`, `expanded`, and `chaptered`.
- Body depth metrics are calculated after stripping source artifacts from rendered Markdown.
- Topic style validation now rejects generic repeated templates such as `Concept / Why It Matters / Lecture Flow / Example`.

## Scenario Log

```powershell
python -m lecturedigest --store .lecturedigest\e2e-real-lecture-validation.json generate-notes --lecture-id lec_3f51e7be057c --openai --dry-run --repair
python -m lecturedigest --store .lecturedigest\e2e-real-lecture-validation.json generate-notes --lecture-id lec_3f51e7be057c --openai --repair --max-repair-attempts 5 --openai-timeout-seconds 240 --export-preview-dir .lecturedigest\note-previews\18c-gpt41
```

## API Boundary

| Operation | Actual external upload? | Model | Prompt version | Requests |
|---|---:|---|---|---:|
| OpenAI note dry-run | No | `gpt-4.1` | `openai-markdown-note-prd-v4` | 3 |
| OpenAI note generation | Yes | `gpt-4.1` | `openai-markdown-note-prd-v4` | 3 |

Dry-run total input size: 152,075 bytes.

## Output Summary

| Candidate | Variant | Status | Preview chars | Preview lines | Failed rules |
|---|---|---|---:|---:|---|
| `note-candidate-openai-9f0c883a89-01` | `balanced` | `review_required` | 6,079 | 139 | none |
| `note-candidate-openai-2bd11711d4-02` | `concept_focused` | `review_required` | 6,254 | 157 | none |
| `note-candidate-openai-20245549c4-03` | `action_focused` | `review_required` | 7,287 | 154 | none |

Remaining warnings on all three candidates:

- `missing_flow_diagram`
- `missing_comparison_table`
- `missing_code_block`
- `coverage_too_sparse`

These warnings do not block human review. They mark optional structures and coverage characteristics for manual inspection.

## Readability Gate

| Criterion | Status | Evidence |
|---|---|---|
| No visible `(source:)` citations | Pass | Preview scan returned no matches |
| No visible `seg-...` IDs | Pass | Preview scan returned no matches |
| No visible timestamp artifacts | Pass | Preview scan returned no matches |
| Source mapping preserved | Pass | `source_segment_ids` remains required and validator keeps `source_mapping_missing` |
| Adaptive short-source policy | Pass | tiny/compact tests do not force 6,000 chars |
| Adaptive long-source policy | Pass | chaptered policy does not impose a 10,000 char single-note cap |
| Generic topic template rejected | Pass | unit tests cover `generic_subheading_present` and `repetitive_topic_template` |
| At least one candidate ready for review | Pass | 3 candidates are `review_required` |

## Required Checks

| Check | Result |
|---|---|
| `python -m unittest discover -s tests` | Pass, 197 tests |
| `python -m compileall lecturedigest tests` | Pass |
| `git diff --check` | Pass with line-ending warnings only |
| `scripts/validate-harness.ps1 -Mode Project` | Pass |
| `scripts/validate-harness.ps1 -CodeHealth -Mode Project` | Pass |

## Conclusion

The generated notes are now readable Markdown without visible source/timestamp noise, while source traceability remains in metadata. The next manual step is to read the `18c-gpt41` previews and decide whether one candidate can become the golden note baseline.

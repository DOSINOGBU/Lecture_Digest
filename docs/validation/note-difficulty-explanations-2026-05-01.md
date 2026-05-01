# Note Difficulty Explanations Validation - 2026-05-01

## Scope

This report records validation for `18d-difficulty-aware-note-explanations`.

Repository policy was followed:

- Original video: excluded from repository.
- Full subtitle file: excluded from repository.
- Full generated note previews: exported locally under `.lecturedigest/` and excluded from repository.
- API key and local sensitive paths: excluded from repository.
- Golden note sample: not added because human approval is still pending.

## Implementation Notes

- Prompt version was raised to `openai-markdown-note-prd-v5`.
- Difficult concepts are detected from source text and generated sections.
- Candidate metadata preserves `notes.difficulty_explanations`.
- Validation checks that difficult concepts have beginner-friendly explanations in the visible body and traceable metadata.
- Local fallback adds a minimal beginner explanation for detected difficult terms.

## Scenario Log

```powershell
python -m lecturedigest --store .lecturedigest\e2e-real-lecture-validation.json generate-notes --lecture-id lec_3f51e7be057c --openai --dry-run --repair
python -m lecturedigest --store .lecturedigest\e2e-real-lecture-validation.json generate-notes --lecture-id lec_3f51e7be057c --openai --repair --max-repair-attempts 5 --openai-timeout-seconds 240 --export-preview-dir .lecturedigest\note-previews\18d-gpt41
```

The full CLI generation process exceeded the 15 minute command limit. The remaining process was stopped manually. The store file was not changed and no partial preview directory was written.

To validate the actual API path without repeating three long calls, a single `balanced` candidate was generated with the same model and prompt version.

## API Boundary

| Operation | Actual external upload? | Model | Prompt version | Requests |
|---|---:|---|---|---:|
| OpenAI note dry-run | No | `gpt-4.1` | `openai-markdown-note-prd-v5` | 3 |
| OpenAI note generation, full CLI | Yes | `gpt-4.1` | `openai-markdown-note-prd-v5` | timed out |
| OpenAI note generation, single candidate | Yes | `gpt-4.1` | `openai-markdown-note-prd-v5` | 1 |

Dry-run total input size: 157,760 bytes.

Single candidate actual call:

| Variant | Status | Duration | Input size | Validation |
|---|---|---:|---:|---|
| `balanced` | succeeded | 62,978 ms | 52,730 bytes | `review_required` |

## Output Summary

| Candidate | Variant | Status | Preview chars | Preview lines | Failed rules |
|---|---|---|---:|---:|---|
| `note-candidate-openai-853b2b138d-01` | `balanced` | `review_required` | 6,521 | 136 | none |

Difficulty validation:

| Metric | Value |
|---|---:|
| expected difficult concepts | 8 |
| metadata explanations | 4 |
| visible easy markers | 3 |

Metadata terms included:

- `DOM`
- `하이레벨/로우레벨`
- `렌더링 엔진`
- `렌더 트리`

Remaining warnings:

- `missing_flow_diagram`
- `missing_code_block`
- `coverage_too_sparse`

## Readability Gate

| Criterion | Status | Evidence |
|---|---|---|
| Easy explanations in visible body | Pass | Preview includes `쉽게 풀이` and `초보자를 위한 TIP` |
| Difficulty metadata preserved | Pass | `generator_notes.difficulty_explanations` included 4 terms |
| No visible `(source:)` citations | Pass | Preview scan returned no matches |
| No visible `seg-...` IDs | Pass | Preview scan returned no matches |
| No visible timestamp artifacts | Pass | Preview scan returned no matches |
| At least one actual candidate ready for review | Pass | Single `balanced` candidate is `review_required` |
| Full 3-candidate actual CLI validation | Partial | Timed out before completion |

## Required Checks

| Check | Result |
|---|---|
| `python -m unittest discover -s tests` | Pass, 203 tests |
| `python -m compileall lecturedigest tests` | Pass |
| `git diff --check` | Pass with line-ending warnings only |
| `scripts/validate-harness.ps1 -Mode Project` | Pass |
| `scripts/validate-harness.ps1 -CodeHealth -Mode Project` | Pass |

## Conclusion

18d adds difficulty-aware explanations without exposing source artifacts in the rendered note. The actual single-candidate API path passes validation, but the full three-candidate CLI run needs a follow-up runtime/retry strategy before it can be considered fully validated end to end.

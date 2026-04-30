# Real Lecture E2E Validation - 2026-04-30

## Scope

This report records the manual validation for `docs/exec-plans/active/17-end-to-end-real-lecture-validation.md`.

Repository policy was followed:

- Original video: excluded from repository.
- Full subtitle file: excluded from repository.
- Full OCR raw text: excluded from repository.
- API key and local sensitive paths: excluded from repository.
- Golden note sample: not added because a human-approved sample is still pending.

## Redacted Input

| Item | Value |
|---|---|
| Lecture ID | `lec_3f51e7be057c` |
| Lecture title | `결국 브라우저가 이해하는 것` |
| Video source | Local MP4 path redacted |
| Video size | 244,106,516 bytes |
| Video preflight | 1920x1080, 1536.999 seconds |
| Subtitle source | Local SRT path redacted |
| Subtitle size | 51,615 bytes |
| Transcript source | Subtitle import, not STT |

## Scenario Log

Commands below use redacted placeholders for local paths.

```powershell
python -m lecturedigest --store .lecturedigest\e2e-real-lecture-validation.json register --video <LOCAL_VIDEO_PATH> --subtitle <LOCAL_SUBTITLE_PATH> --title "결국 브라우저가 이해하는 것" --instructor "Unknown" --category "Coding"
python -m lecturedigest --store .lecturedigest\e2e-real-lecture-validation.json chunk --lecture-id lec_3f51e7be057c --chapter "Ch 2 JS and Browser Understanding"
python -m lecturedigest --store .lecturedigest\e2e-real-lecture-validation.json finalize-transcript --lecture-id lec_3f51e7be057c --openai --dry-run --batch-size 64
python -m lecturedigest --store .lecturedigest\e2e-real-lecture-validation.json ocr --lecture-id lec_3f51e7be057c --dry-run --method interval --sample-interval-seconds 300
$env:PYTHONUTF8='1'; python -m lecturedigest --store .lecturedigest\e2e-real-lecture-validation.json ocr --lecture-id lec_3f51e7be057c --dry-run --method interval --sample-interval-seconds 300
python -m lecturedigest --store .lecturedigest\e2e-real-lecture-validation.json summarize --lecture-id lec_3f51e7be057c
python -m lecturedigest --store .lecturedigest\e2e-real-lecture-validation.json index --lecture-id lec_3f51e7be057c --embed-openai
python -m lecturedigest --store .lecturedigest\e2e-real-lecture-validation.json generate-notes --lecture-id lec_3f51e7be057c
python -m lecturedigest --store .lecturedigest\e2e-real-lecture-validation.json approve-note --lecture-id lec_3f51e7be057c --candidate-id note-candidate-3d852dafc4-01
python -m lecturedigest --store .lecturedigest\e2e-real-lecture-validation.json generate-cards --lecture-id lec_3f51e7be057c --max-cards 12
python -m lecturedigest --store .lecturedigest\e2e-real-lecture-validation.json generate-quizzes --lecture-id lec_3f51e7be057c --quiz-count 8 --seed 42
python -m lecturedigest --store .lecturedigest\e2e-real-lecture-validation.json export-anki --lecture-id lec_3f51e7be057c --output .lecturedigest\e2e-exports\real-lecture-anki.tsv
python -m lecturedigest --store .lecturedigest\e2e-real-lecture-validation.json export-anki --lecture-id lec_3f51e7be057c --format json --output .lecturedigest\e2e-exports\real-lecture-anki.json
python -m lecturedigest --store .lecturedigest\e2e-real-lecture-validation.json ask --lecture-id lec_3f51e7be057c --question "브라우저가 이해하는 것은 무엇인가?" --top-k 3 --embed-openai
```

## Observed Output

| Area | Result |
|---|---|
| Subtitle segments | 564 |
| Chunks | 21 |
| Search index entries | 21 |
| Embedding status | 21/21 ready |
| Embedding model | `text-embedding-3-large` |
| Vector store | `local_json` |
| Note candidates | 3 generated, 3 flagged |
| Approved note | Technical pipeline approval only; not human golden approval |
| Approved note validation | `flagged` |
| Note section timestamp links | 4/4 |
| Anki cards | 10 ready, 10/10 timestamp-linked |
| Quiz items | 8 ready, 8/8 timestamp-linked |
| OCR slides | 0 saved; Vision OCR was dry-run only |
| Anki TSV export | `.lecturedigest/e2e-exports/real-lecture-anki.tsv`, 140,075 bytes |
| Anki JSON export | `.lecturedigest/e2e-exports/real-lecture-anki.json`, 262,702 bytes |
| RAG answer | Vector strategy returned 3 cited results |

## API Boundary

| Operation | Actual external upload? | Model | Notes |
|---|---:|---|---|
| Transcript correction | No | `gpt-4o` | Dry-run only; 9 batches, 564 segments |
| Vision OCR | No | `gpt-4o` | Dry-run only; frame upload not performed |
| Chunk embedding | Yes | `text-embedding-3-large` | 21 chunks embedded successfully |
| Query embedding | Yes | `text-embedding-3-large` | RAG query used vector strategy |

## Quality Gate

| Criterion | Status | Evidence |
|---|---|---|
| Source timestamps 100% linked | Pass for generated artifacts | 22/22 note/card/quiz items had segment/timestamp links |
| Key concepts not missing | Blocked | Needs human golden-note approval against lecture content |
| No hallucination | Blocked | Needs human review; generated note candidates are flagged |
| OCR-needed areas marked | Blocked | 1080p preflight succeeded, but actual Vision OCR was not run |
| Anki convertible | Pass | TSV and JSON exports generated from approved note state |
| Repository data policy | Pass in inspected outputs | Original video, full subtitle, OCR raw text, API key, and local sensitive paths were not added |

## Findings

- The first OCR dry-run failed on Windows when ffprobe output was decoded under the default CP949 environment. Retrying with `PYTHONUTF8=1` succeeded.
- Parallel CLI commands that write to the same JSON store can overwrite or corrupt local validation state. Store writes should be serialized or made atomic before larger real-world runs.
- The generated note candidates are structurally valid but all flagged by validation because the length ratio is outside the target range. They are not yet suitable as golden samples.
- The approved note used here was a technical pipeline approval to exercise downstream card, quiz, and export steps. It is not a human-approved golden note.

## Verdict

Partial. The E2E pipeline can process a real lecture into chunks, embeddings, notes, Anki cards, quizzes, exports, and vector RAG citations. The MVP quality gate is not complete until human note approval and real OCR sample validation are done.

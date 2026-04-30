# 18c. 읽기용 노트 스타일 정리 + 적응형 분량 정책

## 상태

완료

## 목표

18b에서 본문 밀도는 좋아졌지만, preview Markdown에 `(source: seg-... @ timestamp)`가 노출되어 읽기용 학습노트로는 거슬렸다. 또한 고정 글자 수 기준은 1분 강의와 1~3시간 강의 모두에 맞지 않는다.

18c의 목표는 다음이다.

- 사람이 읽는 Markdown에서는 source artifact를 제거한다.
- 출처 연결은 section metadata로만 유지한다.
- 강의 시간이 아니라 정제 텍스트 양과 주제 밀도로 노트 분량을 조절한다.
- 주제별 본문 형식을 고정 템플릿이 아니라 내용에 맞게 다양화한다.

## 범위

- `note_depth`에 adaptive body length policy를 추가한다.
- `note_prd` validator에서 visible source artifact를 차단한다.
- OpenAI note/repair prompt에서 visible citation 요구를 제거한다.
- OpenAI parser가 본문 텍스트에서 segment id를 긁어오지 않고 `source_segment_ids` metadata를 사용하게 한다.
- local fallback Markdown에서도 visible citation을 제거한다.
- 실제 강의 샘플로 OpenAI 후보를 재생성하고 preview를 검증한다.
- 카드, 퀴즈, UI는 변경하지 않는다.

## 적응형 분량 정책

노트 분량은 `estimated_tokens`, `topic_shift_count`, `chunk_count`, `segment_count`를 기반으로 판단한다.

| strategy | 기준 | 목표 분량 |
|---|---|---|
| `tiny` | `< 300 tokens` | 500~1,200자 |
| `compact` | `300~700 tokens` | 1,000~2,500자 |
| `short` | `700~1,800 tokens` | 2,500~5,000자 |
| `standard` | `1,800~4,500 tokens` | 5,000~10,000자 |
| `expanded` | `4,500~12,000 tokens` | 10,000~20,000자 |
| `chaptered` | `> 12,000 tokens` 또는 topic shift가 많음 | 챕터별 부분 노트 + master summary |

짧은 강의는 억지로 6,000자 이상으로 늘리지 않는다. 긴 강의는 10,000자 상한으로 억지 압축하지 않고 chaptered 산출을 허용한다.

## 추가 validation 규칙

- `visible_source_artifacts`: Markdown 본문에 `(source:)`, `seg-...`, timestamp가 보이면 실패
- `generic_subheading_present`: `### Concept`, `### Why It Matters`, `### Lecture Flow`, `### Example` 같은 고정 템플릿 heading이 보이면 실패
- `repetitive_topic_template`: 여러 topic이 같은 H3 구조를 반복하면 실패
- `insufficient_style_variety`: topic 형식이 지나치게 단조로우면 실패

본문 길이 계산은 visible source artifact를 제거한 순수 Markdown 기준으로 수행한다.

## 작업 결과

- `openai-markdown-note-prd-v4` prompt로 올렸다.
- prompt와 repair prompt에서 visible citation 요구를 제거했다.
- `source_segment_ids` metadata를 출처 연결의 주 경로로 고정했다.
- local fallback의 `_citation()` 기반 표시를 제거했다.
- validator가 source artifact와 반복 템플릿을 잡도록 보강했다.
- profile 전략을 `tiny`, `compact`, `short`, `standard`, `expanded`, `chaptered`로 세분화했다.
- 실제 강의 `lec_3f51e7be057c`를 `gpt-4.1`로 재생성했고, 후보 3개 모두 `review_required` 상태가 됐다.
- preview 파일은 `.lecturedigest/note-previews/18c-gpt41/`에 생성했다. 이 경로는 저장소에 포함하지 않는다.
- validation report는 `docs/validation/note-readable-style-2026-04-30.md`에 기록했다.

## 검증

- `python -m unittest discover -s tests`
- `python -m compileall lecturedigest tests`
- `git diff --check`
- `powershell -ExecutionPolicy Bypass -File scripts/validate-harness.ps1 -Mode Project`
- `powershell -ExecutionPolicy Bypass -File scripts/validate-harness.ps1 -CodeHealth -Mode Project`
- 실제 강의 OpenAI dry-run
- 실제 강의 OpenAI generation + preview export
- preview Markdown source artifact scan

## 남은 확인

- 골든 노트 승인은 사용자가 직접 읽고 결정해야 한다.
- `missing_flow_diagram`, `missing_comparison_table`, `missing_code_block`, `coverage_too_sparse`는 review warning으로 남아 있으며 22번 품질 재검증에서 다시 본다.

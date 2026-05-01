# 18d. 어려운 개념 쉬운 설명 보강

## 상태

완료

## 목표

18c에서 읽기용 Markdown과 적응형 분량 정책은 정리됐다. 18d는 카드/퀴즈로 넘어가기 전에, 난이도가 높은 개념을 입문자도 이해할 수 있도록 노트 본문 안에서 자연스럽게 풀어 설명하는 품질 기준을 추가한다.

## 확정 정책

- 표시 위치: 노트 본문 안에 포함
- 설명 수준: 분야와 무관하게 입문자 기준
- 외부 지식: 쉬운 비유/직관 설명에 한해 제한적으로 허용
- 금지: 강의에 없는 사실 주장, visible source/timestamp, 반복 템플릿화
- 출처: 본문에는 표시하지 않고 `source_segment_ids` metadata로 유지

## 범위

- 어려운 개념 감지 helper를 추가한다.
- OpenAI note/repair prompt를 `openai-markdown-note-prd-v5`로 올린다.
- 후보 metadata에 `notes.difficulty_explanations`를 보존한다.
- validator가 본문과 metadata를 함께 검사한다.
- local fallback은 최소 수준의 쉬운 설명을 생성한다.
- 카드, 퀴즈, UI는 변경하지 않는다.

## 추가 validation 규칙

- `difficult_concept_explanation_missing`: 어려운 개념이 감지됐는데 본문/metadata 설명이 부족함
- `easy_explanation_too_jargony`: 쉬운 설명이 다시 전문용어 위주임
- `unsupported_easy_explanation`: 출처 metadata가 없거나 unsupported로 표시됨
- `easy_explanation_overused`: 같은 쉬운 설명 문구를 과도하게 반복함

## 작업 결과

- `note_difficulty` 모듈을 추가해 어려운 개념 감지와 쉬운 설명 검증을 분리했다.
- OpenAI prompt와 repair prompt에 `difficulty_explanation_policy`를 추가했다.
- parser가 `notes.difficulty_explanations`를 `generator_notes`로 보존하게 했다.
- local fallback이 감지된 어려운 개념에 대해 짧은 입문자용 설명을 본문에 넣고 metadata를 남기게 했다.
- 실제 강의 `lec_3f51e7be057c`의 단일 `balanced` 후보를 `gpt-4.1` / `openai-markdown-note-prd-v5`로 생성했고 `review_required`를 확인했다.
- 단일 preview는 `.lecturedigest/note-previews/18d-gpt41-single/`에 생성했다. 이 경로는 저장소에 포함하지 않는다.

## 검증

- `python -m unittest discover -s tests`
- `python -m compileall lecturedigest tests`
- `git diff --check`
- `powershell -ExecutionPolicy Bypass -File scripts/validate-harness.ps1 -Mode Project`
- `powershell -ExecutionPolicy Bypass -File scripts/validate-harness.ps1 -CodeHealth -Mode Project`
- OpenAI dry-run 3 requests
- OpenAI actual single-candidate generation
- preview Markdown source artifact scan

## 남은 확인

- 전체 CLI 3후보 생성은 v5에서 15분 제한을 넘겨 중단했다.
- 저장소 상태는 v4 note store 그대로 유지됐고, 부분 저장은 발생하지 않았다.
- 22번 품질 재검증에서 긴 실행 시간과 3후보 전체 생성 안정성을 다시 확인한다.
- 골든 노트 승인은 사용자가 직접 preview를 읽고 결정한다.

# 18. 강의노트 구조 PRD 반영

## 상태

완료

## 목표

강의노트 생성 구조를 전용 강의노트 PRD에 맞춘다. 1분짜리 짧은 강의부터 2-3시간짜리 긴 강의까지 커버할 수 있도록, 강의 시간이 아니라 원천 텍스트 양과 주제 구조를 기준으로 노트 분량과 계층을 조절한다.

## 범위

- 강의노트 PRD를 노트 섹션, 깊이, 검수 기준의 기준 문서로 사용한다.
- PRD의 표준 구조를 생성 계약에 명시적으로 반영한다.
- 고정된 섹션/항목 개수 대신 `estimated_tokens`, segment 수, 주제 전환 수를 함께 보는 콘텐츠 프로필을 적용한다.
- 현재 승인 흐름을 유지한다. 생성된 후보는 사람이 승인하기 전까지 `review_required` 상태로 남긴다.
- 기존 OpenAI 노트 후보는 PRD 반영 이전에 생성된 결과물이므로 골든 노트로 간주하지 않는다.
- 이 계획에서는 카드/퀴즈 생성 로직을 변경하지 않는다.

## PRD 필수 구조

생성되는 Markdown 강의노트는 기본적으로 아래 순서를 따른다.

1. `# 강의 제목`
2. `## 강의 한 줄 요약`
3. `## 학습 목표`
4. `## 1. 핵심 주제`
5. 필요한 경우 `### 하위 개념`
6. 필요한 경우 흐름도
7. 필요한 경우 표
8. 필요한 경우 코드 예시
9. `## 실무 관점에서 기억할 것`
10. `## 핵심 용어 정리`
11. `## 복습 질문`
12. `## 최종 정리`

원천 텍스트에 근거가 부족한 항목은 내용을 지어내지 않는다. 대신 후보 metadata 또는 validation 결과에 부족 사유를 남긴다.

## 콘텐츠 프로필 정책

의존성 없이 아래 방식으로 텍스트 양을 추정한다.

- `estimated_tokens = max(word_count, round(non_space_character_count / 3))`

텍스트 양뿐 아니라 아래 신호를 함께 사용한다.

- `segment_count`: 자막/STT segment 수
- `topic_shift_count`: 제목, OCR, 자막 흐름에서 감지한 주제 전환 수
- `has_code_or_commands`: 코드/명령어가 실제로 등장하는지 여부
- `has_process_flow`: 단계, 순서, 처리 흐름이 실제로 등장하는지 여부
- `has_comparison`: 비교/구성 요소 설명이 실제로 등장하는지 여부

## 길이별 생성 전략

### compact note

짧은 강의 또는 원천 텍스트가 부족한 경우 사용한다.

- 대상 예: `estimated_tokens < 700`
- PRD 구조는 유지하되, 항목 수를 억지로 채우지 않는다.
- 학습 목표, 핵심 용어, 복습 질문은 원문 근거가 있는 최소 세트로 생성한다.
- PRD 최소 개수를 채우기 어렵다면 `source_insufficient_for_full_note=true`를 남긴다.
- 없는 개념, 예시, 코드, 흐름도, 표를 지어내지 않는다.

### standard note

대부분의 일반 강의에 사용한다.

- 대상 예: `700 <= estimated_tokens <= 4500`
- PRD의 기본 기준을 최대한 충족한다.
- 학습 목표 4-7개, 핵심 용어 최소 8개, 복습 질문 8-15개를 우선 목표로 한다.
- 핵심 주제 섹션은 강의 흐름에 맞춰 번호를 붙인다.
- 코드, 흐름, 비교가 등장하면 코드 블록, 흐름도, 표를 사용한다.

### expanded note

긴 강의지만 하나의 문서로 무리 없이 정리 가능한 경우 사용한다.

- 대상 예: `4500 < estimated_tokens <= 12000`
- 항목 개수를 무한히 늘리지 않고, 핵심 주제 섹션과 하위 섹션으로 계층화한다.
- 세부 내용은 주제별로 묶고, 최종 정리에서 전체 흐름을 다시 압축한다.
- 출처 segment/timestamp 연결을 섹션 단위로 유지한다.

### chaptered note

2-3시간 강의처럼 매우 긴 입력에 사용한다.

- 대상 예: `estimated_tokens > 12000` 또는 주제 전환이 많은 강의
- 하나의 거대한 노트를 바로 만들지 않는다.
- 먼저 챕터/주제 단위 부분 노트를 생성한다.
- 마지막에 전체 통합 노트 또는 master summary를 생성한다.
- 각 챕터 노트는 PRD 구조를 축약 적용하고, master summary는 전체 흐름과 핵심 연결을 정리한다.
- 챕터 분리 기준과 각 챕터의 segment/timestamp 범위를 metadata에 남긴다.

## PRD 최소 기준과 예외 처리

PRD의 최소 항목 수는 기본 목표이지만, 원천 텍스트가 부족한 경우에는 환각 방지가 우선이다.

- 학습 목표 4개 미만이면 `insufficient_learning_goals`를 남긴다.
- 핵심 용어 8개 미만이면 `insufficient_key_terms`를 남긴다.
- 복습 질문 8개 미만이면 `insufficient_review_questions`를 남긴다.
- 코드/흐름도/표가 필요한데 생성되지 않으면 `missing_expected_structure`를 남긴다.
- 원문 근거 없이 항목 수를 채우는 후보는 승인 대상에서 제외한다.

## 생성 경로

- PRD 품질 기준은 OpenAI 노트 생성 경로를 우선 대상으로 맞춘다.
- 로컬 노트 생성은 구조 확인, offline preview, fallback 성격으로 유지한다.
- 두 경로 모두 동일한 content profile metadata와 validation 결과를 저장한다.
- 모델명, prompt version, content profile, stale 여부를 후보 metadata에 기록한다.

## 작업 단계

1. 강의노트 구조 PRD를 읽고 필수 Markdown 구조를 노트 생성 계약에 반영한다.
2. `estimated_tokens`, segment 수, 주제 전환 수를 계산하는 콘텐츠 프로필 헬퍼를 추가한다.
3. compact, standard, expanded, chaptered note 전략을 선택하는 분기 로직을 추가한다.
4. OpenAI 노트 프롬프트를 PRD 구조와 길이별 생성 전략에 맞게 갱신한다.
5. 로컬 노트 생성은 동일한 구조 metadata를 남기는 fallback으로 정리한다.
6. OpenAI 응답 파서/검증기에 PRD 체크리스트와 부족 사유 flag를 추가한다.
7. 실제 강의 샘플의 노트 후보를 다시 생성하고, 이전 후보는 stale 또는 non-golden으로 표시한다.
8. tiny, short, medium, long, very long 입력 사례 테스트를 추가한다.
9. 25분 실제 강의 샘플의 이전 후보와 PRD 반영 후보를 비교 기록한다.

## 검증

- `python -m unittest discover -s tests`
- `python -m compileall lecturedigest tests`
- `git diff --check`
- `powershell -ExecutionPolicy Bypass -File scripts/validate-harness.ps1 -Mode Project`
- `powershell -ExecutionPolicy Bypass -File scripts/validate-harness.ps1 -CodeHealth -Mode Project`
- 실제 강의 샘플로 OpenAI 노트 후보를 다시 생성한다.
- 생성 후보가 PRD 체크리스트를 얼마나 충족하는지 기록한다.
- 섹션별 출처 segment/timestamp 연결이 유지되는지 확인한다.
- 핵심 개념 누락, 환각, 과도한 축약 여부를 사람이 수동 검토한다.

## 완료 기준

- PRD 표준 구조가 노트 생성 계약과 검증기에 반영되어 있다.
- 짧은 강의는 환각 없이 compact note로 생성된다.
- 보통 강의는 PRD 기본 기준을 충족하는 standard note로 생성된다.
- 긴 강의는 하위 섹션 또는 챕터 기반으로 계층화된다.
- 원천 근거가 부족한 항목은 지어내지 않고 명시적인 flag로 남는다.
- 실제 강의 샘플에서 기존 후보보다 노트 깊이와 구조가 개선되었음을 확인한다.

## 열린 질문

- 골든 노트 샘플의 최종 승인 담당자가 필요하다.
- `topic_shift_count`를 OCR 기반으로 강하게 볼지, 자막/교정본 기반으로 우선 볼지 결정이 필요하다.
- `chaptered note`의 실제 분리 기준은 22번 품질 재검증에서 조정할 수 있다.

## 결과

구현 완료.

- PRD 표준 Markdown 구조를 로컬/OpenAI 노트 생성 계약에 반영했다.
- `estimated_tokens`, segment 수, topic shift, 코드/흐름/비교 신호를 계산하는 content profile을 추가했다.
- compact, standard, expanded, chaptered note 전략을 metadata와 prompt contract에 반영했다.
- 원천 텍스트가 짧은 경우 PRD 최소 개수를 억지로 채우지 않고 부족 flag를 남기도록 검증기를 추가했다.
- OpenAI 응답 파서가 PRD 섹션, numbered topic, 출처 segment/timestamp를 검증하도록 갱신했다.
- 실제 강의 샘플로 `gpt-4o` OpenAI 노트 후보 3개를 재생성했다.
- 실제 후보는 이전 4섹션 MVP보다 PRD 구조가 풍부해졌지만, 세 후보 모두 validation flagged 상태이므로 골든 노트로 승인하지 않는다.
- 검증 보고서: `docs/validation/note-prd-alignment-2026-04-30.md`
- 남은 품질 재검증과 골든 승인 작업은 `22-real-lecture-quality-revalidation.md`에서 이어서 수행한다.

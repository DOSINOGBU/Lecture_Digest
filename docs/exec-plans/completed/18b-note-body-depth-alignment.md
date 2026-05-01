# 18b. 노트 본문 밀도 보강

## 상태

완료

## 목표

18번과 18a를 통해 PRD 구조와 repair 흐름은 안정화됐지만, 실제 생성 노트는 아직 학습 교재형 본문에 비해 지나치게 요약 중심이다. 사용자가 제공한 기준 노트 수준처럼, 핵심 주제마다 충분한 설명, 예시, 흐름, 실무 연결이 포함된 본문 밀도 기준을 추가한다.

## 기준 샘플

사용자가 제공한 `02. 결국 브라우저가 이해하는 것 - 강의노트.md`를 목표 품질 기준으로 삼는다.

관찰한 차이:

- 기준 노트: 약 7,858자, 343줄, H2 17개, H3 5개, 코드블록 4개
- 현재 OpenAI 후보: 약 3,677자, 66줄, H2 10개, H3 0개, 코드블록 0개

따라서 현재 후보는 validation은 통과했지만, 학습노트라기보다 출처 달린 요약본에 가깝다.

## 범위

- OpenAI 노트 생성 prompt에 본문 밀도 요구사항을 추가한다.
- PRD validator에 본문 부실 감지 규칙을 추가한다.
- repair pass가 개수 보강뿐 아니라 topic 본문 확장도 수행하도록 조정한다.
- 실제 강의 샘플에서 기준 노트와 생성 노트를 정량 비교하는 validation report를 추가한다.
- 카드, 퀴즈, UI 구현은 변경하지 않는다.

## 본문 품질 정책

### 공통 원칙

- 노트는 짧은 요약이 아니라 학습 교재형 문서여야 한다.
- 핵심 주제는 단일 문단으로 끝내지 않고, 개념 설명, 왜 중요한가, 강의 흐름 속 위치, 예시나 주의점을 포함한다.
- 강의 근거가 있는 경우 `###` 하위 섹션, 표, 흐름도, 코드블록을 적극 사용한다.
- 짧은 강의는 텍스트 양 기준으로 compact하게 처리하되, 긴 강의를 임의로 요약본으로 축소하지 않는다.

### adaptive 기준

강의 시간이 아니라 정제 텍스트의 `estimated_tokens`와 주제 밀도를 기준으로 본문량을 조정한다.

- `compact`: 원문이 짧으면 구조는 유지하되 억지로 항목을 늘리지 않는다.
- `standard`: 전체 노트 목표 7,000~10,000자, 핵심 주제 5~10개, topic당 300~600자 우선.
- `expanded`: 핵심 주제와 하위 섹션을 더 늘리고, 장문 topic은 `###`로 분해한다.
- `chaptered`: 챕터 단위 부분 노트와 master summary로 분리한다.

## 추가 validation 규칙

다음 항목을 자동 검증에 추가한다.

- `body_too_short`: 전체 Markdown이 content profile 대비 너무 짧음
- `topic_body_too_shallow`: 핵심 topic 섹션 평균 본문 길이가 부족함
- `insufficient_subsections`: standard 이상인데 하위 섹션이 거의 없음
- `missing_explanatory_depth`: 개념 설명, 중요성, 사용 맥락이 부족함
- `coverage_too_sparse`: source chunk 대비 다루는 topic 범위가 너무 좁음

단, compact note에는 완화 기준을 적용한다.

## 작업 단계

1. 기준 노트의 구조와 분량을 validation 기준으로 문서화한다.
2. `note_prd` validator에 본문 밀도 관련 count와 rule을 추가한다.
3. OpenAI note prompt에 “짧게 요약 금지”와 topic별 본문 요구사항을 추가한다.
4. repair prompt에 `topic_body_too_shallow`, `body_too_short` 보강 지시를 추가한다.
5. 기준 노트와 생성 후보를 비교하는 report helper 또는 수동 validation 절차를 추가한다.
6. 실제 강의 `lec_3f51e7be057c`로 다시 생성/repair한다.
7. 최소 1개 후보가 구조 validation과 본문 밀도 validation을 모두 통과하는지 확인한다.
8. 사용자가 preview를 읽고 골든 노트 후보로 승인할 수 있도록 경로와 판단 기준을 보고한다.

## 완료 기준

- 기준 노트 수준을 반영한 본문 밀도 규칙이 validator에 들어간다.
- OpenAI prompt와 repair prompt가 교재형 본문 생성을 명확히 요구한다.
- 실제 강의 후보 중 최소 1개가 `review_required`이며 `body_too_short`, `topic_body_too_shallow`에 걸리지 않는다.
- preview Markdown이 기준 노트와 비슷한 학습 가능 분량과 구조를 가진다.
- 골든 노트 승인은 사용자가 직접 결정한다.

## 검증

- `python -m unittest discover -s tests`
- `python -m compileall lecturedigest tests`
- `git diff --check`
- `powershell -ExecutionPolicy Bypass -File scripts/validate-harness.ps1 -Mode Project`
- `powershell -ExecutionPolicy Bypass -File scripts/validate-harness.ps1 -CodeHealth -Mode Project`
- 실제 강의 OpenAI generation + repair
- 기준 노트와 생성 노트의 글자 수, H2/H3 수, topic 평균 본문 길이, 표/코드/흐름도 포함 여부 비교

## 열린 질문

- 문단마다 citation을 유지할지, 섹션/소주제 단위 citation으로 읽기 편하게 완화할지 결정이 필요하다.
- 기준 노트의 문체를 모든 강의에 고정할지, 강의 분야별로 tone/profile을 나눌지 후속 검토가 필요하다.

## 결과

구현 완료.

- 노트 본문 밀도 validator를 추가했다.
- `body_too_short`, `topic_body_too_shallow`, `insufficient_subsections`, `missing_explanatory_depth`, `coverage_too_sparse`를 validation 결과에 포함했다.
- OpenAI 노트 prompt를 `openai-markdown-note-prd-v3`로 올리고 교재형 본문, H3 하위 섹션, topic별 설명 깊이 요구사항을 추가했다.
- OpenAI 노트 기본 모델을 `gpt-4.1`로 올렸다.
- 긴 본문 생성용으로 `generate-notes --openai-timeout-seconds` 옵션을 추가했다.
- repair prompt가 body depth gap을 보고 부족한 글자 수와 topic 평균 길이를 보강하도록 조정했다.
- 실제 강의 `lec_3f51e7be057c`를 `gpt-4.1`로 재생성했고, 후보 3개 모두 `review_required` 상태가 됐다.
- preview 파일은 `.lecturedigest/note-previews/18b-gpt41/`에 생성했다. 이 경로는 저장소에 포함하지 않는다.
- validation report는 `docs/validation/note-body-depth-alignment-2026-04-30.md`에 기록했다.
- 골든 노트 승인은 아직 사용자가 직접 결정해야 한다.

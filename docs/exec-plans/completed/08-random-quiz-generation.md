# Plan: Random Quiz Generation

## Goal

승인된 학습 노트와 출처 매핑을 기반으로 사지선다형과 서술형 퀴즈를 생성하고, 사용자에게 랜덤 순서로 출제할 수 있는 CLI 기반 산출물을 만든다.

## Scope

- 퀴즈 입력은 승인된 Markdown 노트와 원본 segment mapping이다.
- 문제 유형은 사지선다형과 서술형을 지원한다.
- 출제 순서는 유형을 랜덤으로 섞어 나온다.
- 각 문항은 문제, 보기, 정답, 해설, 출처를 포함한다.
- 출처 없는 문항은 `flagged`로 남긴다.

## Out Of Scope

- Anki 카드 생성.
- 점수화 학습 통계.
- 모바일 복습 앱.
- 개념 그래프 기반 적응형 출제.

## Assumptions

- 퀴즈는 Anki 이후 후속 기능이다.
- 사지선다형은 정답 1개와 오답 보기 3개를 기본값으로 둔다.
- 서술형은 자동 채점보다 해설과 출처 제공을 우선한다.

## Steps

- [x] 퀴즈 입력 소스와 필수 출처 필드를 정의한다.
- [x] 사지선다형 문항 스키마를 정의한다.
- [x] 서술형 문항 스키마를 정의한다.
- [x] 랜덤 출제 정책과 재현 가능한 seed 처리를 정한다.
- [x] 문항 유효성 검수 기준을 만든다.

## Validation

- 객관식과 서술형이 섞여 출제된다.
- 모든 ready 문항은 출처 timestamp를 포함한다.
- 사지선다형은 보기 4개와 정답 1개를 포함한다.
- 서술형은 기준 답안과 해설을 포함한다.
- 출처 없는 문항은 `flagged`로 남는다.

## Risks

- 오답 보기가 부정확하면 잘못된 학습 흐름을 만들 수 있다.
- 서술형을 자동 채점까지 확장하면 평가 기준 설계가 필요하다.

## Result

Completed.

- Added approved-note-only quiz generation with mixed `multiple_choice` and `written` item types.
- Added source payloads with segment ids, timestamps, lecture/chapter metadata, and jump links.
- Added validation so multiple-choice items require four choices and exactly one correct answer.
- Added written quiz expected answers, rubrics, explanations, and source citations.
- Added `generate-quizzes` CLI with loading, empty, success, and error states.
- Added seed-based random ordering for reproducible quiz sequences.
- Items without source mappings are stored as `flagged`.
- Verification passed with `python -m unittest discover -s tests`, `python -m compileall lecturedigest tests`, CLI help, and harness validation.

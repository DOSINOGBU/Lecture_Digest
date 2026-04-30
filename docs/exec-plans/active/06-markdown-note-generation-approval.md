# Plan: Markdown Note Generation And Approval

## Goal

교정 완료 transcript, 정제 OCR, 요약 결과를 바탕으로 Markdown 학습 노트 후보 3개를 만들고, 사용자 승인 후 확정 노트로 저장합니다.

## Scope

- ScriptDigest 입력: lecture_id, lecture_title, clip/chapter metadata, category, instructor, start_ts/end_ts/text 세그먼트 배열.
- 선택 입력: 정제 OCR 텍스트, 도메인 용어집, tone(`formal`, `casual`, `keep_original`).
- 챕터 단위 권장 범위: 5~30분 또는 약 3,000~15,000 토큰.
- filler word와 즉시 반복 제거.
- 의미 단락 분할과 Markdown 생성.
- 노트 후보 3개 생성과 승인 상태 관리.
- Markdown 미리보기에서 형식이 잘 적용되도록 표준 섹션을 고정.
- 원본 segment id와 타임스탬프 매핑 보존.

## Required Markdown Format

```md
[1] 강의 요약 (3~5줄)
- 핵심만 압축

[2] 핵심 개념 (Key Concepts)
- 개념 1:
  정의:
  왜 중요한가:
  어디에 쓰나:

[3] 구조 / 흐름 (Flow)
- 강의 전체 논리 흐름
- 단계별 정리

[4] 실행 (Action)
- 내가 당장 할 것
- Task로 변환
```

## Out Of Scope

- STT/OCR 직접 수행.
- Anki/퀴즈 생성.
- 전체 교정 검수 UI.

## Assumptions

- 기본 tone은 `formal`입니다.
- OCR이 없으면 화면 메모 콜아웃을 생성하지 않습니다.
- 원문 OCR은 보관용으로 유지하고, 노트 본문에는 정제 OCR만 반영합니다.
- 원문 근거 없는 용어 정의는 생성하지 않고, LLM 부연이 필요하면 `(추론)`을 표시합니다.
- 승인 전 후보 노트는 확정 산출물로 저장하지 않습니다.

## Steps

- [ ] ScriptDigest 입력 스키마와 오류 메시지를 정의한다.
- [ ] 정제 단계별 중간 산출물 이름과 캐시 키를 정한다.
- [ ] filler 제거와 반복 정리 규칙을 정의한다.
- [ ] 문어체 rewrite prompt와 버전 관리 방식을 정한다.
- [ ] Markdown 표준 섹션과 frontmatter 필드를 정의한다.
- [ ] 후보 3개 생성, 승인, 기각, 재생성 상태를 정의한다.
- [ ] 원본 매핑 누락 시 `flagged` 처리 방식을 정한다.

## Validation

- 입력 세그먼트가 없으면 노트를 생성하지 않습니다.
- 노트 후보 3개가 생성되고 승인 전에는 확정 노트로 저장되지 않습니다.
- 승인된 후보만 카드/퀴즈 입력으로 사용됩니다.
- 노트 길이는 원본 대본의 40~70% 목표 범위에 들어오는지 확인합니다.
- 각 문단 또는 주요 문장은 원본 segment id와 타임스탬프를 유지합니다.
- 모델 또는 prompt 변경 시 노트는 stale로 표시되고 자동 재생성되지 않습니다.

## Risks

- 구어체를 과도하게 정제하면 강사의 강조와 뉘앙스가 사라질 수 있습니다.
- STT 오류가 정제 단계까지 전파되면 잘못된 학습 본문이 만들어질 수 있습니다.
- 후보 3개 생성은 LLM 비용과 검토 피로를 늘릴 수 있습니다.

## Result

진행 전입니다.

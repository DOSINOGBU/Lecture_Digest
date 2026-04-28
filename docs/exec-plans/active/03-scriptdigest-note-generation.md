# Plan: ScriptDigest Note Generation

## Goal

챕터 단위 대본 세그먼트를 정제, 구조화, 문어체 변환, 보강, 검증하여 원본 매핑이 보존된 Markdown 학습 노트를 생성합니다.

## Scope

- ScriptDigest 입력: lecture_id, lecture_title, chapter_title, category, instructor, start_ts/end_ts/text 세그먼트 배열.
- 선택 입력: 정제 OCR 텍스트, 도메인 용어집, tone(`formal`, `casual`, `keep_original`).
- 챕터 단위 권장 범위: 5~30분 또는 약 3,000~15,000 토큰.
- filler word와 즉시 반복 제거.
- 의미 단락 분할, H2/H3 제목 부여.
- Markdown frontmatter 생성.
- 원본 segment id와 타임스탬프 매핑 보존.

## Out Of Scope

- STT/OCR 직접 수행.
- Anki/퀴즈 생성.
- 전체 교정 검수 UI.

## Assumptions

- 기본 tone은 `formal`입니다.
- OCR이 없으면 화면 메모 콜아웃을 생성하지 않습니다.
- 원문 OCR은 보관용으로 유지하고, 노트 본문에는 정제 OCR만 반영합니다.
- 원문 근거 없는 용어 정의는 생성하지 않고, LLM 부연이 필요하면 `(추론)`을 표시합니다.

## Steps

- [ ] ScriptDigest 입력 스키마와 오류 메시지를 정의한다.
- [ ] 정제 단계별 중간 산출물 이름과 캐시 키를 정한다.
- [ ] filler 제거와 반복 정리 규칙을 정의한다.
- [ ] 문어체 rewrite prompt와 버전 관리 방식을 정한다.
- [ ] Markdown 표준 섹션과 frontmatter 필드를 정의한다.
- [ ] 원본 매핑 누락 시 `flagged` 처리 방식을 정한다.

## Validation

- 입력 세그먼트가 없으면 노트를 생성하지 않습니다.
- 노트 길이는 원본 대본의 40~70% 목표 범위에 들어오는지 확인합니다.
- 각 문단 또는 주요 문장은 원본 segment id와 타임스탬프를 유지합니다.
- 원문 근거 없는 용어집 fallback이 발생하지 않아야 합니다.
- 모델 또는 prompt 변경 시 노트는 stale로 표시되고 자동 재생성되지 않습니다.

## Risks

- 구어체를 과도하게 정제하면 강사의 강조와 뉘앙스가 사라질 수 있습니다.
- STT 오류가 정제 단계까지 전파되면 잘못된 학습 본문이 만들어질 수 있습니다.

## Result

진행 전입니다.

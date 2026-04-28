# Plan: Correction, Validation, And Review

## Goal

STT 의심 세그먼트와 맥락 기반 오탈자 후보를 안전하게 교정하고, 자동 적용하지 못한 항목을 검수 가능한 상태로 남깁니다.

## Scope

- STT 무결성 검증: 미완성 문장, 고립 조사, 숫자 단편, 음운 혼동 후보, 세그먼트 길이 이상치.
- 단계적 보정: `gpt-4o-mini` 1차, `gpt-4o` 2차 후보.
- 맥락 교정 Pass A/B/C 후보 탐지와 confidence 정책.
- confidence 0.9 이상만 자동 교정.
- 0.7~0.9 후보 정책은 미정으로 남기되 검수 대기 기본값을 우선.
- validation log와 correction log 저장.

## Out Of Scope

- 전체 프론트엔드 검수 UI 완성.
- Kiwi 형태소 분석 고도화 전체 구현.
- 카드/퀴즈 품질 검수.

## Assumptions

- 낮은 confidence 후보는 원문 유지 또는 검수 대기이며 자동 적용하지 않습니다.
- 고유명사, 숫자, 생소어 보호 규칙을 교정 전에 적용합니다.

## Steps

- [ ] STT 의심 패턴과 severity를 정의한다.
- [ ] correction_log 필드와 상태 전이를 정의한다.
- [ ] Pass A/B/C 입출력과 confidence 기준을 정의한다.
- [ ] 자동 교정 상한과 보호 규칙을 정한다.
- [ ] 출력 검증 게이트 규칙을 구현 계획으로 나눈다.
- [ ] 검수 UI에 필요한 API/데이터를 정리한다.

## Validation

- 자동 교정 precision 95% 이상, false positive 1% 이하를 목표로 표본 검수합니다.
- confidence 0.9 미만 후보가 자동 적용되지 않는지 확인합니다.
- 검증 실패 항목은 자동 수정 가능 여부와 함께 기록됩니다.

## Risks

- false positive 교정은 학습 내용을 왜곡할 수 있습니다.
- 너무 보수적인 교정은 노트 품질 개선 효과를 낮출 수 있습니다.

## Open Questions

- confidence 0.7~0.9 후보를 본문에 선적용할지, 검수 전에는 원문 유지할지?
- `speaker_mode=dialogue`를 언제 자동 활성화할지?

## Result

진행 전입니다.

# Plan: LLM Transcript Correction

## Goal

자막 파일 기반 transcript와 OpenAI STT 기반 transcript 모두에 동일한 LLM 교정 파이프라인을 적용하고, 고신뢰 교정은 자동 적용하며 낮은 confidence 후보는 검토 대기로 남긴다.

## Scope

- 교정 대상은 완성 전 transcript segment text이다.
- 기본 LLM은 사용자 결정에 따라 `gpt-4o`로 둔다.
- prompt_version을 명시하고 model/prompt 변경 시 기존 교정 산출물은 stale로 표시한다.
- confidence 0.9 이상은 자동 적용, 0.7 이상 0.9 미만은 `review_required`, 0.7 미만은 적용하지 않는다.
- 원문, 수정문, confidence, reason, applied, status, provider metadata를 correction log에 저장한다.
- 자동 교정은 강사의 의도와 코드/고유명사를 과도하게 바꾸지 않는 보수적 정책을 따른다.

## Steps

- [ ] 교정 요청 payload와 prompt contract를 정의한다.
- [ ] correction CLI에 OpenAI 호출 옵션과 `--dry-run`을 추가한다.
- [ ] segment 단위 또는 작은 batch 단위 호출을 구현한다.
- [ ] LLM 응답 schema를 검증하고 malformed response를 명확히 실패 처리한다.
- [ ] confidence threshold별 적용/검토/보류 정책을 구현한다.
- [ ] protected terms, code-like text, URL/path-like text는 보수적으로 보호한다.
- [ ] stale 교정 결과가 자동 재생성되지 않도록 status를 유지한다.
- [ ] 중간 confidence 후보를 이후 Streamlit review UI에서 사용할 수 있는 형태로 남긴다.

## Validation

- 자막 기반 transcript와 STT 기반 transcript가 같은 교정 경로를 타는지 테스트한다.
- 0.9 이상, 0.7~0.9, 0.7 미만 confidence 분기를 테스트한다.
- model/prompt 변경 시 stale 표시와 자동 재생성 금지를 테스트한다.
- malformed response, API 실패, 빈 segment, protected term 보존을 테스트한다.
- `python -m unittest discover -s tests`
- `python -m compileall lecturedigest tests`
- `git diff --check`
- `powershell -ExecutionPolicy Bypass -File scripts/validate-harness.ps1 -Mode Project`
- `powershell -ExecutionPolicy Bypass -File scripts/validate-harness.ps1 -CodeHealth -Mode Project`

## Result

작성 전.

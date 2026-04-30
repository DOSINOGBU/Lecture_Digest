# Testing

변경 후 무엇을 실행해야 하는지 AI가 추측하지 않도록 기록합니다. 현재 MVP는 표준 라이브러리 기반으로 구현되어 별도의 설치 과정 없이 Python 환경만으로 실행 가능합니다.

## Commands

| 목적 | 명령 | 비고 |
|---|---|---|
| 설치 | `python --version` | 별도 설치 과정 없음, Python 환경 확인 |
| 개발 서버 | `python -m lecturedigest --help` | UI 도입 전 CLI 진입점 확인 |
| 단위 테스트 | `python -m unittest discover -s tests` | 관련 테스트 우선 실행 |
| 린트 | `python -m compileall lecturedigest tests` | 린터 미도입, 문법/임포트 오류 대체 확인 |
| 타입체크 | `python -m compileall lecturedigest tests` | 타입체커 미도입, 기본 정적 오류 대체 확인 |
| 빌드 | `python -m compileall lecturedigest` | 패키징 전 단계, 컴파일 가능 여부 확인 |
| 하네스 템플릿 검증 | `powershell -ExecutionPolicy Bypass -File scripts/validate-harness.ps1 -Mode Template` | 템플릿 원본 검증, TODO 명령은 warning |
| 하네스 프로젝트 검증 | `powershell -ExecutionPolicy Bypass -File scripts/validate-harness.ps1 -Mode Project` | 실제 프로젝트 도입 후 TODO를 실패로 처리 |
| 하네스 호환 엄격 검증 | `powershell -ExecutionPolicy Bypass -File scripts/validate-harness.ps1 -Strict` | 기존 명령 호환용, Project mode처럼 동작 |
| 하네스 유지보수 검증 | `powershell -ExecutionPolicy Bypass -File scripts/validate-harness.ps1 -Maintenance` | 드리프트 감지, 기본은 warning |
| 하네스 프로젝트 유지보수 검증 | `powershell -ExecutionPolicy Bypass -File scripts/validate-harness.ps1 -Maintenance -Mode Project` | 유지보수 finding을 실패로 처리 |
| 코드 건강도 검증 | `powershell -ExecutionPolicy Bypass -File scripts/validate-harness.ps1 -CodeHealth` | 큰 코드 파일 감지, 기본은 warning |
| 프로젝트 코드 건강도 검증 | `powershell -ExecutionPolicy Bypass -File scripts/validate-harness.ps1 -CodeHealth -Mode Project` | 1200줄 이상 코드 파일을 실패로 처리 |
| 테스트 명령 감지 | `powershell -ExecutionPolicy Bypass -File scripts/init-testing-commands.ps1` | 감지 결과만 출력, 파일 변경 없음 |
| 테스트 명령 적용 | `powershell -ExecutionPolicy Bypass -File scripts/init-testing-commands.ps1 -Apply` | 확인 후 `docs/TESTING.md` 명령 표 갱신 |
| validator 자기 테스트 | `powershell -ExecutionPolicy Bypass -File scripts/tests/run-validator-fixtures.ps1` | fixture 기반 하네스 검증 |
| 버전 관리 추천 | `powershell -ExecutionPolicy Bypass -File scripts/recommend-version-control.ps1 -VerificationStatus Passed` | 커밋, 푸시, PR 타이밍 조언만 출력 |

## Verification Policy

- 기능 변경은 관련 테스트 또는 수동 시나리오를 반드시 기록합니다.
- 버그 수정은 재현 방법과 수정 후 확인 방법을 함께 기록합니다.
- 테스트를 실행하지 못한 경우 이유와 대체 검증을 남깁니다.
- MVP 초기 단계는 개발 생산성을 우선해 최소 검증 체계로 운영합니다.
- UI는 아직 도입하지 않았으므로 Streamlit이나 웹 서버 대신 CLI 기반 진입점을 확인합니다.
- lint, typecheck, build 파이프라인은 UI와 서비스 구조가 확정된 뒤 정식 도구로 교체합니다.
- 템플릿 원본은 `-Mode Template`을 사용하고, 실제 프로젝트에 적용한 뒤에는 `-Mode Project`를 통과시킵니다.
- `-Strict`는 기존 사용자를 위한 호환 옵션이며 `-Mode Project`와 같은 수준으로 처리합니다.
- `init-testing-commands.ps1`는 자동 적용 전에 반드시 dry-run 출력으로 명령을 확인합니다.

## Product Test Strategy

| 영역 | 검증 목표 | 예시 |
|---|---|---|
| Ingestion | 파일/자막/메타데이터 검증 | 지원/미지원 확장자, 자막 있음/없음 |
| STT/Subtitles | 타임스탬프 보존과 fallback | SRT/VTT 파싱, STT 전환, 오디오 없음 |
| Chunking/Embedding | 청크 경계와 payload 보존 | 60~90초 청크, 15초 오버랩, segment id |
| RAG | 출처 정확도와 근거 부족 처리 | 수동 표본 50개, 빈 검색, 낮은 근거 |
| ScriptDigest | 원본 매핑과 노트 품질 | STT 마커, 용어집 fallback 금지, frontmatter |
| Correction | confidence 정책 | 0.9 이상 자동 적용, 0.7~0.9 검수 대기 |
| Reliability | 실패 단계 재개 | STT/OCR/LLM 실패 후 재시도 |
| Cost | 캐시와 호출 제한 | 같은 입력 반복 처리 시 외부 호출 감소 |
| Regeneration | stale 산출물 처리 | 모델/prompt 변경 후 자동 재생성 없음, 수동 재생성 버튼 |

## Manual Scenario Template

```text
Scenario:
1. 
2. 
3. 

Expected:

Observed:
```

## MVP Manual Scenarios

1. 자막이 있는 강의를 등록하면 STT를 건너뛰고 세그먼트와 요약이 생성된다.
2. 자막이 없는 강의를 등록하면 STT 단계로 전환되고 예상 처리 시간이 표시된다.
3. RAG 질문에 대해 답변, 출처 타임스탬프, 원본 점프 링크가 함께 표시된다.
4. 근거가 부족한 질문은 답변을 꾸며내지 않고 검색 범위 조정 안내를 표시한다.
5. 챕터 학습 노트 생성 시 Markdown frontmatter, 원본 매핑, 검증 결과가 생성된다.
6. 낮은 confidence 교정 후보는 자동 적용되지 않고 검수 대상으로 남는다.
7. 모델 또는 prompt 버전이 바뀐 산출물은 stale로 표시되고 자동 재생성되지 않는다.

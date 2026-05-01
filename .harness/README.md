# Harness

이 폴더는 AI 에이전트를 운영하기 위한 반복 가능한 작업 절차를 담습니다.

## Contents

| 경로 | 목적 |
|---|---|
| `checklists/` | 작업 유형별 완료 기준 |
| `prompts/` | 반복 사용 가능한 프롬프트 템플릿 |
| `config.json` | 하네스 검증 기준과 제외 경로 |

## Checklists

| 파일 | 사용 시점 |
|---|---|
| `feature-change.md` | 기능 추가·변경 |
| `bug-fix.md` | 버그 수정 |
| `refactor.md` | 동작 변경 없는 구조 개선 |
| `release.md` | 릴리스 전 점검 |
| `dependency-add.md` | 새 의존성 도입 |
| `migration.md` | 데이터·스키마 마이그레이션 |
| `incident.md` | 장애 대응과 사후 기록 |
| `doc-update.md` | 문서 갱신 |
| `commit.md` | 커밋 전 점검 |
| `pull-request.md` | PR 생성·머지 전 점검 |
| `maintenance.md` | 드리프트 정리 전 점검 |

## Prompts

| 파일 | 사용 시점 |
|---|---|
| `plan-task.md` | 구현 전에 계획부터 받고 싶을 때 |
| `implement-task.md` | 합의된 계획으로 구현 |
| `review-change.md` | 변경 자체 리뷰 |
| `fix-failing-check.md` | 검증 실패 분석·수정 |
| `debug-issue.md` | 증상에서 원인까지 단계 분석 |
| `write-tests.md` | 신뢰할 만한 테스트 작성 |
| `update-docs.md` | 변경에 맞춰 문서 갱신 |
| `explain-code.md` | 모르는 코드 빠르게 파악 |
| `commit-change.md` | 변경 검토 후 커밋 |
| `prepare-pr.md` | PR 제목과 본문 초안 작성 |
| `cleanup-drift.md` | 유지보수 감지 결과 정리 |

## Validation

`scripts/validate-harness.ps1`는 문서 인덱스와 체크리스트/프롬프트 연결이 실제 파일과 맞는지 확인합니다.
템플릿 원본에서는 `-Mode Template`을 사용하고, 실제 프로젝트 도입 후에는 `-Mode Project`로 `docs/TESTING.md`의 TODO 명령까지 실패로 처리합니다.
기존 `-Strict` 옵션은 호환용이며 `-Mode Project`와 같은 수준으로 동작합니다.
검증 기준은 `.harness/config.json`에서 조정합니다.
`-Maintenance`를 함께 사용하면 오래된 계획, 등록 누락, generated 문서 placeholder, 과도한 TODO를 warning으로 보고합니다.

## Version Control Recommendation

작업 완료 보고 전에는 `scripts/recommend-version-control.ps1`로 Commit/Push/PR 타이밍을 확인합니다.
이 스크립트는 Git 상태와 diff check를 읽기만 하며 커밋이나 푸시를 실행하지 않습니다.
검증 결과에 맞춰 `-VerificationStatus Passed`, `Partial`, `Failed`, `NotRun` 중 하나를 전달하고, 자동화 연동이 필요하면 `-Json`을 사용합니다.

## Principle

프롬프트는 일회성 지시입니다.
하네스는 반복 가능한 작업 시스템입니다.
같은 실수가 두 번 나오면 체크리스트로, 세 번 나오면 자동화로 옮깁니다.

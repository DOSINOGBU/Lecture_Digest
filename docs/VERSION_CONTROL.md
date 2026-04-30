# Version Control

커밋은 나중에 원인을 추적하고 되돌릴 수 있는 작업 단위입니다.
작은 커밋보다 중요한 것은 하나의 목적과 검증 가능한 상태입니다.

## Commit Principles

- 한 커밋은 하나의 목적만 가집니다.
- 기능 추가, 버그 수정, 리팩터링, 문서 수정, 설정 변경을 섞지 않습니다.
- 되돌리기 쉬운 최소 단위로 커밋합니다.
- 실행 불가능한 상태에서는 커밋하지 않습니다.
- 자동 포맷 변경과 기능 수정은 별도 커밋으로 분리합니다.

## Before Commit

| 확인 | 기준 |
|---|---|
| 실행 가능 상태 | 앱, 빌드, 테스트 중 작업에 맞는 검증을 통과 |
| 타입 검사 | 타입 시스템이 있으면 타입 에러 없음 |
| 린트 | 린트가 있으면 통과, 자동 수정은 기능 변경과 분리 |
| 회귀 확인 | 기존 핵심 흐름이 깨지지 않음 |
| 디버그 코드 | 임시 로그, 테스트 코드, 주석 제거 |
| 민감정보 | `.env`, 토큰, API 키, 계정 정보가 포함되지 않음 |

검증을 실행할 수 없으면 커밋 메시지로 숨기지 말고 완료 보고에 이유와 대체 확인 방법을 남깁니다.

## Automated Recommendation

작업 완료 보고 전에는 아래 명령으로 커밋, 푸시, PR 타이밍을 판정합니다. 이 명령은 Git 상태를 읽기만 하며 `git add`, `git commit`, `git push`를 실행하지 않습니다.

```powershell
powershell -ExecutionPolicy Bypass -File scripts/recommend-version-control.ps1 -VerificationStatus Passed
```

`-VerificationStatus`는 `Passed`, `Partial`, `Failed`, `NotRun` 중 하나로 기록합니다. 구조화된 후속 자동화가 필요하면 `-Json`을 함께 사용합니다.

| 판단 | 추천 조건 | 보류 또는 금지 조건 |
|---|---|---|
| Commit | 변경이 있고 검증이 통과 또는 부분 통과했으며 diff check와 민감 파일 검사를 통과 | 검증 실패/미실행, 충돌, 민감 파일 의심, diff check 실패, 목적 분리 의심 |
| Push | 작업 트리가 clean이고, topic branch가 upstream보다 ahead이며, 검증이 통과 | uncommitted change, behind 상태, 검증 미완료, upstream 없음 |
| PR | topic branch가 clean/pushed/verified 상태이고 `origin/main`과 차이가 있음 | `main` 브랜치, dirty tree, push 전 local commit, 검증 미완료 |

`main` 직접 push는 기본 보류합니다. 필요한 경우 topic branch로 분리하거나 PR 흐름을 사용합니다.

## Commit Message Format

```text
type(scope): summary
```

예시:

```text
feat(chat): add button-based goal suggestion flow
fix(dnd): prevent drop sync error
refactor(project): split logic into utils
docs(prd): update recurring automation spec
style(ui): adjust card spacing
test(task): add schedule parser test
chore(repo): update gitignore
```

## Types

| type | 의미 |
|---|---|
| `feat` | 기능 추가 |
| `fix` | 버그 수정 |
| `refactor` | 기능 변화 없는 구조 개선 |
| `docs` | 문서 수정 |
| `style` | UI 또는 스타일 수정 |
| `test` | 테스트 추가 또는 수정 |
| `chore` | 설정, 의존성, 저장소 관리 |
| `perf` | 성능 개선 |

## Message Rules

- 첫 줄은 짧고 명확하게 씁니다.
- `update`, `fix stuff`처럼 범위와 목적을 알 수 없는 표현은 쓰지 않습니다.
- 무엇을 바꿨는지와 왜 하나의 커밋인지 드러나게 씁니다.
- 한 커밋에 여러 의미가 보이면 커밋을 나눕니다.

## Split Criteria

좋은 커밋 단위:

- 드래그 버그 수정
- 목표 카드 UI 수정
- 반복 로직 추가
- 테스트 명령 문서화

나쁜 커밋 단위:

- UI, DB, 상태관리, 문구 수정을 한 번에 포함
- 자동 포맷과 기능 변경을 한 번에 포함
- 미완성 기능과 관련 없는 정리를 함께 포함

# DeskMate 첫 세팅 — 웹 UI(설정 대시보드)로

Chrome 북마크를 마크다운 저장소(옵시디언 볼트)로 동기화하고 위클리 인사이트 대화를 시작하기까지,
터미널 없이 설정 웹 UI의 버튼만으로 끝내는 절차입니다. (설계: [`oss_plan/2026-11-06-weekly-insight-design.md`](../oss_plan/2026-11-06-weekly-insight-design.md), 구현 계획: [`oss_plan/2026-11-07-deskmate-setup-dashboard-plan.md`](../oss_plan/2026-11-07-deskmate-setup-dashboard-plan.md))

> **신뢰 경계:** 설정 UI는 `0.0.0.0:7860`에 바인딩되어 같은 네트워크(LAN)의 누구나 열 수 있고,
> 이 화면의 버튼은 `.env`에 씁니다(기존 Connection 설정과 같은 경계). 집 Wi-Fi 밖(공용 네트워크)에서는
> 7860 포트를 열지 마세요. 인증은 upstream 영역이라 추가하지 않았습니다.

## 실제 Chrome 북마크로 시작하기

1. `.env`에 `CONVERSATION_BACKEND`·API 키만 넣고 `reachy-mini-conversation-app --ui` 실행 →
   브라우저에서 `http://127.0.0.1:7860/#/settings` 열기.
2. Settings 화면 아래쪽 **DeskMate** 섹션의 상태 카드가 "설정 안 됨 (`DESKMATE_BOOKMARK_REPO` 없음)"을 보여 줍니다.
3. **프로필 탐색** → 표에 프로필 폴더명(`Default`, `Profile 1`), Chrome 표시 이름, 북마크 파일별 개수
   (`Bookmarks: 120`, `AccountBookmarks: 244`), 마지막 사용 프로필 표시가 뜹니다. 북마크 파일이 없는 프로필은
   회색으로 "북마크 파일 없음". Chrome 폴더를 못 찾으면 "Chrome User Data 경로 직접 지정" 입력란이 열립니다
   (`chrome://version`의 "프로필 경로"에서 마지막 폴더를 뺀 상위 폴더).
4. 표의 체크박스로 읽을 프로필을 고릅니다(기본: 마지막 사용 프로필 1개). 다른 사람·회사 프로필은 고르지 않습니다.
5. **북마크 저장소 폴더** 입력란에 마크다운이 쌓일 폴더를 적습니다. 기본 제안은 `~/Documents/bookmarks`
   (서버가 홈 디렉터리로 풀어 보낸 절대 경로라 Windows에서도 맞습니다). 입력하는 동안 아래 한 줄에
   "존재함/없음 · 쓰기 가능 · 북마크 md N개 · 인사이트 노트 N개"가 갱신됩니다.
   **폴더 만들기·적용** → 없으면 하위 폴더까지 만들고 `DESKMATE_BOOKMARK_REPO`를 `.env`에 씁니다.
   상대 경로, Chrome User Data 안쪽, 홈 폴더 자체, 드라이브 루트, 쓰기 불가 폴더는 거부되고 아무것도 만들지 않습니다.
6. **.env에 적용** → 체크한 프로필이 `DESKMATE_CHROME_PROFILES`로, Chrome 경로를 직접 적었다면
   `DESKMATE_CHROME_USER_DATA_DIR`도 함께 `.env`와 실행 중 프로세스에 반영됩니다(5번을 건너뛰고 저장소 경로까지
   한 번에 적용해도 같은 검증을 거칩니다). 상태 카드가 "설정됨"으로 바뀌고 재시작은 필요 없습니다.
7. **동기화 실행** → 버튼이 잠기고 스피너가 돌다가 프로필별 created/updated/archived/excluded 표와 경고 목록이 뜹니다.
   동기화 중 다시 누르면 즉시 "이미 동기화 중"이 표시됩니다. 요약·인사이트 배치가 저장소를 쓰는 중이면
   60초까지 기다린 뒤 "배치가 끝난 뒤 다시 누르세요"로 돌아옵니다. 음성 대화는 동기화 중에도 계속됩니다.
8. 로봇에게 "이번 주 북마크 얘기하자"라고 말합니다. 요약·인사이트 배치는 기존 `get_insight` 흐름이 처리합니다.

## 시뮬 데모 (실제 Chrome 없이)

1. 같은 섹션의 **데모 데이터 준비** → 대상 폴더(기본 `~/deskmate-demo`)에 픽스처(요약된 북마크 3개 +
   ready 인사이트 노트 1개 + 가짜 `User Data`)가 복사되고, 돌려받은 `.env` 값 세 줄 아래의
   **이 값을 .env에 적용** 버튼이 6번 단계를 대신합니다. 대상 폴더가 이미 있으면 거부합니다(덮어쓰기 없음).
   픽스처는 저장소 체크아웃(`tests/deskmate/fixtures`)에만 있으므로 설치본(editable 아님)에서는 "픽스처 없음"이 뜹니다.
2. 페르소나 `deskmate_ko`는 Personalities 화면에서 고릅니다("Set as default"가 `REACHY_MINI_CUSTOM_PROFILE`을 저장).
3. "10월 31일부터 11월 6일까지 북마크 얘기하자" → `ready` 노트로 바로 대화.

## 그 밖의 .env 값 (대시보드가 쓰지 않는 것)

대시보드는 위 세 키만 씁니다. 나머지는 `.env.example` 7절 주석을 보고 직접 적습니다: 요약 배치의 하루 상한
`DESKMATE_DAILY_MAX_SUMMARIES`(기본 100, 넘치면 다음 날 백필, M7)와 호출 간격 `DESKMATE_CALL_INTERVAL_S`(기본 6초),
그리고 저장소 미러 `DESKMATE_GIT_MIRROR=1`(기본 끔, M9 — 켜면 동기화 결과 표 위에 프로필별 미러 커밋 수가 함께 나오고,
과거 이력은 `python -m deskmate.sync --git-rebuild`로 재구성합니다).

같은 일을 터미널로 하려면: `python -m deskmate.sync --discover`(탐색), `python -m deskmate.sync`(동기화),
`python scripts/deskmate_demo_setup.py ~/deskmate-demo`(데모).

## JSON-RPC 메서드 (`/rpc`, 다른 클라이언트에서 쓸 때)

| 메서드 | params | 오류 reason |
| :--- | :--- | :--- |
| `deskmate.status` | `{}` | (읽기 전용, 오류 없음) |
| `deskmate.discover` | `{chrome_dir?}` | `deskmate_chrome_dir_not_found`, `deskmate_no_profiles` |
| `deskmate.sync` | `{profiles?, repo?, chrome_dir?}` | `deskmate_not_configured`, `deskmate_sync_running`, `deskmate_repo_locked`, `deskmate_sync_failed` |
| `deskmate.repo.set` | `{path, create}` | `deskmate_repo_path_invalid`, `deskmate_repo_path_relative`, `deskmate_repo_inside_chrome`, `deskmate_repo_path_reserved`, `deskmate_repo_not_writable` |
| `deskmate.env.apply` | `{DESKMATE_CHROME_PROFILES?, DESKMATE_BOOKMARK_REPO?, DESKMATE_CHROME_USER_DATA_DIR?}` | `deskmate_env_key_not_allowed`, `deskmate_env_value_invalid` + `repo.set`의 경로 오류 |
| `deskmate.demo_setup` | `{target}` | `deskmate_demo_target_exists`, `deskmate_fixtures_missing`, `deskmate_demo_failed` |

형식이 잘못된 params(문자열이 아닌 `chrome_dir` 등)는 `deskmate_params_invalid`. 결과 필드는 계획서의 라우트 명세 표를 따릅니다.

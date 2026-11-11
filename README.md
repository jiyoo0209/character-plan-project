# 캐릭터 일정 비서 (CharacterPlan)

바탕화면에 캐릭터가 늘 떠 있다가, 일정이 다가오면 통통 뛰면서 말을 걸어 주는 Windows 일정 앱입니다.

> "지유야! 오늘 오전 10시에 회의 일정이 있어! 10분 남았어."

## 기능

- **바탕화면 상주**: 아이콘 위, 일반 창 아래에 떠 있고 `Win+D`(바탕화면 보기)에도 사라지지 않습니다.
- **클릭 → 오늘 할 일**: 캐릭터를 누르면 머리 위에 오늘 일정 체크리스트가 뜹니다. 줄을 누르면 체크되고 테마 색 빗금이 그어집니다 (반복 일정은 날마다 따로). 맨 아래 **일정 관리**를 누르면 달력이 열립니다.
- **달력**: 일정을 추가/수정/삭제할 수 있습니다. 일정 있는 날은 색으로 표시됩니다.
- **드래그 이동**: 캐릭터를 끌어서 원하는 위치에 두면 다음 실행 때도 그 자리에 나옵니다.
- **알림**: 설정한 시간 전(기본 10분)과 정각에 캐릭터가 뛰면서 말풍선으로 알려 줍니다. 알림 중에는 다른 창 위로 올라오고, 말풍선이나 캐릭터를 누르면 끝납니다.
- **실행 시 인사**: 켤 때 오늘 남은 일정을 요약해 줍니다.
- **자동 실행**: Windows 로그인 시 항상 같이 켜집니다.
- **알림 효과음**: 일정 알림 때 캐릭터마다 다른 효과음이 납니다 (`assets/sounds/<캐릭터 id>.mp3`). 파일이 없으면 Windows 기본 알림음이 나고, 설정의 '알림 소리'에서 끌 수 있습니다.
- **우클릭 메뉴 · 트레이 아이콘**: 일정 보기, 설정, 캐릭터 숨기기, 종료.
- **캐릭터 고르기**: 설정에서 치이카와 · 우사기 · 쿠리만쥬 중에 고릅니다. 크기는 설정에서 90~260px(10px 단위, 기본 160px)로 바꿀 수 있습니다. GIF는 애니메이션이 그대로 재생되고, 그 위에 둥실거림·알림 점프 모션이 더해집니다.

### 일정 카테고리

일정마다 카테고리를 하나 고를 수 있습니다 (안 골라도 됨): 💼 일 · 📚 공부 · 🎮 게임 · ☕ 약속 · 💪 운동 · 💊 병원 · ✈️ 여행 · 📌 기타.
목록은 `app/categories.py`, 아이콘은 `assets/icons/categories/` 에 있습니다.
일정 추가·수정 창에서 날짜는 달력에서 고른 날로 고정되고, 시간은 시간 칸을 눌러 입력합니다.

### 단일 일정 / 반복 일정

일정 추가 창 위쪽에서 **단일 일정** 또는 **반복 일정**을 고릅니다.

- 반복: 매일 · 매주(요일 여러 개) · 매월(N일 / N째 주 X요일) · 매년, **종료일은 꼭** 고릅니다 (시작일보다 앞은 못 고름).
  아래 요약 줄에 '매주 월 · 수 · 금 오후 7시 · 12월 31일까지 (22번)' 처럼 몇 번인지 보여 줍니다. 반복 일정에는 메모가 없습니다.
- 달력에는 반복되는 날마다 점이 찍히고, 일정 카드에는 반복 규칙과 테마 색 반복 화살표가 붙습니다.
- 반복 일정을 수정하거나 지우면 '이 날만 / 이 날부터 쭉 / 전체' 중에 고릅니다.
  '이 날만 바꾸기'는 그날을 반복에서 빼고 단일 일정으로 따로 만듭니다.
- 알림은 반복되는 날마다 단일 일정과 똑같이 미리 알림 + 정각 알림을 줍니다.

### D-day

- 일정 추가·수정 창의 **D-day로 세기** 스위치를 켜면 D-day 일정이 됩니다 (단일 일정, 매년 반복 일정만. 매년 반복은 다음 기념일까지 셉니다).
- 달력 창 위쪽에 가까운 D-day 3개가 카드로 나오고 (누르면 그 날로 이동), 달력 날짜 옆에 작은 별이 붙습니다.
- 날짜가 지난 D-day는 D-day 카드·별에서만 빠지고 일정은 그대로 남습니다.

### 하루 브리핑

설정에서 **컴퓨터 켤 때**(앱이 켜질 때) 또는 **정해진 시간**(예: 오전 8시 30분, 하루 한 번)을 고릅니다.
캐릭터가 말풍선으로 오늘 남은 일정을 먼저 말하고, 이어서 등록된 D-day를 알려 줍니다.
정해진 시간이 지난 뒤에 컴퓨터를 켜면, 그날 아직 안 했으면 켜자마자 브리핑합니다.

### 캐릭터 이미지 넣기

캐릭터 목록은 `app/config.py` 의 `CHARACTERS` 에 있고, 이미지는 `assets/characters/` 에 넣습니다 (`.gif` 권장, `.webp`, `.png` 도 됨).

| id | 이름 | 바탕화면 캐릭터 | 설정 창 고르기 카드 | 달력 '일정 없는 날' |
| --- | --- | --- | --- | --- |
| `chiikawa` | 치이카와 | `chiikawa.gif` | `chiikawa_pick.gif` | `chiikawa_1.png` |
| `usagi` | 우사기 | `usagi.gif` | `usagi_pick.gif` | `usagi_1.png` |
| `kurimanju` | 쿠리만쥬 | `kurimanju.gif` | `kurimanju_pick.gif` | `kurimanju_1.png` |

- 고르기 카드는 평소엔 첫 장면으로 멈춰 있다가, 고르면 뽀잉 튀어 오르면서 GIF 를 한 바퀴 재생하고 다시 멈춥니다.
- 둘 중 하나만 있으면 있는 그림을 양쪽에 같이 씁니다 (예: `usagi_pick.gif` 만 있으면 바탕화면에도 그 그림).
- `_1.png` 가 없으면 달력의 일정 없는 날에는 테마 색 리본이 나옵니다.

캐릭터마다 설정 창 색 테마가 있습니다 (`app/themes.py`: 치이카와 핑크 · 우사기 크림 노랑 · 쿠리만쥬 밤색).
캐릭터 높이는 `CHARACTER_SIZE`, 평소 말풍선 표시 시간은 `BUBBLE_SECONDS` 에서 바꿉니다.

## 저장 위치

설치 폴더 안 `data/` 에 저장됩니다.

| 파일 | 내용 |
| --- | --- |
| `data/schedules.json` | 일정 |
| `data/settings.json` | 이름, 미리 알림 시간, 고른 캐릭터, 하루 브리핑, 알림 소리, 캐릭터 위치 |
| `data/error.log` | 오류 기록 (문제가 있을 때만 생김) |

설치 폴더에 쓰기 권한이 없으면(예: `Program Files`) 자동으로 `%LOCALAPPDATA%\CharacterPlan\data` 를 씁니다.
제거해도 `data/` 는 남으므로 다시 설치하면 일정이 그대로 있습니다.

```json
{
  "version": 1,
  "schedules": [
    {
      "title": "회의",
      "date": "2026-11-05",
      "time": "10:00",
      "memo": "3층 회의실",
      "id": "a1b2c3d4e5f6",
      "notified_before": false,
      "notified_on_time": false
    }
  ]
}
```

## 개발 실행

Python 3.10 이상.

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## 빌드 / 설치 파일 만들기

```powershell
.\build.ps1             # dist\CharacterPlan\CharacterPlan.exe
.\build.ps1 -Installer  # installer_output\CharacterPlan-Setup.exe (Inno Setup 6 필요)
```

설치 파일은 `%LOCALAPPDATA%\Programs\CharacterPlan` 에 관리자 권한 없이 설치되고, Windows 시작 시 자동 실행이 등록됩니다.
Inno Setup 에 한국어 언어 파일이 없다는 오류가 나면 `installer.iss` 의 `[Languages]` 를 `compiler:Default.isl` 로 바꾸세요.

## 자동 업데이트

1. `main` 에 파일을 올리면 GitHub Actions 가 설치 파일을 만들고 **Releases** 에 새 버전(`v0.2.<빌드 번호>`)으로 올립니다.
   릴리스의 '달라진 점'은 지난 릴리스 이후 커밋 메시지에서 뽑습니다 (본문의 `- ` 줄, 없으면 제목. `Add files via upload` 같은 기본 메시지는 빠짐).
2. 설치된 앱은 켜질 때(5초 뒤)와 6시간마다 최신 릴리스를 확인하고, 새 버전이면 업데이트 창을 띄웁니다.
3. '지금 업데이트' → 설치 파일을 받아 조용히 설치(`/VERYSILENT`) → 앱이 꺼졌다가 다시 켜집니다. 일정·설정(`data\`)은 그대로 남습니다.

소스로 실행할 때(`python main.py`)는 확인하지 않습니다.

인증서는 윈도우가 직접 확인하고(`truststore`), 안 되면 앱에 넣은 인증서 묶음(`certifi`)으로 다시 시도합니다. 확인·받기에 실패하면 이유가 `data\update.log` 에 남습니다.

## 구조

```
main.py                  진입점
app/app.py               전체 조립 (트레이, 메뉴, 알림 흐름, 중복 실행 방지)
app/character.py         캐릭터 창(애니메이션·드래그) + 말풍선
app/today_popup.py       캐릭터 클릭 → 오늘 할 일 체크리스트
app/calendar_window.py   달력 / 일정 편집
app/settings_dialog.py   설정 창 (캐릭터 고르기, 이름, 미리 알림)
app/frame.py             둥근 창 테두리 + 창 버튼
app/updater.py           자동 업데이트 (최신 릴리스 확인, 설치 파일 받기·실행)
app/update_dialog.py     업데이트 창
app/version.py           앱 버전 (빌드할 때 CI 가 채움)
app/themes.py            캐릭터별 색 테마
app/categories.py        일정 카테고리 목록 (이름 + 이모지 아이콘)
app/recurrence.py        반복 일정 규칙 (매일/매주/매월/매년, 종료일)
app/notifier.py          15초마다 일정 확인 → 알림
app/sound.py             캐릭터 효과음 재생
app/messages.py          대사 (이름 뒤 아/야, 오전/오후 표현)
app/storage.py           schedules.json 읽기/쓰기
app/config.py            경로, settings.json
app/desktop.py           Windows 바탕화면 레이어 고정 (Win32 API)
app/autostart.py         시작 프로그램 등록 (HKCU Run)
assets/characters/       캐릭터 이미지 (<id>.gif)
assets/sounds/           캐릭터 효과음 (<id>.mp3, .wav 도 됨)
assets/icon.ico          아이콘
assets/fonts/            폰트 (주아, SIL OFL)
assets/icons/            작은 아이콘 (테마 색 리본, 카테고리 이모지: Noto Emoji, Apache 2.0)
tools/make_character.py  기본 캐릭터 이미지 생성 스크립트
tools/release_notes.py   릴리스 '달라진 점' 만들기 (CI)
```

### 바탕화면 고정 방식

월페이퍼 엔진처럼 아이콘 *뒤*(WorkerW)에 그리면 클릭이 아이콘으로 가 버려 캐릭터를 누를 수 없습니다.
그래서 캐릭터 창의 소유자를 바탕화면 창(`Progman`)으로 지정해 **아이콘 위 · 일반 창 아래** 레이어에 둡니다.
탐색기가 재시작되거나 창이 숨겨지는 경우를 대비해 1.5초마다 다시 확인합니다.

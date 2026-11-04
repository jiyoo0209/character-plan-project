# 캐릭터 일정 비서 (CharacterPlan)

바탕화면에 캐릭터가 늘 떠 있다가, 일정이 다가오면 통통 뛰면서 말을 걸어 주는 Windows 일정 앱입니다.

> "지유야! 오늘 오전 10시에 회의 일정이 있어! 10분 남았어."

## 기능

- **바탕화면 상주**: 아이콘 위, 일반 창 아래에 떠 있고 `Win+D`(바탕화면 보기)에도 사라지지 않습니다.
- **클릭 → 달력**: 캐릭터를 누르면 달력이 열리고 일정을 추가/수정/삭제할 수 있습니다. 일정 있는 날은 색으로 표시됩니다.
- **드래그 이동**: 캐릭터를 끌어서 원하는 위치에 두면 다음 실행 때도 그 자리에 나옵니다.
- **알림**: 설정한 시간 전(기본 10분)과 정각에 캐릭터가 뛰면서 말풍선으로 알려 줍니다. 알림 중에는 다른 창 위로 올라오고, 말풍선이나 캐릭터를 누르면 끝납니다.
- **실행 시 인사**: 켤 때 오늘 남은 일정을 요약해 줍니다.
- **자동 실행**: Windows 로그인 시 같이 켜집니다 (설치 옵션 / 설정에서 변경).
- **우클릭 메뉴 · 트레이 아이콘**: 일정 보기, 설정, 캐릭터 숨기기, 종료.
- **캐릭터 교체**: 설정 → 캐릭터 이미지에서 투명 배경 PNG 또는 움직이는 GIF를 고르면 바뀝니다. GIF는 애니메이션이 그대로 재생되고, 그 위에 둥실거림·알림 점프 모션이 더해집니다.

### 기본 캐릭터 바꾸기

`assets/character.gif` 파일이 있으면 그것이 기본 캐릭터가 되고, 없으면 `assets/character.png`(새싹이)를 씁니다.
설정에서 따로 이미지를 고른 경우에는 그 이미지가 우선합니다.

## 저장 위치

설치 폴더 안 `data/` 에 저장됩니다.

| 파일 | 내용 |
| --- | --- |
| `data/schedules.json` | 일정 |
| `data/settings.json` | 이름, 알림 시간, 캐릭터 크기·위치 등 |
| `data/character/` | 직접 고른 캐릭터 이미지 |
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

설치 파일은 `%LOCALAPPDATA%\Programs\CharacterPlan` 에 관리자 권한 없이 설치되고, "Windows 시작 시 자동 실행"이 기본 체크되어 있습니다.
Inno Setup 에 한국어 언어 파일이 없다는 오류가 나면 `installer.iss` 의 `[Languages]` 를 `compiler:Default.isl` 로 바꾸세요.

## 구조

```
main.py                  진입점
app/app.py               전체 조립 (트레이, 메뉴, 알림 흐름, 중복 실행 방지)
app/character.py         캐릭터 창(애니메이션·드래그) + 말풍선
app/calendar_window.py   달력 / 일정 편집
app/notifier.py          15초마다 일정 확인 → 알림
app/messages.py          대사 (이름 뒤 아/야, 오전/오후 표현)
app/storage.py           schedules.json 읽기/쓰기
app/config.py            경로, settings.json
app/desktop.py           Windows 바탕화면 레이어 고정 (Win32 API)
app/autostart.py         시작 프로그램 등록 (HKCU Run)
assets/                  기본 캐릭터, 아이콘
tools/make_character.py  기본 캐릭터 이미지 생성 스크립트
```

### 바탕화면 고정 방식

월페이퍼 엔진처럼 아이콘 *뒤*(WorkerW)에 그리면 클릭이 아이콘으로 가 버려 캐릭터를 누를 수 없습니다.
그래서 캐릭터 창의 소유자를 바탕화면 창(`Progman`)으로 지정해 **아이콘 위 · 일반 창 아래** 레이어에 둡니다.
탐색기가 재시작되거나 창이 숨겨지는 경우를 대비해 1.5초마다 다시 확인합니다.
